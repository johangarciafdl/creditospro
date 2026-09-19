from decimal import Decimal, ROUND_DOWN, ROUND_HALF_UP


CENT = Decimal("0.01")


def money(value) -> Decimal:
    return Decimal(str(value or "0")).quantize(CENT, rounding=ROUND_HALF_UP)


def money_int(value) -> Decimal:
    return Decimal(str(value or "0")).quantize(Decimal("1"), rounding=ROUND_HALF_UP)


def cop(value) -> str:
    """Pesos colombianos para el usuario: $1.500, $2.000.000, $933,36.

    El punto separa los miles y la coma los decimales, como se escribe en
    Colombia. Sin esto los mensajes de error mostraban Decimal('10000.00'),
    que no dice nada a un cobrador.

    Los centavos solo aparecen cuando los hay. Redondearlos siempre hacia el
    peso entero hacia que la pantalla y el cobro discreparan: la tarjeta de
    una cuota de 933,36 anunciaba "$933" y el formulario cobraba 933,36, y
    esa diferencia de 36 centavos por cuota no cuadraba en ningun arqueo. Lo
    que se muestra tiene que ser exactamente lo que se cobra.
    """
    d = money(value)
    entero = int(d.to_integral_value(rounding=ROUND_DOWN))
    centavos = int((abs(d) - abs(Decimal(entero))) * 100)
    texto = "$" + f"{entero:,}".replace(",", ".")
    return texto if centavos == 0 else f"{texto},{centavos:02d}"
