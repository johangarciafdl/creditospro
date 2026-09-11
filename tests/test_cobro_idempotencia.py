"""Un cobro sincronizado dos veces desde la PWA no debe cobrarse dos veces.

Escenario real: el cobrador registra el cobro sin señal, la PWA lo sube al
recuperar conexion, el servidor lo aplica, pero la respuesta se pierde en el
camino (tipico en la calle). La PWA lo sigue viendo como pendiente y lo
reintenta. Sin clave de idempotencia, el cliente termina con dos cobros
registrados por el mismo pago.
"""
import datetime
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base, Cliente, Cobro, Cuota, Empresa, Prestamo, Zona
from app.routers.cobros import aplicar_cobro_atomico
from app.utils.money import money


@pytest.fixture()
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    try:
        session.add_all([
            Empresa(id=1, nombre="Test", activa=True),
            Zona(id=1, empresa_id=1, codigo="Z1", nombre="Zona 1", activa=True),
            Cliente(id=1, empresa_id=1, cedula="123", nombre="Juan", telefono="3101112233", zona_id=1),
            Prestamo(id=1, empresa_id=1, cliente_id=1, zona_id=1, capital=1000,
                     interes_total=200, total_pagar=1200, num_cuotas=3, valor_cuota=400,
                     plazo_dias=30, fecha_inicio=datetime.date(2026, 1, 1), estado="Activo"),
        ])
        session.flush()
        cuota = Cuota(empresa_id=1, prestamo_id=1, numero=1, valor=Decimal("400.00"),
                      valor_pagado=Decimal("0.00"), fecha_vencimiento=datetime.date(2026, 2, 1),
                      estado="Pendiente")
        session.add(cuota)
        session.commit()
        yield session
    finally:
        session.close()
        engine.dispose()


def _registrar(db, clave, valor=Decimal("100.00")):
    """Replica lo que hace /cobros/registrar con la clave de idempotencia."""
    ya = db.query(Cobro).filter(Cobro.empresa_id == 1, Cobro.idempotency_key == clave).first()
    if ya:
        return ya, True                      # reintento: se devuelve el existente

    cuota = db.query(Cuota).filter(Cuota.empresa_id == 1).first()
    assert aplicar_cobro_atomico(db, cuota, money(valor))
    cobro = Cobro(empresa_id=1, cuota_id=cuota.id, prestamo_id=1, cliente_id=1, zona_id=1,
                  valor_cobrado=money(valor), fecha=datetime.date.today(), cobrador="tester",
                  metodo_pago="Efectivo", idempotency_key=clave)
    db.add(cobro)
    db.commit()
    return cobro, False


def test_reintento_con_la_misma_clave_no_cobra_dos_veces(db):
    primero, era_dup = _registrar(db, "clave-del-celular-123")
    assert not era_dup

    segundo, era_dup = _registrar(db, "clave-del-celular-123")   # la PWA reintenta
    assert era_dup and segundo.id == primero.id

    assert db.query(Cobro).count() == 1, "se registro el cobro dos veces"
    cuota = db.query(Cuota).filter(Cuota.empresa_id == 1).first()
    assert money(cuota.valor_pagado) == money("100.00"), "la cuota se pago dos veces"


def test_cobros_distintos_si_se_registran(db):
    _registrar(db, "clave-a", Decimal("100.00"))
    _registrar(db, "clave-b", Decimal("50.00"))

    assert db.query(Cobro).count() == 2
    cuota = db.query(Cuota).filter(Cuota.empresa_id == 1).first()
    assert money(cuota.valor_pagado) == money("150.00")


def test_la_clave_es_unica_por_empresa(db):
    """Dos empresas pueden generar la misma clave sin pisarse."""
    db.add(Empresa(id=2, nombre="Otra", activa=True))
    db.commit()
    _registrar(db, "misma-clave")
    otra = db.query(Cobro).filter(Cobro.empresa_id == 2, Cobro.idempotency_key == "misma-clave").first()
    assert otra is None, "la clave de una empresa no debe verse desde otra"
