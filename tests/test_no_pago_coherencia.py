"""El historial de una cuota no puede decir dos cosas contrarias.

Un cobro se puede registrar con la fecha del dia en que se recibio, que no
es siempre el dia en que se teclea. Si esa fecha es anterior a un "no pago"
ya anotado y el cobro salda la cuota, el historial afirmaria a la vez que la
cuota se pago el 17 y que el cliente no pago el 19 -- imposible, porque el
19 ya no habia nada que cobrar. Los registros de no pago anteriores al pago
si son ciertos y se conservan: el cliente realmente no pago esos dias.
"""
import datetime
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base, Cuota, NoPago


@pytest.fixture()
def db():
    motor = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(motor)
    s = sessionmaker(bind=motor)()
    yield s
    s.close()


def _cuota(db, valor="1000"):
    c = Cuota(empresa_id=1, prestamo_id=1, numero=1, valor=Decimal(valor),
              valor_pagado=Decimal("0"), estado="Pendiente",
              fecha_vencimiento=datetime.date(2026, 9, 14))
    db.add(c)
    db.commit()
    return c


def _no_pago(db, cuota, dia):
    db.add(NoPago(empresa_id=1, cuota_id=cuota.id, prestamo_id=1, cliente_id=1,
                  fecha=dia))
    db.commit()


def _limpiar(db, cuota, fecha_pago, empresa_id=1):
    """La regla del endpoint: solo si la cuota quedo saldada."""
    if cuota.estado != "Pagada":
        return 0
    return (db.query(NoPago)
            .filter(NoPago.cuota_id == cuota.id,
                    NoPago.empresa_id == empresa_id,
                    NoPago.fecha > fecha_pago)
            .delete(synchronize_session=False))


def test_se_retira_el_no_pago_posterior_a_un_pago_que_salda_la_cuota(db):
    c = _cuota(db)
    _no_pago(db, c, datetime.date(2026, 9, 19))
    c.estado = "Pagada"
    c.valor_pagado = Decimal("1000")
    db.commit()

    assert _limpiar(db, c, datetime.date(2026, 9, 17)) == 1
    db.commit()
    assert db.query(NoPago).count() == 0


def test_se_conservan_los_no_pago_anteriores_al_pago(db):
    """Esos dias el cliente de verdad no pago."""
    c = _cuota(db)
    _no_pago(db, c, datetime.date(2026, 9, 14))
    _no_pago(db, c, datetime.date(2026, 9, 15))
    c.estado = "Pagada"
    db.commit()

    assert _limpiar(db, c, datetime.date(2026, 9, 17)) == 0
    assert db.query(NoPago).count() == 2


def test_un_abono_parcial_no_borra_nada(db):
    """La cuota sigue debiendo: volver y no cobrar es perfectamente posible."""
    c = _cuota(db)
    _no_pago(db, c, datetime.date(2026, 9, 19))
    c.estado = "Parcial"
    c.valor_pagado = Decimal("300")
    db.commit()

    assert _limpiar(db, c, datetime.date(2026, 9, 17)) == 0
    assert db.query(NoPago).count() == 1


def test_no_toca_los_no_pago_de_otra_empresa(db):
    c = _cuota(db)
    db.add(NoPago(empresa_id=2, cuota_id=c.id, prestamo_id=1, cliente_id=1,
                  fecha=datetime.date(2026, 9, 19)))
    c.estado = "Pagada"
    db.commit()

    assert _limpiar(db, c, datetime.date(2026, 9, 17), empresa_id=1) == 0
    assert db.query(NoPago).count() == 1
