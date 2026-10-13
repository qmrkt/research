"""Controls for the synthetic information intervention and decision policies."""

from dataclasses import replace
from decimal import Decimal
import unittest

from research.active_lp.information_timing import TimingRegime, effect_row, evaluate_regime
from research.active_lp.information_frontier import allocation_rows, founder_cash
from research.active_lp.reference_math import lmsr_cost


class InformationTimingTests(unittest.TestCase):
    def test_uninformative_channels_have_zero_information_value(self):
        base = TimingRegime("control", pre_shares=40, future_shares=160, flow_accuracy=.4)
        for target, accuracy in (("outcome", 1 / 3), ("flow_alignment", .5)):
            for rule in ("flat", "normalized", "isolated_cohort"):
                summaries, raw = evaluate_regime(replace(base, signal_accuracy=accuracy), rule, .15, target)
                self.assertAlmostEqual(sum(r["probability"] for r in raw), 1.0, places=12)
                self.assertAlmostEqual(effect_row(summaries)["private_information_value"], 0.0, places=12)

    def test_signal_changes_information_not_entry_price_or_collateral(self):
        regime = TimingRegime("paired", flow_accuracy=.4, signal_accuracy=.9)
        summaries, raw = evaluate_regime(regime, "flat", 0.0, "flow_alignment")
        # These quantities must be fixed even across different signal realizations.
        self.assertEqual(len({r["late_deposit"] for r in raw}), 1)
        self.assertEqual(len({r["late_entry_prices"] for r in raw}), 1)
        by_world = {}
        for row in raw:
            key = row["winner"], row["future_flow_direction"]
            by_world.setdefault(key, set()).add(row["late_net_profit"])
            if not row["late_private_optional_enter"]:
                self.assertEqual(row["late_private_optional_net_profit"], 0.0)
                self.assertEqual(row["late_private_optional_offered_return"], 0.0)
        self.assertTrue(all(len(payoffs) == 1 for payoffs in by_world.values()))
        self.assertGreaterEqual(effect_row(summaries)["private_information_value"], -1e-12)

    def test_more_accurate_alignment_signal_does_not_reduce_option_value(self):
        base = TimingRegime("quality", pre_shares=10, future_shares=240, flow_accuracy=.5)
        values = [effect_row(evaluate_regime(replace(base, signal_accuracy=q), "flat", 0.0, "flow_alignment")[0])["private_information_value"]
                  for q in (.5, .6, .8, .95, 1.0)]
        self.assertTrue(all(b >= a - 1e-12 for a, b in zip(values, values[1:])), values)
        self.assertGreater(values[-1], 0.0, "Sign-crossing intervention should have strict value")

    def test_zero_lambda_matches_flat_and_isolated_no_flow_has_no_value(self):
        regime = TimingRegime("identity", flow_accuracy=.4)
        flat, _ = evaluate_regime(regime, "flat", 0.0, "flow_alignment")
        normalized, _ = evaluate_regime(regime, "normalized", 0.0, "flow_alignment")
        for a, b in zip(flat, normalized):
            self.assertAlmostEqual(a["mean_return_per_offered_capital"], b["mean_return_per_offered_capital"], places=12)
        no_flow = replace(regime, future_shares=0)
        isolated, _ = evaluate_regime(no_flow, "isolated_cohort", 0.0, "flow_alignment")
        self.assertAlmostEqual(effect_row(isolated)["private_information_value"], 0.0, places=12)

    def test_declined_offer_preserves_actual_founder_economics(self):
        # With no entrant, one sponsor earns the full LMSR cash surplus and LP
        # fees. This independent closed-form check excludes fee protocol income.
        q = (Decimal(40), Decimal(80), Decimal(0))
        gross = lmsr_cost(q, Decimal(100)) - lmsr_cost((Decimal(0),)*3, Decimal(100))
        cash = founder_cash(40, 80, 100, 0, 30, "normalized", .15, 1, 1, False)
        expected_profit = gross * Decimal("1.01") - Decimal(80)
        self.assertAlmostEqual(cash["founder_cash_profit"], float(expected_profit), places=10)
        self.assertNotIn("entrant_deposit", cash)
        regime = TimingRegime("decline")
        rows, raw, _ = allocation_rows(regime, "flat", 0.0)
        public = next(r for r in rows if r["policy"] == "late_public_optional")
        self.assertEqual(public["entry_rate"], 0.0)
        self.assertEqual(public["entrant_offered_return"], 0.0)
        self.assertIsNone(public["founder_conditional_return"])
        self.assertNotEqual(public["founder_unconditional_return"], 0.0)
        self.assertTrue(any(r["late_public_optional_founder_net_profit"] != 0 for r in raw))


if __name__ == "__main__":
    unittest.main()
