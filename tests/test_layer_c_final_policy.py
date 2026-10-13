"""Final economic-policy regressions for the integer-accounting research model.

These tests exercise the pinned Python numerical helper, not compiled AVM code.
"""

from copy import deepcopy
from decimal import Decimal as D
from itertools import permutations
from random import Random
import unittest

from research.active_lp.candidate_global_state import CandidateGlobalStateEngine, create_candidate_initial_state
from research.active_lp.events import (
    BootstrapMarket, BuyOutcome, CancelMarket, ClaimLpFees, ClaimLpResidual,
    ClaimRefund, ClaimWinnings, LpEnterActive, ResolveMarket, SellOutcome, WithdrawLpFees,
)
from research.active_lp.layer_c_fixed_point import (
    AVM_AMOUNT_SCALE, MAX_UINT64, LayerCFixedPointEngine, LayerCInvariantChecker,
    _amount_to_fp, _basis_reduction_fp, _ledger_fp, _to_uint64, create_layer_c_initial_state,
)
from research.active_lp.reference_parallel_lmsr import (
    RESERVE_POOL, RefundReserveViolation, ReferenceParallelLmsrEngine,
    _claimable_residual_for_cohort, _refund_reserve_requirement,
    _total_non_fee_assets, _winner_reserve_requirement, create_initial_state,
)


MICRO = D("0.000001")


def setup(n=3, fees=(100, 25), engine_type=LayerCFixedPointEngine, state_factory=create_layer_c_initial_state):
    engine = engine_type(
        residual_policy=RESERVE_POOL, residual_weight_scheme="linear_lambda_normalized",
        residual_linear_lambda=D("0.15"), lp_fee_bps=fees[0], protocol_fee_bps=fees[1],
    )
    state = state_factory(n, residual_weight_scheme="linear_lambda_normalized", residual_linear_lambda=D("0.15"))
    # A specified common micro-unit deposit avoids a cross-model bootstrap confound.
    funding = (D(n).ln() * 100).quantize(MICRO, rounding="ROUND_CEILING") + D(20)
    return engine, engine.apply_event(state, BootstrapMarket(1, "creator", funding, D(100)))


def buy(t, actor, outcome, shares):
    return BuyOutcome(t, actor, outcome, D(shares), D("1e50"))


class LayerCFinalPolicyTests(unittest.TestCase):
    def assert_safe(self, state):
        failures = [item for item in LayerCInvariantChecker(residual_policy=RESERVE_POOL).check_all(state) if not item.passed]
        self.assertEqual(failures, [], failures)
        self.assertGreaterEqual(_total_non_fee_assets(state), _winner_reserve_requirement(state))
        for amount in (state.treasury.contract_funds, state.treasury.lp_fee_balance, state.treasury.protocol_fee_balance):
            _ledger_fp(amount, name="balance")

    def test_unsafe_sell_is_atomic_and_cancel_refunds_are_integer_backed(self):
        for fees in ((0, 0), (100, 25)):
            engine, state = setup(fees=fees)
            for event in (buy(2, "arb", 0, 100), buy(3, "bag0", 0, 500), SellOutcome(4, "arb", 0, D(100), 0), buy(5, "arb", 1, 100), buy(6, "bag1", 1, 1000)):
                state = engine.apply_event(state, event)
                self.assert_safe(state)
            quote = engine.sell_execution_quote(state, "arb", 1, D(100))
            self.assertFalse(quote["executable"])
            self.assertLess(quote["cancellation_reserve_margin"], -D(22))
            before = deepcopy(state)
            with self.assertRaises(RefundReserveViolation):
                engine.apply_event(state, SellOutcome(7, "arb", 1, D(100), 0))
            self.assertEqual(state, before)
            state = engine.apply_event(state, CancelMarket(8, "regression"))
            owed = _refund_reserve_requirement(state)
            paid = D(0)
            for trader, positions in list(state.traders.positions_by_trader.items()):
                for outcome, shares in enumerate(positions):
                    if shares:
                        funds = state.treasury.contract_funds
                        state = engine.apply_event(state, ClaimRefund(9, trader, outcome, shares))
                        paid += funds - state.treasury.contract_funds
                        self.assert_safe(state)
            self.assertEqual(paid, owed)

    def test_pooled_integer_snapshot_matches_exact_policy_and_every_claim_order(self):
        for cancelled in (False, True):
            engine, state = setup(n=64)
            state = engine.apply_event(state, buy(2, "alice", 0, 250))
            state = engine.apply_event(state, buy(3, "bob", 1, 500))
            state = engine.apply_event(state, LpEnterActive(4, "late", D(20), D("1e50"), state.pricing.price_vector, D("1e-12")))
            state = engine.apply_event(state, CancelMarket(5, "test") if cancelled else ResolveMarket(5, 1))
            for key, sponsor in state.sponsors.items():
                exact_entitlement = _claimable_residual_for_cohort(state, sponsor)
                integer_entitlement = D(state.residual_entitlements_fp[key]) / AVM_AMOUNT_SCALE
                self.assertGreaterEqual(exact_entitlement - integer_entitlement, 0)
                self.assertLess(exact_entitlement - integer_entitlement, MICRO)
            self.assertLess(state.treasury.rounding_dust, MICRO * len(state.sponsors))
            actions = [ClaimLpResidual(6, "creator"), ClaimLpResidual(6, "late")]
            if cancelled:
                actions.extend([ClaimRefund(6, "alice", 0, D(250)), ClaimRefund(6, "bob", 1, D(500))])
            else:
                actions.append(ClaimWinnings(6, "bob", 1, D(500)))
            for ordering in permutations(actions):
                current = deepcopy(state)
                for event in ordering:
                    current = engine.apply_event(current, event)
                    self.assert_safe(current)
                self.assertEqual(_total_non_fee_assets(current), state.treasury.rounding_dust)
                self.assertEqual(current.residual_entitlements_fp, state.residual_entitlements_fp)
                before = current.treasury.contract_funds
                # Later claim timestamps do not recompute weights or revive claims.
                for actor in ("creator", "late"):
                    current = engine.apply_event(current, ClaimLpResidual(700, actor))
                self.assertEqual(current.treasury.contract_funds, before)

    def test_partial_refunds_conserve_basis_and_leave_no_fractional_claim(self):
        engine, state = setup()
        state = engine.apply_event(state, buy(2, "alice", 0, 7))
        state = engine.apply_event(state, CancelMarket(3, "partial refunds"))
        basis = state.traders.cost_basis_by_trader["alice"][0]
        paid = D(0)
        for quantity in (D("0.333333"), D("0.000001"), D("2"), D("4.666666")):
            funds = state.treasury.contract_funds
            state = engine.apply_event(state, ClaimRefund(4, "alice", 0, quantity))
            paid += funds - state.treasury.contract_funds
            self.assert_safe(state)
        self.assertEqual(paid, basis)
        self.assertEqual(state.traders.cost_basis_by_trader["alice"][0], 0)
        self.assertEqual(_basis_reduction_fp(D(3), MICRO, D(1)), 0)

    def test_fee_units_are_consistent_and_fees_are_nonretroactive(self):
        engine, state = setup(fees=(100, 25))
        state = engine.apply_event(state, buy(2, "alice", 0, 30))
        old_fees = next(iter(state.sponsors.values())).claimable_fees
        state = engine.apply_event(state, LpEnterActive(3, "late", D(100), D("1e50"), state.pricing.price_vector, D("1e-12")))
        late_key = next(key for key, sponsor in state.sponsors.items() if sponsor.sponsor_id == "late")
        creator_key = next(key for key, sponsor in state.sponsors.items() if sponsor.sponsor_id == "creator")
        self.assertEqual(state.sponsors[late_key].claimable_fees, 0)
        state = engine.apply_event(state, buy(4, "bob", 1, 30))
        early_increment = state.sponsors[creator_key].claimable_fees - old_fees
        late_increment = state.sponsors[late_key].claimable_fees
        self.assertLessEqual(abs(early_increment - late_increment), MICRO)
        self.assertEqual(sum(s.claimable_fees for s in state.sponsors.values()), state.treasury.lp_fee_balance)
        assets = _total_non_fee_assets(state)
        state = engine.apply_event(state, ClaimLpFees(5, "late"))
        state = engine.apply_event(state, WithdrawLpFees(6, "late", late_increment))
        self.assertEqual(_total_non_fee_assets(state), assets)
        self.assert_safe(state)

    def test_explicit_margin_and_user_order_caps_reject_without_mutation(self):
        engine, state = setup(fees=(0, 0))
        quote = engine.buy_cost(state.pricing, 0, D(100))
        with self.assertRaisesRegex(ValueError, "max_total_cost"):
            engine.apply_event(state, BuyOutcome(2, "alice", 0, D(100), quote - MICRO))
        state = engine.apply_event(state, buy(2, "alice", 0, 100))
        quote = engine.sell_return(state.pricing, 0, D(10))
        with self.assertRaisesRegex(ValueError, "min_total_return"):
            engine.apply_event(state, SellOutcome(3, "alice", 0, D(10), quote + MICRO))
        engine.reserve_margin_fp = _ledger_fp(_total_non_fee_assets(state), name="assets")
        self.assertFalse(engine.sell_execution_quote(state, "alice", 0, D(10))["executable"])
        before = deepcopy(state)
        with self.assertRaises(RefundReserveViolation):
            engine.apply_event(state, SellOutcome(3, "alice", 0, D(10), 0))
        self.assertEqual(state, before)

    def test_uint64_bounds_cover_authoritative_state_and_inputs(self):
        self.assertEqual(_to_uint64(MAX_UINT64, name="limit"), MAX_UINT64)
        self.assertEqual(_amount_to_fp(D(MAX_UINT64) / AVM_AMOUNT_SCALE), MAX_UINT64)
        for bad in (-1, MAX_UINT64 + 1, D("0.1"), D("NaN"), D("Infinity")):
            with self.assertRaises(ValueError):
                _to_uint64(bad, name="bad")
        engine = LayerCFixedPointEngine(residual_policy=RESERVE_POOL)
        state = create_layer_c_initial_state(3)
        with self.assertRaisesRegex(ValueError, "uint64"):
            engine.apply_event(state, BootstrapMarket(1, "creator", D(MAX_UINT64 + 1) / AVM_AMOUNT_SCALE, D(100)))
        self.assertEqual(state.treasury.contract_funds, 0)
        engine, state = setup(fees=(0, 0))
        state.treasury.contract_funds = D(MAX_UINT64) / AVM_AMOUNT_SCALE
        before = deepcopy(state)
        with self.assertRaisesRegex(ValueError, "uint64"):
            engine.apply_event(state, buy(2, "alice", 0, 1))
        self.assertEqual(state, before)

    def test_certified_micro_quotes_and_round_trips_cannot_create_trader_profit(self):
        engine, state = setup(fees=(0, 0))
        state = engine.apply_event(state, buy(2, "large", 0, 1000))
        # Archived arithmetic quoted100 micro-units for this1-micro sale.
        self.assertLessEqual(engine.sell_return(state.pricing, 0, MICRO), MICRO)
        for outcome in range(3):
            for quantity in (MICRO, D("0.000003"), D(1)):
                before = state.treasury.contract_funds
                before_q = state.pricing.pricing_q
                state = engine.apply_event(state, BuyOutcome(3, "roundtrip", outcome, quantity, quantity))
                state = engine.apply_event(state, SellOutcome(3, "roundtrip", outcome, quantity, 0))
                self.assertGreaterEqual(state.treasury.contract_funds, before)
                self.assertEqual(state.pricing.pricing_q, before_q)
                self.assert_safe(state)

    def test_three_models_apply_same_terminal_policy_on_matched_histories(self):
        models = ((ReferenceParallelLmsrEngine, create_initial_state), (CandidateGlobalStateEngine, create_candidate_initial_state), (LayerCFixedPointEngine, create_layer_c_initial_state))
        for n in (3, 8, 64):
            active = []
            for engine_type, state_factory in models:
                engine, state = setup(n=n, engine_type=engine_type, state_factory=state_factory)
                for event in (buy(2, "alice", 0, 80), buy(3, "bob", 1, 50)):
                    state = engine.apply_event(state, event)
                state = engine.apply_event(state, LpEnterActive(4, "late", D(20), D("1e50"), state.pricing.price_vector, D("1e-12")))
                state = engine.apply_event(state, SellOutcome(5, "alice", 0, D(20), 0))
                active.append((engine, state))
            for branch in (0, 1, n - 1, None):
                entitlements = []
                for engine, state in active:
                    state = engine.apply_event(state, CancelMarket(6, "test") if branch is None else ResolveMarket(6, branch))
                    nav = engine.mark_to_market_nav(state)
                    entitlements.append(nav)
                for exact in entitlements[:2]:
                    for key in exact:
                        # An empirical fixture tolerance, not a uniform error theorem.
                        self.assertLess(abs(exact[key] - entitlements[2][key]), D("0.05"))

    def test_seeded_long_paths_keep_all_terminal_states_and_entitlements_funded(self):
        for seed, n in ((9150, 3), (9151, 8)):
            rng = Random(seed)
            engine, state = setup(n=n)
            for t in range(2, 122):
                if t in (25, 60, 90):
                    event = LpEnterActive(t, f"lp{t}", D(20), D("1e50"), state.pricing.price_vector, D("1e-12"))
                else:
                    positions = [(actor, i, shares) for actor, vector in state.traders.positions_by_trader.items() for i, shares in enumerate(vector) if shares > 0]
                    if positions and rng.random() < 0.55:
                        actor, i, held = rng.choice(positions)
                        event = SellOutcome(t, actor, i, min(held, D(rng.choice((5, 20, 60, 120)))), 0)
                    else:
                        event = buy(t, f"trader{rng.randrange(4)}", rng.randrange(n), rng.choice((5, 20, 60, 120)))
                before = deepcopy(state)
                try:
                    state = engine.apply_event(state, event)
                except RefundReserveViolation:
                    self.assertEqual(state, before)
                self.assert_safe(state)
            for outcome in list(range(n)) + [None]:
                final = engine.apply_event(state, CancelMarket(122, "branch") if outcome is None else ResolveMarket(122, outcome))
                for sponsor in ("creator", "lp25", "lp60", "lp90"):
                    final = engine.apply_event(final, ClaimLpResidual(123, sponsor))
                    self.assert_safe(final)
                for actor, positions in list(final.traders.positions_by_trader.items()):
                    for i, shares in enumerate(positions):
                        if shares and (outcome is None or outcome == i):
                            event = ClaimRefund(124, actor, i, shares) if outcome is None else ClaimWinnings(124, actor, i, shares)
                            final = engine.apply_event(final, event)
                            self.assert_safe(final)
                self.assertEqual(_total_non_fee_assets(final), final.treasury.rounding_dust)


if __name__ == "__main__":
    unittest.main()
