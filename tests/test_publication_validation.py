"""Economic and statistical checks for the publication diagnostic suite."""
import unittest
from decimal import Decimal as D

from research.active_lp.precision import high_precision
from research.active_lp import publication_validation as pv
from research.active_lp import reference_parallel_lmsr as ref
from research.active_lp.events import ResolveMarket


class PublicationValidationTests(unittest.TestCase):
    def test_zero_flow_excess_capital_transfer_and_isolated_accounts(self):
        history = pv.stress_histories()[0]
        with high_precision():
            for funding in pv.FUNDING:
                state, audit, rejected = pv.run_history(history, funding)
                self.assertEqual(rejected, [])
                isolated, cohort_rows = pv.measure(history, funding, state, audit, policy="capital_accounts")
                self.assertAlmostEqual(float(isolated["gap"]), 0.0, places=12)
                for row in cohort_rows:
                    self.assertAlmostEqual(float(row["nav_per_deposit"]), 1.0, places=12)
                flat, _ = pv.measure(history, funding, state, audit, policy="flat")
                if funding == "floor":
                    self.assertAlmostEqual(float(flat["gap"]), 0.0, places=12)
                else:
                    self.assertGreater(flat["gap"], D(".1"))
            state, audit, _ = pv.run_history(history, "fixed_20")
            flat, _ = pv.measure(history, "fixed_20", state, audit, policy="flat")
            self.assertAlmostEqual(float(flat["gap"]), 0.1773749637, places=9)

    def test_allocation_matches_engine_and_conserves_all_outcome_residuals(self):
        history = pv.generate_history(31000)
        with high_precision():
            state, audit, _ = pv.run_history(history, "fixed_20")
            for outcome in range(history.outcomes):
                available = pv.nonfee_assets(state) - D(state.traders.aggregate_outstanding_claims[outcome])
                for policy in pv.POLICIES:
                    allocation = pv.allocations(state, policy, outcome, history.settlement_time)
                    self.assertLess(abs(sum(allocation.values(), D(0)) - available), D("1e-10"))
                    self.assertGreaterEqual(min(allocation.values()), D("-1e-12"))
                for policy, scheme in (("flat", "flat"), ("normalized_015", "linear_lambda_normalized")):
                    engine = ref.ReferenceParallelLmsrEngine(residual_policy=ref.RESERVE_POOL, residual_weight_scheme=scheme, residual_linear_lambda=D(".15"))
                    settled = engine.apply_event(state, ResolveMarket(history.settlement_time, outcome))
                    settled.residual_weight_scheme = scheme
                    settled.residual_linear_lambda = D(".15")
                    engine_nav = engine.mark_to_market_nav(settled)
                    allocation = pv.allocations(state, policy, outcome, history.settlement_time)
                    for key, sponsor in state.sponsors.items():
                        expected = allocation[key] + D(sponsor.claimable_fees) + D(sponsor.withdrawable_fee_surplus)
                        self.assertLess(abs(engine_nav[key] - expected), D("1e-10"))

    def test_rejected_sell_preserves_request_and_records_opportunity(self):
        history = pv.stress_histories()[-1]
        with high_precision():
            state, audit, rejected = pv.run_history(history, "fixed_20")
            self.assertEqual(len(history.steps), 6)
            self.assertEqual(audit["requested_trades"], 6)
            self.assertEqual(audit["requested_sells"], 2)
            self.assertEqual(audit["rejected_sells"], 1)
            self.assertGreater(rejected[0]["quoted_net_proceeds"], 0)
            self.assertGreater(rejected[0]["shortfall"], 0)
            self.assertGreaterEqual(pv.nonfee_assets(state), pv.refund_requirement(state))
            row, _ = pv.measure(history, "fixed_20", state, audit, policy="flat")
            self.assertEqual(row["winner"], None)
            self.assertRaises(ValueError, pv.allocations, state, "capital_accounts", None, history.settlement_time)

    def test_cluster_bootstrap_does_not_count_restamps_as_new_samples(self):
        original = [{"cluster_id": "a", "gap": -0.3}, {"cluster_id": "b", "gap": 0.2}, {"cluster_id": "c", "gap": 0.4}]
        restamped = [dict(row, variant=index) for row in original for index in range(3)]
        first = pv.clustered_summary(original, "gap", resamples=100, seed=123)
        second = pv.clustered_summary(restamped, "gap", resamples=100, seed=123)
        self.assertEqual(second["n_rows"], 9)
        self.assertEqual(second["n_independent_clusters"], 3)
        self.assertEqual(first["mean"], second["mean"])
        self.assertEqual(first["ci95"], second["ci95"])

    def test_generator_is_repeatable_long_and_uses_independent_history_ids(self):
        first = pv.generate_history(31001)
        second = pv.generate_history(31001)
        third = pv.generate_history(31002)
        self.assertEqual(pv.canonical(pv.asdict(first)), pv.canonical(pv.asdict(second)))
        self.assertNotEqual(first.cluster_id, third.cluster_id)
        trades = [step for step in first.steps if step["kind"] in ("buy", "sell")]
        self.assertGreaterEqual(len(trades), 40)
        self.assertLessEqual(len(trades), 100)
        self.assertGreater(first.settlement_time, first.steps[-1]["timestamp"])
        self.assertAlmostEqual(float(sum(first.true_probabilities)), 1.0)

    def test_adaptive_actor_chooses_from_observed_candidate_objectives(self):
        history = pv.stress_histories()[0]
        with high_precision():
            rows, decisions = pv.run_adaptive(history, "fixed_20", "flat")
            self.assertEqual(len(rows), history.outcomes)
            self.assertTrue(any(d["chosen_actions"] for d in decisions))
            for decision in decisions:
                best = max(D(c["expected_profit"]) for c in decision["candidates"] if "expected_profit" in c)
                self.assertLess(abs(best - decision["chosen_expected_profit"]), D("1e-10"))
                self.assertGreaterEqual(decision["gain_over_wait"], 0)
            # A zero-flow uniform-prior case offers a subsidy-sharing LP entry,
            # without any event information or trading edge.
            self.assertGreater(rows[0]["expected_profit"], 0)


if __name__ == "__main__":
    unittest.main()
