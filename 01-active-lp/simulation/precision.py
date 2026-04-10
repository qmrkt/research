from __future__ import annotations

from contextlib import contextmanager
from decimal import Decimal, localcontext

DEFAULT_PRECISION = 80
DECIMAL_ZERO = Decimal("0")
DECIMAL_ONE = Decimal("1")


def to_decimal(value: int | float | Decimal | str) -> Decimal:
    if isinstance(value, Decimal):
        return value
    if isinstance(value, int):
        return Decimal(value)
    if isinstance(value, float):
        return Decimal(str(value))
    return Decimal(value)


@contextmanager
def high_precision(precision: int = DEFAULT_PRECISION):
    with localcontext() as ctx:
        ctx.prec = precision
        yield ctx
