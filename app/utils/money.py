from decimal import Decimal, ROUND_HALF_UP


CENT = Decimal("0.01")


def money(value) -> Decimal:
    return Decimal(str(value or "0")).quantize(CENT, rounding=ROUND_HALF_UP)


def money_int(value) -> Decimal:
    return Decimal(str(value or "0")).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
