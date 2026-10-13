"""Terminal Decimal residue must never spend non-fee collateral."""

from copy import deepcopy
from dataclasses import replace
from decimal import Decimal as D
import unittest

from research.active_lp.candidate_global_state import CandidateGlobalStateEngine, create_candidate_initial_state
from research.active_lp.events import BootstrapMarket, WithdrawLpFees
from research.active_lp.precision import high_precision
from research.active_lp.reference_parallel_lmsr import ReferenceParallelLmsrEngine, _total_non_fee_assets, create_initial_state


class DecimalFeeReconciliationTests(unittest.TestCase):
    def markets(self, fee_assets, nominal_claim):
        for engine_type, factory in ((ReferenceParallelLmsrEngine, create_initial_state), (CandidateGlobalStateEngine, create_candidate_initial_state)):
            engine = engine_type()
            state = engine.apply_event(factory(3), BootstrapMarket(1, "creator", D(150), D(100)))
            state.treasury.lp_fee_balance = fee_assets
            state.treasury.contract_funds += fee_assets
            key = next(iter(state.sponsors))
            state.sponsors[key] = replace(state.sponsors[key], withdrawable_fee_surplus=nominal_claim)
            yield engine, state, key

    def test_sub_tolerance_excess_is_discharged_without_spending_reserves(self):
        with high_precision():
            for engine, state, key in self.markets(D(1) - D("1e-25"), D(1)):
                assets = _total_non_fee_assets(state)
                funds = state.treasury.contract_funds
                after = engine.apply_event(state, WithdrawLpFees(2, "creator", D(1)))
                self.assertEqual(funds - after.treasury.contract_funds, D(1) - D("1e-25"))
                self.assertEqual(after.treasury.lp_fee_balance, 0)
                self.assertEqual(after.sponsors[key].withdrawable_fee_surplus, 0)
                self.assertEqual(_total_non_fee_assets(after), assets)

    def test_sub_tolerance_request_above_nominal_claim_is_capped(self):
        with high_precision():
            for engine, state, key in self.markets(D(1), D(1) - D("1e-25")):
                assets = _total_non_fee_assets(state)
                after = engine.apply_event(state, WithdrawLpFees(2, "creator", D(1)))
                self.assertEqual(after.treasury.lp_fee_balance, D("1e-25"))
                self.assertEqual(after.sponsors[key].withdrawable_fee_surplus, 0)
                self.assertEqual(_total_non_fee_assets(after), assets)

    def test_real_underfunding_remains_atomic_rejection(self):
        with high_precision():
            for fee_assets, nominal in ((D(1) - D("1e-6"), D(1)), (D(1), D(1) - D("1e-6"))):
                for engine, state, _ in self.markets(fee_assets, nominal):
                    before = deepcopy(state)
                    with self.assertRaises(ValueError):
                        engine.apply_event(state, WithdrawLpFees(2, "creator", D(1)))
                    self.assertEqual(state, before)


if __name__ == "__main__":
    unittest.main()
