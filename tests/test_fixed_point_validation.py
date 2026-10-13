"""Smoke the paired final-policy artifact generator without a publication run."""

from decimal import Decimal as D
import unittest

from research.active_lp.fixed_point_validation import run_path
from research.active_lp.publication_validation import History
from research.active_lp.precision import high_precision
from research.active_lp.reference_math import uniform_price_vector


class FixedPointValidationTests(unittest.TestCase):
    def test_all_terminal_branches_pay_and_retain_paired_requests(self):
        history = History(
            "unit_path", "unit_path", "unit", None, 3, D(100), D(100), D(25),
            uniform_price_vector(3),
            [{"kind": "buy", "timestamp": 2, "actor": "alice", "outcome": 0, "amount": D(30)},
             {"kind": "lp", "timestamp": 3, "actor": "late", "amount": D(20)},
             {"kind": "buy", "timestamp": 4, "actor": "bob", "outcome": 1, "amount": D(20)}],
            0, 5,
        )
        with high_precision():
            row, requests, rejections, terminal, cohorts = run_path(history, "floor")
        self.assertTrue(row["all_terminal_claims_paid"])
        self.assertEqual(row["acceptance_disagreements"], 0)
        self.assertEqual(len(requests), 3)
        self.assertEqual(len(terminal), 12)
        self.assertEqual(len(cohorts), 24)
        self.assertEqual(rejections, [])
        self.assertEqual({value["outcome"] for value in terminal}, {None, 0, 1, 2})
        self.assertTrue(all(value["all_claims_paid"] for value in terminal))


if __name__ == "__main__":
    unittest.main()
