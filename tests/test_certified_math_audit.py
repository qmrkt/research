"""Audit the numerical enclosure primitives independently of LMSR composition."""
from decimal import Decimal as D, localcontext
from fractions import Fraction as F
import unittest

from research.active_lp import certified_math as cm


def rational_exp_inverse_bounds(x, terms):
    """Direct exact-rational positive exp series, without range reduction."""
    term = total = F(1)
    for degree in range(1, terms + 1):
        term *= x / degree
        total += term
    first = term * x / (terms + 1)
    ratio = x / (terms + 2)
    assert ratio < 1
    return 1 / (total + first / (1 - ratio)), 1 / total


class CertifiedMathAuditTests(unittest.TestCase):
    def test_exp_interval_contains_independent_exact_rational_bracket(self):
        for numerator, denominator, terms in ((0, 1, 64), (1, cm.UINT64_MAX, 16), (1, 2, 64), (1, 1, 128), (2, 1, 128), (64, 1, 512)):
            with self.subTest(numerator=numerator, denominator=denominator):
                low, high = rational_exp_inverse_bounds(F(numerator, denominator), terms)
                interval = cm._exp_negative_interval(numerator, denominator)
                self.assertLessEqual(F(interval.lower, interval.scale), low)
                self.assertGreaterEqual(F(interval.upper, interval.scale), high)

    def test_log_enclosures_at_every_power_of_two_reduction_boundary(self):
        with localcontext() as context:
            context.prec = 160
            for power in range(7):
                for offset in (-1, 0, 1):
                    scaled = (cm.SCALE << power) + offset
                    if scaled < cm.SCALE:
                        continue
                    with self.subTest(power=power, offset=offset):
                        exact = (D(scaled) / D(cm.SCALE)).ln()
                        interval = cm._log_integer_scaled_interval(scaled)
                        self.assertLessEqual(D(interval.lower) / interval.scale, exact)
                        self.assertGreaterEqual(D(interval.upper) / interval.scale, exact)
            self.assertEqual(cm._log_integer_scaled_interval(cm.SCALE), cm.FixedInterval(0, 0))

    def test_exact_integral_cost_ties_remain_conservative_not_correctly_rounded(self):
        # q=(0,2), then buying 2 of outcome0 gives (2,2). This is not
        # an integral tie, so use the swapped two-outcome endpoints instead:
        # q=(0,2), buy 4 outcome0 -> (4,2)=2+(2,0). Symmetry gives cost=2.
        q, b, amount = [0, 2], 100, 4
        buy = cm.certified_lmsr_cost_delta_interval(q, b, 0, amount)
        sell = cm.certified_lmsr_sell_return_interval([4, 2], b, 0, amount)
        self.assertLessEqual(buy.lower, 2 * cm.SCALE)
        self.assertGreaterEqual(buy.upper, 2 * cm.SCALE)
        self.assertLessEqual(sell.lower, 2 * cm.SCALE)
        self.assertGreaterEqual(sell.upper, 2 * cm.SCALE)
        paid = cm.certified_lmsr_cost_delta(q, b, 0, amount)
        received = cm.certified_lmsr_sell_return([4, 2], b, 0, amount)
        self.assertGreaterEqual(paid, 2)
        self.assertLessEqual(received, 2)
        self.assertLessEqual(paid - received, 2)


if __name__ == "__main__":
    unittest.main()
