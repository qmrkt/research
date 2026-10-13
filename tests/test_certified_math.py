"""Independent high-precision oracle and economic metamorphisms for intervals."""
from decimal import Decimal as D
from random import Random
import unittest

from research.active_lp import certified_math as cm
from research.active_lp.precision import high_precision
from research.active_lp.reference_math import lmsr_cost_delta, lmsr_sell_return


class CertifiedMathTests(unittest.TestCase):
    def check_quote(self, q, b, outcome, shares, *, sell=False):
        interval_fn = cm.certified_lmsr_sell_return_interval if sell else cm.certified_lmsr_cost_delta_interval
        quote_fn = cm.certified_lmsr_sell_return if sell else cm.certified_lmsr_cost_delta
        exact_fn = lmsr_sell_return if sell else lmsr_cost_delta
        bounds = interval_fn(q, b, outcome, shares)
        quote = quote_fn(q, b, outcome, shares)
        with high_precision():
            exact = exact_fn(tuple(map(D, q)), D(b), outcome, D(shares))
            lower, upper = D(bounds.lower) / D(bounds.scale), D(bounds.upper) / D(bounds.scale)
            self.assertLessEqual(lower, exact)
            self.assertGreaterEqual(upper, exact)
            self.assertLess(upper - lower, D(1))
            self.assertGreaterEqual(quote, 0)
            self.assertLessEqual(quote, shares)
            if sell:
                self.assertLessEqual(D(quote), exact)
                self.assertLess(exact - D(quote), D(1) + upper - lower)
            else:
                self.assertGreaterEqual(D(quote), exact)
                self.assertLess(D(quote) - exact, D(1) + upper - lower)
        return bounds, quote

    def test_high_skew_tiny_sell_cannot_receive_hundredfold_overpayment(self):
        q, b = [1_000_000_000, 0, 0], 100_000_000
        bounds, quote = self.check_quote(q, b, 0, 1, sell=True)
        self.assertEqual(quote, 0)
        with high_precision():
            self.assertGreater(D(bounds.lower) / bounds.scale, D(".9999"))
            self.assertLess(D(bounds.upper) / bounds.scale, D(1))
        _, whole_token_quote = self.check_quote(q, b, 0, 1_000_000, sell=True)
        self.assertLess(whole_token_quote, 999_910)
        self.assertGreater(whole_token_quote, 999_900)

    def test_certificates_cover_decimal_oracle_across_outcomes_scales_and_domain_edges(self):
        rng = Random(63000)
        for n in (2, 3, 8, 64):
            for b in (1, 100_000_000, 1_000_000_000_000, cm.UINT64_MAX // 8):
                for case in range(3):
                    q = [rng.randrange(0, 4 * b + 1) for _ in range(n)]
                    outcome = rng.randrange(n)
                    shares = min((1, max(1, b // 100), b)[case], cm.UINT64_MAX - q[outcome])
                    with self.subTest(n=n, b=b, case=case):
                        self.check_quote(q, b, outcome, shares)
                        after = q.copy()
                        after[outcome] += shares
                        self.check_quote(after, b, outcome, shares, sell=True)
        for n in (3, 8, 64):
            b = 100_000_000
            q = [64 * b] + [0] * (n - 1)
            self.check_quote(q, b, 0, 1, sell=True)
            self.check_quote(q, b, n - 1, 1)
            self.check_quote([0] * n, b, 0, 64 * b)

    def test_closed_inventory_paths_cannot_profit_from_rounding(self):
        rng = Random(64000)
        for n in (3, 8, 64):
            q = [0] * n
            b, cash_out, trades = 100_000_000, 0, []
            for _ in range(24):
                outcome = rng.randrange(n)
                shares = rng.choice((1, 7, 1_000_000, 100_000_000))
                cash_out += cm.certified_lmsr_cost_delta(q, b, outcome, shares)
                q[outcome] += shares
                trades.append((outcome, shares))
            for outcome, shares in reversed(trades):
                cash_out -= cm.certified_lmsr_sell_return(q, b, outcome, shares)
                q[outcome] -= shares
            self.assertEqual(q, [0] * n)
            self.assertGreaterEqual(cash_out, 0)
            self.assertLessEqual(cash_out, 2 * len(trades), "rounding friction exceeds two raw units per round trip")

    def test_gauge_shift_and_integer_unit_rescaling_preserve_certificates(self):
        q, b, outcome, shares = [23_000_000, 45_000_000, 9_000_000], 100_000_000, 1, 123_456
        original = cm.certified_lmsr_cost_delta_interval(q, b, outcome, shares)
        shifted = cm.certified_lmsr_cost_delta_interval([v + 1_000_000_000 for v in q], b, outcome, shares)
        scaled = cm.certified_lmsr_cost_delta_interval([v * 7 for v in q], b * 7, outcome, shares * 7)
        self.assertEqual(original, shifted)
        self.assertEqual(scaled.lower, original.lower * 7)
        self.assertEqual(scaled.upper, original.upper * 7)

    def test_zero_routed_amount_and_explicit_domain_rejection(self):
        self.assertEqual(cm.certified_lmsr_cost_delta([0, 0, 0], 1, 0, 0), 0)
        self.assertEqual(cm.certified_lmsr_sell_return([0, 0, 0], 1, 0, 0), 0)
        invalid = [([0], 1, 0, 1), ([0, 0], 0, 0, 1), ([0, 0], 1, 0, 65), ([0, 65], 1, 0, 1), ([0, 0], 1, 2, 1), ([cm.UINT64_MAX, cm.UINT64_MAX], 1, 0, 1), ([0.0, 0], 1, 0, 1)]
        for args in invalid:
            with self.subTest(args=args), self.assertRaises(cm.CertificationDomainError):
                cm.certified_lmsr_cost_delta(*args)
        with self.assertRaises(cm.CertificationDomainError):
            cm.certified_lmsr_sell_return([0, 0], 1, 0, 1)


if __name__ == "__main__":
    unittest.main()
