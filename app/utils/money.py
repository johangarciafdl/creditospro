from decimal import Decimal, ROUND_HALF_UP


CENT = Decimal("0.01")


def money(value) -> Decimal:
    return Decimal(str(value or "0")).quantize(CENT, rounding=ROUND_HALF_UP)


def money_int(value) -> Decimal:
    return Decimal(str(value or "0")).quantize(Decimal("1"), rounding=ROUND_HALF_UP)


def cop(value) -> str:
    """Pesos colombianos para mensajes al usuario: $1.500, $2.000.000.

    El punto separa los miles, como se escribe en Colombia. Sin esto los
    mensajes de error mostraban Decimal('10000.00'), que no dice nada a un
    cobrador.
    """
    entero = int(money_int(value))
    return "$" + f"{entero:,}".replace(",", ".")
