"""Conservative integer LMSR quotes from finite, directed intervals.

All inputs and outputs use the same integer token unit (normally one microtoken).
The critical path uses Python integers only: no float, Decimal, external helper,
or empirically fitted error margin. This is a reference algorithm, not compiled
AVM code or a claim about on-chain resource budgets.

Domain: 2..64 outcomes; uint64 inventories, depth and trade size; positive depth;
resulting inventories still uint64; inventory spread and trade size at most 64*b.
An unsupported domain or an insufficiently narrow certificate raises explicitly.

Certificate construction
------------------------
Let Q=2**128. A FixedInterval [L,U] means L/Q <= value <= U/Q.
Every division rounds the lower endpoint down and the upper endpoint up.

For x >= 0, reduce z=x/2**s <= 1/2. Bound exp(z) by its positive Taylor
polynomial through degree 64. After the first omitted term the ratio of
successive terms is <= 1/2, so twice that term bounds the complete tail.
Invert the endpoints to bound exp(-z), then square s times with directed
rounding to bound exp(-x). Zero is handled exactly.

For v >= 1, write v=2**k*m, 1<=m<2. With z=(m-1)/(m+1) in [0,1/3),
log(m)=2*sum_{j>=0} z**(2*j+1)/(2*j+1). After M=64 terms the tail is at most
2*z**(2*M+1)/((2*M+1)*(1-z*z)) <= 9*z**(2*M+1)/(4*(2*M+1)).
The same formula at z=1/3 bounds log(2). All terms and tails are bounded using
integer intervals; monotonicity then bounds log of an interval by its endpoints.

For each inventory vector evaluate
    C(q) = max(q) + b*log(sum_i exp((q_i-max(q))/b)).
Subtract endpoint intervals in the conservative order. Intersect the difference
with the independently known [0, shares] range: each LMSR marginal price is in
[0,1]. Require interval width < one integer token unit. Charge ceil(upper) for
a buy and pay floor(lower) for a sell. Thus each accepted buy costs at least the
exact LMSR increment and each sell pays at most the exact decrement. Summing
these inequalities over a closed inventory path gives nonnegative trader cost;
rounding alone cannot create profit. This does not rule out information profits,
price-moving external flow, LP transfers, or other economic attacks.
"""
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from typing import Sequence

FRACTION_BITS = 128
SCALE = 1 << FRACTION_BITS
UINT64_MAX = (1 << 64) - 1
MAX_OUTCOMES = 64
MAX_NORMALIZED_SPREAD = 64
EXP_TERMS = 64
LOG_TERMS = 64


class CertificationDomainError(ValueError):
    """The requested quote is outside this algorithm's declared domain."""


class CertificationPrecisionError(ArithmeticError):
    """The interval certificate cannot resolve the requested precision."""


@dataclass(frozen=True, slots=True)
class FixedInterval:
    """Endpoints are numerators over ``scale``, in raw integer token units."""
    lower: int
    upper: int
    scale: int = SCALE

    def __post_init__(self) -> None:
        if self.scale <= 0 or self.lower > self.upper:
            raise ValueError("invalid interval")

    @property
    def width_numerator(self) -> int:
        return self.upper - self.lower

    def floor_lower(self) -> int:
        return self.lower // self.scale

    def ceil_upper(self) -> int:
        return _ceil_div(self.upper, self.scale)


def _ceil_div(numerator: int, denominator: int) -> int:
    return -((-numerator) // denominator)


def _uint64(name: str, value: int, *, positive: bool = False) -> None:
    if not isinstance(value, int) or isinstance(value, bool) or value < int(positive) or value > UINT64_MAX:
        raise CertificationDomainError(f"{name} must be {'positive ' if positive else ''}uint64")


@lru_cache(maxsize=8192)
def _exp_negative_interval(numerator: int, denominator: int) -> FixedInterval:
    """exp(-numerator/denominator), for a nonnegative rational <=64."""
    if numerator == 0:
        return FixedInterval(SCALE, SCALE)
    squarings = 0
    reduced_denominator = denominator
    while 2 * numerator > reduced_denominator:
        reduced_denominator *= 2
        squarings += 1
    term_lower = term_upper = SCALE
    total_lower = total_upper = SCALE
    for degree in range(1, EXP_TERMS + 1):
        divisor = reduced_denominator * degree
        term_lower = term_lower * numerator // divisor
        term_upper = _ceil_div(term_upper * numerator, divisor)
        total_lower += term_lower
        total_upper += term_upper
    first_omitted_upper = _ceil_div(term_upper * numerator, reduced_denominator * (EXP_TERMS + 1))
    total_upper += 2 * first_omitted_upper
    lower = SCALE * SCALE // total_upper
    upper = _ceil_div(SCALE * SCALE, total_lower)
    for _ in range(squarings):
        lower = lower * lower // SCALE
        upper = _ceil_div(upper * upper, SCALE)
    return FixedInterval(lower, upper)


def _log_atanh_interval(numerator: int, denominator: int) -> FixedInterval:
    """2*atanh(numerator/denominator) for 0<=numerator/denominator<=1/3."""
    if numerator == 0:
        return FixedInterval(0, 0)
    z_lower = numerator * SCALE // denominator
    z_upper = _ceil_div(numerator * SCALE, denominator)
    square_lower = z_lower * z_lower // SCALE
    square_upper = _ceil_div(z_upper * z_upper, SCALE)
    power_lower, power_upper = z_lower, z_upper
    total_lower = total_upper = 0
    for index in range(LOG_TERMS):
        divisor = 2 * index + 1
        total_lower += power_lower // divisor
        total_upper += _ceil_div(power_upper, divisor)
        power_lower = power_lower * square_lower // SCALE
        power_upper = _ceil_div(power_upper * square_upper, SCALE)
    # power now bounds z**(2*LOG_TERMS+1), including all directed rounding.
    tail_upper = _ceil_div(9 * power_upper, 4 * (2 * LOG_TERMS + 1))
    return FixedInterval(2 * total_lower, 2 * total_upper + tail_upper)


@lru_cache(maxsize=1)
def _log_two_interval() -> FixedInterval:
    return _log_atanh_interval(1, 3)


def _log_integer_scaled_interval(value: int) -> FixedInterval:
    """log(value/SCALE), where value/SCALE>=1, with exact power-of-two reduction."""
    if value < SCALE:
        raise CertificationDomainError("log sum must be at least one")
    exponent = value.bit_length() - SCALE.bit_length()
    base = SCALE << exponent
    if value < base:
        exponent -= 1
        base >>= 1
    reduced = _log_atanh_interval(value - base, value + base)
    two = _log_two_interval()
    return FixedInterval(reduced.lower + exponent * two.lower, reduced.upper + exponent * two.upper)


def _potential_interval(q: tuple[int, ...], b: int) -> FixedInterval:
    maximum = max(q)
    components = [_exp_negative_interval(maximum - value, b) for value in q]
    sum_lower = sum(value.lower for value in components)
    sum_upper = sum(value.upper for value in components)
    log_lower = _log_integer_scaled_interval(sum_lower).lower
    log_upper = _log_integer_scaled_interval(sum_upper).upper
    return FixedInterval(maximum * SCALE + b * log_lower, maximum * SCALE + b * log_upper)


def _validate(q: Sequence[int], b: int, outcome_index: int, shares: int, *, sell: bool) -> tuple[tuple[int, ...], tuple[int, ...]]:
    inventory = tuple(q)
    if not 2 <= len(inventory) <= MAX_OUTCOMES:
        raise CertificationDomainError("outcome count must be between 2 and 64")
    _uint64("b", b, positive=True)
    _uint64("shares", shares)
    if not isinstance(outcome_index, int) or isinstance(outcome_index, bool) or not 0 <= outcome_index < len(inventory):
        raise CertificationDomainError("invalid outcome index")
    for value in inventory:
        _uint64("inventory", value)
    if shares > MAX_NORMALIZED_SPREAD * b:
        raise CertificationDomainError("trade/depth ratio exceeds 64")
    updated = list(inventory)
    updated[outcome_index] += -shares if sell else shares
    _uint64("resulting inventory", updated[outcome_index])
    for vector in (inventory, updated):
        if max(vector) - min(vector) > MAX_NORMALIZED_SPREAD * b:
            raise CertificationDomainError("normalized inventory spread exceeds 64")
    return inventory, tuple(updated)


def _quote_interval(q: Sequence[int], b: int, outcome_index: int, shares: int, *, sell: bool) -> FixedInterval:
    before_q, after_q = _validate(q, b, outcome_index, shares, sell=sell)
    if shares == 0:
        return FixedInterval(0, 0)
    before, after = _potential_interval(before_q, b), _potential_interval(after_q, b)
    left, right = (before, after) if sell else (after, before)
    lower = max(0, left.lower - right.upper)
    upper = min(shares * SCALE, left.upper - right.lower)
    if lower > upper:
        raise CertificationPrecisionError("computed interval contradicts LMSR monotonicity bounds")
    interval = FixedInterval(lower, upper)
    if interval.width_numerator >= SCALE:
        raise CertificationPrecisionError("quote interval is not narrower than one raw token unit")
    return interval


def certified_lmsr_cost_delta_interval(q: Sequence[int], b: int, outcome_index: int, delta: int) -> FixedInterval:
    """Certificate for the exact positive-inventory LMSR cost increment."""
    return _quote_interval(q, b, outcome_index, delta, sell=False)


def certified_lmsr_sell_return_interval(q: Sequence[int], b: int, outcome_index: int, shares: int) -> FixedInterval:
    """Certificate for the exact LMSR cost decrement from selling inventory."""
    return _quote_interval(q, b, outcome_index, shares, sell=True)


def certified_lmsr_cost_delta(q: Sequence[int], b: int, outcome_index: int, delta: int) -> int:
    """Charge the ceiling of a certified upper bound, in raw token units."""
    return certified_lmsr_cost_delta_interval(q, b, outcome_index, delta).ceil_upper()


def certified_lmsr_sell_return(q: Sequence[int], b: int, outcome_index: int, shares: int) -> int:
    """Pay the floor of a certified lower bound, in raw token units."""
    return certified_lmsr_sell_return_interval(q, b, outcome_index, shares).floor_lower()
