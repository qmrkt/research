"""Metamorphic tests for time premiums on a fixed terminal cash-flow history.

These test the signed last-minus-first NAV/deposit gap, not an information
option, an adaptive strategy, or a guarantee of decreasing absolute gaps.
"""
from copy import deepcopy
from decimal import Decimal as D
import unittest

from research.active_lp.candidate_global_state import (
    CandidateGlobalStateEngine, CandidateInvariantChecker, create_candidate_initial_state,
)
from research.active_lp.events import (
    BootstrapMarket, BuyOutcome, CancelMarket, ClaimLpFees, LpEnterActive, ResolveMarket,
)
from research.active_lp.precision import high_precision
from research.active_lp.reference_math import collateral_required, uniform_price_vector
from research.active_lp.reference_parallel_lmsr import (
    RESERVE_POOL, ReferenceParallelLmsrEngine, ReferenceInvariantChecker,
    _total_non_fee_assets, _winner_reserve_requirement, create_initial_state,
)

MODELS = (
    (ReferenceParallelLmsrEngine, ReferenceInvariantChecker, create_initial_state),
    (CandidateGlobalStateEngine, CandidateInvariantChecker, create_candidate_initial_state),
)
LAMBDAS = tuple(map(D, ("0", ".003636166087", ".139227125962", ".15", "1", "100")))
TOL = D("1e-16")


def active_history(model, *, positive_gap):
    engine_type, checker_type, initial_state = model
    engine = engine_type(
        lp_fee_bps=200, protocol_fee_bps=25, residual_policy=RESERVE_POOL,
        residual_weight_scheme="linear_lambda_normalized", residual_linear_lambda=0,
    )
    state = initial_state(3, residual_weight_scheme="linear_lambda_normalized", residual_linear_lambda=0)
    buffer = D(20) if positive_gap else D(0)
    shares = D(12) if positive_gap else D(120)
    state = engine.apply_event(state, BootstrapMarket(
        1, "creator", collateral_required(D(100), uniform_price_vector(3)) + buffer, D(100),
    ))
    state = engine.apply_event(state, BuyOutcome(2, "alice", 0, shares, D("1e20")))
    state = engine.apply_event(state, LpEnterActive(4, "middle", D(30), D("1e20"), state.pricing.price_vector, TOL))
    state = engine.apply_event(state, BuyOutcome(6, "bob", 1, D(8), D("1e20")))
    state = engine.apply_event(state, LpEnterActive(9, "last", D(20), D("1e20"), state.pricing.price_vector, TOL))
    state = engine.apply_event(state, BuyOutcome(10, "carol", 2, D(5), D("1e20")))
    # Claiming fees changes which field contains the same cash entitlement.
    # NAV must include both fields; it must not treat a claimed fee as lost.
    state = engine.apply_event(state, ClaimLpFees(11, "creator"))
    return engine, checker_type(residual_policy=RESERVE_POOL), state


class ResidualWeightingTests(unittest.TestCase):
    def test_larger_normalized_premium_reduces_signed_gap_on_fixed_terminal_paths(self):
        for model in MODELS:
            for positive_gap in (True, False):
                for terminal in (ResolveMarket(13, 0), CancelMarket(13, "metamorphic")):
                    with self.subTest(model=model[0].__name__, positive_gap=positive_gap, terminal=type(terminal).__name__), high_precision():
                        engine, checker, active = active_history(model, positive_gap=positive_gap)
                        original = deepcopy(active)
                        ordered = sorted(active.sponsors, key=lambda key: active.sponsors[key].entry_timestamp)
                        earliest, latest = ordered[0], ordered[-1]
                        self.assertEqual(active.sponsors[earliest].claimable_fees, 0)
                        self.assertGreater(active.sponsors[earliest].withdrawable_fee_surplus, 0)
                        self.assertGreater(active.sponsors[latest].claimable_fees, 0)
                        fees = {key: sponsor.claimable_fees + sponsor.withdrawable_fee_surplus for key, sponsor in active.sponsors.items()}
                        gaps, baseline_finances = [], None
                        for value in LAMBDAS:
                            counterfactual = deepcopy(active)
                            counterfactual.residual_linear_lambda = value
                            settled = engine.apply_event(counterfactual, terminal)
                            nav = engine.mark_to_market_nav(settled)
                            gap = nav[latest] / settled.sponsors[latest].collateral_posted - nav[earliest] / settled.sponsors[earliest].collateral_posted
                            gaps.append(gap)
                            reserve = _winner_reserve_requirement(settled)
                            free = _total_non_fee_assets(settled) - reserve
                            self.assertGreater(free, 0)
                            self.assertLess(abs(sum(nav.values(), D(0)) - free - sum(fees.values(), D(0))), TOL)
                            self.assertTrue(all(nav[key] >= fees[key] - TOL for key in nav))
                            self.assertEqual([check for check in checker.check_all(settled) if not check.passed], [])
                            finances = (settled.treasury, settled.traders, settled.pricing, reserve, fees)
                            if baseline_finances is None:
                                baseline_finances = deepcopy(finances)
                            else:
                                self.assertEqual(finances, baseline_finances, "lambda changed trade cash, fee rights, prices or trader reserves")
                        self.assertEqual(active, original, "counterfactual settlement mutated the source history")
                        self.assertTrue(all(after < before for before, after in zip(gaps, gaps[1:])))
                        if positive_gap:
                            self.assertGreater(gaps[0], 0)
                            self.assertGreater(gaps[3], 0)
                            self.assertLess(abs(gaps[3]), abs(gaps[0]), "a small premium did not reduce this positive gap")
                            self.assertLess(gaps[-1], 0)
                            self.assertGreater(abs(gaps[-1]), abs(gaps[0]), "large premium should expose overcorrection")
                        else:
                            self.assertLess(gaps[0], 0)
                            self.assertTrue(all(abs(after) > abs(before) for before, after in zip(gaps, gaps[1:])), "signed-gap monotonicity is not absolute-gap improvement")

    def test_one_unit_terminal_span_has_zero_exposure_for_all_cohorts(self):
        for model in MODELS:
            with self.subTest(model=model[0].__name__), high_precision():
                engine_type, _, initial_state = model
                engine = engine_type(residual_policy=RESERVE_POOL, residual_weight_scheme="linear_lambda_normalized")
                state = initial_state(3, residual_weight_scheme="linear_lambda_normalized")
                state = engine.apply_event(state, BootstrapMarket(1, "creator", collateral_required(D(100), uniform_price_vector(3)) + D(20), D(100)))
                state = engine.apply_event(state, LpEnterActive(2, "last", D(20), D("1e20"), state.pricing.price_vector, TOL))
                expected = None
                for value in LAMBDAS:
                    counterfactual = deepcopy(state)
                    counterfactual.residual_linear_lambda = value
                    settled = engine.apply_event(counterfactual, ResolveMarket(2, 0))
                    nav = engine.mark_to_market_nav(settled)
                    if expected is None:
                        expected = nav
                    else:
                        self.assertEqual(nav, expected, "clamped zero exposures must eliminate lambda dependence")


if __name__ == "__main__":
    unittest.main()
