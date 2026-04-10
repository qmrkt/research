from __future__ import annotations

from decimal import Decimal

from research.active_lp.precision import DECIMAL_ONE, DECIMAL_ZERO, high_precision, to_decimal


def sum_decimals(values: list[Decimal] | tuple[Decimal, ...]) -> Decimal:
    total = DECIMAL_ZERO
    for value in values:
        total += value
    return total


def max_abs_diff(left: tuple[Decimal, ...], right: tuple[Decimal, ...]) -> Decimal:
    if len(left) != len(right):
        raise ValueError("vector length mismatch")
    if not left:
        return DECIMAL_ZERO
    return max(abs(a - b) for a, b in zip(left, right))


def uniform_price_vector(num_outcomes: int) -> tuple[Decimal, ...]:
    if num_outcomes < 2:
        raise ValueError("num_outcomes must be at least 2")
    with high_precision():
        n = to_decimal(num_outcomes)
        base = DECIMAL_ONE / n
        prices = [base for _ in range(num_outcomes - 1)]
        prices.append(DECIMAL_ONE - sum_decimals(tuple(prices)))
        return tuple(prices)


def lmsr_cost(q: tuple[Decimal, ...], b: Decimal) -> Decimal:
    if b <= 0:
        raise ValueError("b must be positive")
    if not q:
        raise ValueError("q must be non-empty")
    with high_precision():
        exp_terms = [((qi / b)).exp() for qi in q]
        return b * sum_decimals(exp_terms).ln()


def lmsr_prices(q: tuple[Decimal, ...], b: Decimal) -> tuple[Decimal, ...]:
    if b <= 0:
        raise ValueError("b must be positive")
    if not q:
        raise ValueError("q must be non-empty")
    with high_precision():
        exp_terms = [((qi / b)).exp() for qi in q]
        total = sum_decimals(exp_terms)
        prices = [term / total for term in exp_terms]
        prices[-1] = DECIMAL_ONE - sum_decimals(tuple(prices[:-1]))
        return tuple(prices)


def lmsr_cost_delta(q: tuple[Decimal, ...], b: Decimal, outcome_index: int, shares: Decimal) -> Decimal:
    if shares <= 0:
        raise ValueError("shares must be positive")
    q_after = list(q)
    q_after[outcome_index] += shares
    with high_precision():
        return lmsr_cost(tuple(q_after), b) - lmsr_cost(q, b)


def lmsr_sell_return(q: tuple[Decimal, ...], b: Decimal, outcome_index: int, shares: Decimal) -> Decimal:
    if shares <= 0:
        raise ValueError("shares must be positive")
    q_after = list(q)
    q_after[outcome_index] -= shares
    with high_precision():
        return lmsr_cost(q, b) - lmsr_cost(tuple(q_after), b)


def normalized_q_from_prices(prices: tuple[Decimal, ...], b: Decimal) -> tuple[Decimal, ...]:
    if b <= 0:
        raise ValueError("b must be positive")
    if not prices:
        raise ValueError("prices must be non-empty")
    total = sum_decimals(prices)
    if abs(total - DECIMAL_ONE) > Decimal("1e-18"):
        raise ValueError("prices must sum to 1")
    if any(price <= 0 for price in prices):
        raise ValueError("prices must be strictly positive")
    with high_precision():
        return tuple(b * price.ln() for price in prices)


def gauge_alpha_from_prices(prices: tuple[Decimal, ...]) -> Decimal:
    if not prices:
        raise ValueError("prices must be non-empty")
    if any(price <= 0 for price in prices):
        raise ValueError("prices must be strictly positive")
    with high_precision():
        return max((DECIMAL_ONE / price).ln() for price in prices)


def collateral_required(delta_b: Decimal, prices: tuple[Decimal, ...]) -> Decimal:
    if delta_b <= 0:
        raise ValueError("delta_b must be positive")
    with high_precision():
        return delta_b * gauge_alpha_from_prices(prices)
