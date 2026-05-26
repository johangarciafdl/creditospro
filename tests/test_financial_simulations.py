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
    resultado = calcular_cuotas(1000, 20, 7, datetime.date(2026, 1, 1), 1)

    valores = [c["valor"] for c in resultado["cuotas"]]
    assert sum(valores) == Decimal("1200.00")
    assert valores[:-1] == [Decimal("171.43")] * 6
    assert valores[-1] == Decimal("171.42")
