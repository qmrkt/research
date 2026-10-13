"""Tests for cached terminal accounting and train-only historical selection."""
import unittest
from decimal import Decimal as D

from research.active_lp import historical_calibration as hc
from research.active_lp import publication_validation as pv
from research.active_lp.precision import high_precision


class HistoricalCalibrationTests(unittest.TestCase):
    def test_coefficients_match_direct_weight_allocation(self):
        history = pv.generate_history(31000)
        with high_precision():
            state, audit, _ = pv.run_history(history, "fixed_20")
            row = hc.snapshot(history, "fixed_20", state, audit, {"split": "train"})
            for scheme, policy, value in (("event", "flat", D(0)), ("normalized", "normalized_015", D(".15"))):
                expected, _ = pv.measure(history, "fixed_20", state, audit, policy=policy)
                observed = hc.gap_from_coefficients(hc.coefficients(row, scheme), value)
                self.assertLess(abs(observed - expected["gap"]), D("1e-12"))

    def test_cache_reuse_matches_replay_of_clock_restamps(self):
        histories = hc.historical_pack("train", trials=1, adversarial_limit=0)
        with high_precision():
            first, metadata = histories[0]
            state, audit, _ = pv.run_history(first, "fixed_20")
            for history, metadata in histories:
                self.assertEqual(hc.economic_key(first, "fixed_20"), hc.economic_key(history, "fixed_20"))
                direct, direct_audit, _ = pv.run_history(history, "fixed_20")
                cached = hc.snapshot(history, "fixed_20", state, audit, metadata)
                replayed = hc.snapshot(history, "fixed_20", direct, direct_audit, metadata)
                self.assertEqual(pv.canonical(cached), pv.canonical(replayed))

    def test_continuous_selection_finds_train_root_and_rejects_test(self):
        history = pv.stress_histories()[0]
        with high_precision():
            state, audit, _ = pv.run_history(history, "fixed_20")
            row = hc.snapshot(history, "fixed_20", state, audit, {"split": "train"})
            for scheme in ("event", "normalized"):
                value, trace = hc.select_lambda([row], scheme)
                self.assertGreater(value, 0)
                self.assertLess(abs(hc.gap_from_coefficients(hc.coefficients(row, scheme), value)), D("1e-15"))
                self.assertEqual(trace[-1]["phase"], "selected")
            with self.assertRaises(ValueError):
                hc.select_lambda([dict(row, split="test")], "event")
            with self.assertRaises(ValueError):
                hc.select_lambda([dict(row, funding="floor")], "event")

    def test_original_pack_sizes_and_related_adversarial_ids(self):
        train, test = hc.historical_pack("train"), hc.historical_pack("test")
        self.assertEqual(len(train), 288)
        self.assertEqual(len(test), 288)
        self.assertEqual(len({h.cluster_id for h, _ in train}), 160)
        self.assertEqual(len({h.cluster_id for h, _ in test}), 160)
        self.assertEqual({h.cluster_id for h, m in train if m["family"] == "adversarial"}, {h.cluster_id for h, m in test if m["family"] == "adversarial"})
        self.assertTrue({h.cluster_id for h, m in train if m["family"] == "monte_carlo"}.isdisjoint({h.cluster_id for h, m in test if m["family"] == "monte_carlo"}))


if __name__ == "__main__":
    unittest.main()
