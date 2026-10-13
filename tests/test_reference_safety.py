"""Economic regressions for the exact reference and compressed Decimal model."""

from copy import deepcopy
from decimal import Decimal as D
from itertools import permutations
from random import Random
import unittest

from research.active_lp.candidate_global_state import (
    CandidateGlobalStateEngine, CandidateInvariantChecker, create_candidate_initial_state,
)
from research.active_lp.events import (
    BootstrapMarket, BuyOutcome, CancelMarket, ClaimLpResidual, ClaimRefund,
    ClaimWinnings, LpEnterActive, ResolveMarket, SellOutcome,
)
from research.active_lp.precision import high_precision
from research.active_lp.reference_math import collateral_required, uniform_price_vector
from research.active_lp.reference_parallel_lmsr import (
    RESERVE_POOL, STRICT_ALL_CLAIMED, RefundReserveViolation,
    ReferenceParallelLmsrEngine, ReferenceInvariantChecker,
    _claimable_residual_for_cohort, _refund_reserve_requirement,
    _total_non_fee_assets, _winner_reserve_requirement, create_initial_state,
    refund_reserve_margin,
)


MODELS = (
    (ReferenceParallelLmsrEngine, ReferenceInvariantChecker, create_initial_state),
    (CandidateGlobalStateEngine, CandidateInvariantChecker, create_candidate_initial_state),
)
TOL = D("1e-16")


def bootstrap(model, n=3, policy=RESERVE_POOL, fees=(0, 0)):
    engine_type, checker_type, initial_state = model
    engine = engine_type(
        residual_policy=policy, residual_weight_scheme="linear_lambda_normalized",
        residual_linear_lambda=D("0.15"), lp_fee_bps=fees[0], protocol_fee_bps=fees[1],
    )
    state = initial_state(
        n, residual_weight_scheme="linear_lambda_normalized", residual_linear_lambda=D("0.15"),
    )
    with high_precision():
        funding = collateral_required(D(100), uniform_price_vector(n)) + D(20)
    state = engine.apply_event(state, BootstrapMarket(1, "creator", funding, D(100)))
    return engine, checker_type(residual_policy=policy), state


def buy(t, trader, outcome, shares):
    return BuyOutcome(t, trader, outcome, D(shares), D("1e50"))


def low_tail_state(model, policy=RESERVE_POOL):
    engine, checker, state = bootstrap(model, n=64, policy=policy)
    state = engine.apply_event(state, buy(2, "loser", 0, 250))
    state = engine.apply_event(state, buy(3, "winner", 1, 500))
    state = engine.apply_event(state, LpEnterActive(
        4, "late", D(20), D("1e50"), state.pricing.price_vector, D("1e-16"),
    ))
    state = engine.apply_event(state, ResolveMarket(5, 1))
    return engine, checker, state


class ReferenceSafetyTests(unittest.TestCase):
    def assert_safe(self, checker, state):
        failures = [check for check in checker.check_all(state) if not check.passed]
        self.assertEqual(failures, [], failures)
        self.assertGreaterEqual(_total_non_fee_assets(state) - _winner_reserve_requirement(state), -TOL)

    def test_original_insolvency_history_rejects_only_the_underfunding_sell(self):
        for model in MODELS:
            for fees in ((0, 0), (100, 25)):
                with self.subTest(model=model[0].__name__, fees=fees):
                    engine, checker, state = bootstrap(model, fees=fees)
                    for event in (
                        buy(2, "arb", 0, 100), buy(3, "bag0", 0, 500),
                        SellOutcome(4, "arb", 0, D(100), D(0)),
                        buy(5, "arb", 1, 100), buy(6, "bag1", 1, 1000),
                    ):
                        state = engine.apply_event(state, event)
                        self.assert_safe(checker, state)
                    quote = engine.sell_execution_quote(state, "arb", 1, D(100))
                    self.assertFalse(quote["executable"])
                    self.assertAlmostEqual(float(quote["cancellation_reserve_margin"]), -22.4487554176, places=8)
                    before = deepcopy(state)
                    with self.assertRaises(RefundReserveViolation) as rejected:
                        engine.apply_event(state, SellOutcome(7, "arb", 1, D(100), D(0)))
                    self.assertAlmostEqual(float(rejected.exception.shortfall), 22.4487554176, places=8)
                    self.assertEqual(state, before, "rejected sell mutated the market")

                    # Cancellation is now fully backed; every still-open position
                    # receives its remaining cost basis, including the rejected seller.
                    state = engine.apply_event(state, CancelMarket(8, "test"))
                    original_refunds = _refund_reserve_requirement(state)
                    paid = D(0)
                    for trader, holdings in list(state.traders.positions_by_trader.items()):
                        for outcome, shares in enumerate(holdings):
                            if shares > 0:
                                cash_before = state.treasury.contract_funds
                                state = engine.apply_event(state, ClaimRefund(9, trader, outcome, shares))
                                paid += cash_before - state.treasury.contract_funds
                                self.assert_safe(checker, state)
                    self.assertLess(abs(paid - original_refunds), TOL)
                    self.assertEqual(_refund_reserve_requirement(state), 0)

    def test_resolved_diagnostic_ignores_impossible_losing_branches(self):
        for model in MODELS:
            with self.subTest(model=model[0].__name__):
                engine, checker, state = low_tail_state(model, STRICT_ALL_CLAIMED)
                creator_key = next(key for key, sponsor in state.sponsors.items() if sponsor.sponsor_id == "creator")
                before = state.sponsors[creator_key].residual_basis_by_outcome[1]
                state = engine.apply_event(state, ClaimWinnings(6, "winner", 1, D(500)))
                residual = state.sponsors[creator_key].residual_basis_by_outcome
                self.assertAlmostEqual(float(residual[0]), -189.4643089367, places=8)
                self.assertLess(abs(residual[1] - before), TOL)
                self.assertAlmostEqual(float(residual[1]), 60.5356910633, places=8)
                self.assert_safe(checker, state)

    def test_pooled_winner_and_lp_claim_order_cannot_create_collateral(self):
        for model in MODELS:
            engine, checker, settled = low_tail_state(model)
            entitlements = {
                sponsor.sponsor_id: _claimable_residual_for_cohort(settled, sponsor)
                for sponsor in settled.sponsors.values()
            }
            actions = (
                ClaimWinnings(6, "winner", 1, D(500)),
                ClaimLpResidual(6, "creator"), ClaimLpResidual(6, "late"),
            )
            for ordering in permutations(actions):
                with self.subTest(model=model[0].__name__, ordering=[type(a).__name__ + str(getattr(a, "sponsor_id", "")) for a in ordering]):
                    state = deepcopy(settled)
                    for event in ordering:
                        cash_before = state.treasury.contract_funds
                        state = engine.apply_event(state, event)
                        if isinstance(event, ClaimLpResidual):
                            self.assertLess(abs(cash_before - state.treasury.contract_funds - entitlements[event.sponsor_id]), TOL)
                        self.assert_safe(checker, state)
                    self.assertLess(abs(_total_non_fee_assets(state)), TOL)
                    cash_before = state.treasury.contract_funds
                    for sponsor_id in entitlements:
                        state = engine.apply_event(state, ClaimLpResidual(7, sponsor_id))
                    self.assertLess(abs(cash_before - state.treasury.contract_funds), TOL)

    def test_refund_and_lp_claim_order_preserves_all_refunds(self):
        for model in MODELS:
            engine, checker, state = bootstrap(model)
            state = engine.apply_event(state, buy(2, "alice", 0, 80))
            state = engine.apply_event(state, buy(3, "bob", 1, 90))
            state = engine.apply_event(state, CancelMarket(4, "test"))
            entitlement = _claimable_residual_for_cohort(state, next(iter(state.sponsors.values())))
            for ordering in permutations((ClaimRefund(5, "alice", 0, D(80)), ClaimRefund(5, "bob", 1, D(90)), ClaimLpResidual(5, "creator"))):
                settled = deepcopy(state)
                for event in ordering:
                    before = settled.treasury.contract_funds
                    settled = engine.apply_event(settled, event)
                    if isinstance(event, ClaimLpResidual):
                        self.assertLess(abs(before - settled.treasury.contract_funds - entitlement), TOL)
                    self.assert_safe(checker, settled)
                self.assertLess(abs(_total_non_fee_assets(settled)), TOL)

    def test_long_randomized_paths_preserve_both_terminal_reserves(self):
        # These are long sequential state-machine histories, with rejection treated
        # as an observable outcome rather than silently shrinking an unsafe payout.
        for seed in range(4):
            rng = Random(seed + 9100)
            n = (3, 5, 8, 3)[seed]
            markets = [bootstrap(model, n=n, fees=(100, 25)) for model in MODELS]
            for t in range(2, 242):
                state = markets[0][2]
                if t in (40, 100, 180):
                    event = LpEnterActive(t, f"lp{t}", D(20), D("1e50"), state.pricing.price_vector, D("1e-14"))
                else:
                    holdings = [(trader, i, shares) for trader, vector in state.traders.positions_by_trader.items() for i, shares in enumerate(vector) if shares > 0]
                    if holdings and rng.random() < 0.55:
                        trader, outcome, held = rng.choice(holdings)
                        event = SellOutcome(t, trader, outcome, min(held, D(rng.choice((5, 20, 60, 120)))), D(0))
                    else:
                        event = buy(t, f"trader{rng.randrange(4)}", rng.randrange(n), rng.choice((5, 20, 60, 120)))
                accepted = []
                updated = []
                for engine, checker, current in markets:
                    before = deepcopy(current)
                    try:
                        current = engine.apply_event(current, event)
                        accepted.append(True)
                    except RefundReserveViolation:
                        accepted.append(False)
                        self.assertEqual(current, before)
                    self.assert_safe(checker, current)
                    self.assertGreaterEqual(refund_reserve_margin(current), -TOL)
                    updated.append((engine, checker, current))
                self.assertEqual(accepted[0], accepted[1], "reference and compressed model disagree on sell feasibility")
                self.assertLess(abs(_total_non_fee_assets(updated[0][2]) - _total_non_fee_assets(updated[1][2])), TOL)
                markets = updated
            for engine, checker, state in markets:
                for outcome in range(n):
                    resolved = engine.apply_event(state, ResolveMarket(250, outcome))
                    self.assert_safe(checker, resolved)
                self.assert_safe(checker, engine.apply_event(state, CancelMarket(250, "randomized")))


if __name__ == "__main__":
    unittest.main()
