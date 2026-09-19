import datetime
import random
from decimal import Decimal

import pytest

from app.services.prestamo_service import calcular_cuotas


def _money(value):
    return Decimal(str(value)).quantize(Decimal("0.01"))


def test_simulacion_cuotas_suman_exactamente_total_pagar():
    rng = random.Random(20260524)
    fecha = datetime.date(2026, 1, 1)

    for _ in range(1000):
        capital = rng.randint(50_000, 20_000_000)
        tasa = rng.choice([0, 1.5, 2.75, 5, 10, 19.9, 20, 33.33, 50])
        cuotas = rng.randint(1, 120)
        plazo = rng.randint(1, 60)

        resultado = calcular_cuotas(capital, tasa, cuotas, fecha, plazo)
        total_cuotas = sum(c["valor"] for c in resultado["cuotas"])

        assert total_cuotas == resultado["total_pagar"]
        assert len(resultado["cuotas"]) == cuotas
        assert resultado["cuotas"][-1]["fecha_vencimiento"] == fecha + datetime.timedelta(days=cuotas * plazo)
        assert all(c["valor"] > Decimal("0.00") for c in resultado["cuotas"])


def test_simulacion_rechaza_parametros_invalidos():
    fecha = datetime.date(2026, 1, 1)

    with pytest.raises(ValueError):
        calcular_cuotas(100_000, 20, 0, fecha, 1)
    with pytest.raises(ValueError):
        calcular_cuotas(100_000, 20, 10, fecha, 0)
    with pytest.raises(ValueError):
        calcular_cuotas(-100_000, 20, 10, fecha, 1)
    with pytest.raises(ValueError):
        calcular_cuotas(100_000, -20, 10, fecha, 1)


def test_simulacion_caso_con_residuo_ajusta_ultima_cuota():
    """1200 entre 7 no da exacto: el residuo va a la ultima cuota.

    Los valores son pesos enteros porque el peso colombiano no circula en
    centavos: una cuota de 171,43 no se puede entregar en mano, y al
    mostrarla redondeada la pantalla dejaba de coincidir con lo que el
    sistema cobraba.
    """
    resultado = calcular_cuotas(1000, 20, 7, datetime.date(2026, 1, 1), 1)

    valores = [c["valor"] for c in resultado["cuotas"]]
    assert sum(valores) == Decimal("1200"), "las cuotas deben sumar el total"
    assert valores[:-1] == [Decimal("171")] * 6
    assert valores[-1] == Decimal("174")  # 1200 - 6*171, el residuo al final


def test_ninguna_cuota_lleva_centavos():
    """Ningun plan de pagos puede pedir una fraccion de peso."""
    casos = [(1000, 20, 7), (200_000, 20, 10), (50_000, 10, 30),
             (1_000_000, 15, 7), (333_333, 33, 3)]
    for capital, tasa, num in casos:
        r = calcular_cuotas(capital, tasa, num, datetime.date(2026, 1, 1), 1)
        valores = [c["valor"] for c in r["cuotas"]]
        assert sum(valores) == r["total_pagar"], f"{capital}/{tasa}/{num} no cuadra"
        for v in valores:
            assert v == v.to_integral_value(), f"cuota con centavos: {v}"
