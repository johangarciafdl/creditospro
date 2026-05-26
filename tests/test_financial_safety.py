from decimal import Decimal

from sqlalchemy import Numeric

from app.database import Cobro, Cuota, Prestamo
from app.services.prestamo_service import calcular_cuotas


def test_money_columns_use_numeric():
    assert isinstance(Prestamo.__table__.c.capital.type, Numeric)
    assert isinstance(Cuota.__table__.c.valor.type, Numeric)
    assert isinstance(Cobro.__table__.c.valor_cobrado.type, Numeric)


def test_calcular_cuotas_uses_decimal_money():
    result = calcular_cuotas(1000, 20, 3, __import__("datetime").date.today(), 1)
    assert isinstance(result["total_pagar"], Decimal)
    assert result["total_pagar"] == Decimal("1200.00")
