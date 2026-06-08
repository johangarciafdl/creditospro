"""Tests para el cobro atomico con proteccion contra race conditions.

El problema original: with_for_update() es no-op en SQLite, por lo que dos
peticiones concurrentes podian leer la misma cuota, calcular el nuevo
valor_pagado y ambas escribir valores inconsistentes.

Solucion probada aqui: UPDATE condicional WHERE valor_pagado = <valor leido>
que afecta exactamente 1 fila si nadie mas escribio, o 0 si otra transaccion
ya actualizo la cuota.
"""
import datetime
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import (
    Base, Cuota, Prestamo, Cliente, Zona, Empresa, Usuario,
)
from app.routers.cobros import aplicar_cobro_atomico
from app.utils.money import money


@pytest.fixture()
def db():
    """Crea una BD SQLite en memoria con las tablas necesarias."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    try:
        empresa = Empresa(id=1, nombre="Test", activa=True)
        zona = Zona(id=1, empresa_id=1, codigo="Z1", nombre="Zona 1", activa=True)
        cliente = Cliente(
            id=1, empresa_id=1, cedula="123", nombre="Juan",
            telefono="555", zona_id=1,
        )
        prestamo = Prestamo(
            id=1, empresa_id=1, cliente_id=1, zona_id=1,
            capital=1000, interes_total=200, total_pagar=1200,
            num_cuotas=3, valor_cuota=400, plazo_dias=30,
            fecha_inicio=datetime.date(2026, 1, 1),
            estado="Activo",
        )
        session.add_all([empresa, zona, cliente, prestamo])
        session.flush()
        yield session
    finally:
        session.close()
        engine.dispose()


def _crear_cuota(db, valor=Decimal("400.00"), valor_pagado=Decimal("0.00")):
    cuota = Cuota(
        empresa_id=1, prestamo_id=1, numero=1,
        valor=valor, valor_pagado=valor_pagado,
        fecha_vencimiento=datetime.date(2026, 2, 1),
        estado="Pendiente",
    )
    db.add(cuota)
    db.commit()
    db.refresh(cuota)
    return cuota


def test_aplicar_cobro_atomico_actualiza_cuando_no_hay_conflicto(db):
    cuota = _crear_cuota(db)

    ok = aplicar_cobro_atomico(db, cuota, Decimal("100.00"))

    assert ok is True
    db.refresh(cuota)
    assert cuota.valor_pagado == Decimal("100.00")
    assert cuota.estado == "Parcial"


def test_aplicar_cobro_atomico_marca_como_pagada_cuando_termina(db):
    cuota = _crear_cuota(db, valor=Decimal("400.00"))

    ok = aplicar_cobro_atomico(db, cuota, Decimal("400.00"))

    assert ok is True
    db.refresh(cuota)
    assert cuota.valor_pagado == Decimal("400.00")
    assert cuota.estado == "Pagada"
    assert cuota.fecha_pago is not None


def test_aplicar_cobro_atomico_rechaza_si_otra_tx_ya_escribio(db):
    """Simula el caso de race condition: dos requests leen la misma cuota
    con valor_pagado=0, pero uno ya escribio valor_pagado=100. El segundo
    intento con la lectura vieja debe fallar (devolver False) para que el
    endpoint devuelva 409 al cliente.
    """
    cuota = _crear_cuota(db, valor=Decimal("400.00"), valor_pagado=Decimal("0.00"))

    # Primer cobro: OK, cuota pasa a 100 pagados
    assert aplicar_cobro_atomico(db, cuota, Decimal("100.00")) is True

    # Segundo cobro: el caller todavia cree que la cuota esta en 0 (lectura
    # vieja). El WHERE valor_pagado = 0 no coincide, debe devolver False.
    lectura_vieja = Cuota(
        id=cuota.id, empresa_id=cuota.empresa_id, prestamo_id=cuota.prestamo_id,
        numero=cuota.numero, valor=cuota.valor, valor_pagado=Decimal("0.00"),
        fecha_vencimiento=cuota.fecha_vencimiento, estado="Pendiente",
    )
    ok = aplicar_cobro_atomico(db, lectura_vieja, Decimal("50.00"))

    assert ok is False
    db.refresh(cuota)
    # El valor real de la cuota no se modifica por el intento fallido
    assert cuota.valor_pagado == Decimal("100.00")
    assert cuota.estado == "Parcial"


def test_aplicar_cobro_atomico_lectura_concurrente_dos_ganadores_consistentes(db):
    """Simula dos peticiones que ganan la carrera a la vez: solo una debe
    poder actualizar. La otra falla con False, no se duplica el pago.
    """
    cuota = _crear_cuota(db, valor=Decimal("400.00"), valor_pagado=Decimal("0.00"))

    snapshot_antes = Decimal("0.00")
    snapshot_despues = Decimal("0.00")

    # Ambos leen al mismo tiempo
    lectura_a = Cuota(
        id=cuota.id, empresa_id=cuota.empresa_id, prestamo_id=cuota.prestamo_id,
        numero=cuota.numero, valor=cuota.valor, valor_pagado=snapshot_antes,
        fecha_vencimiento=cuota.fecha_vencimiento, estado="Pendiente",
    )
    lectura_b = Cuota(
        id=cuota.id, empresa_id=cuota.empresa_id, prestamo_id=cuota.prestamo_id,
        numero=cuota.numero, valor=cuota.valor, valor_pagado=snapshot_antes,
        fecha_vencimiento=cuota.fecha_vencimiento, estado="Pendiente",
    )

    # El primero gana, actualiza el snapshot en el objeto local
    ganador = aplicar_cobro_atomico(db, lectura_a, Decimal("200.00"))
    snapshot_despues = money(snapshot_antes + Decimal("200.00"))

    # El segundo intenta con la lectura vieja: WHERE valor_pagado = 0 ya no
    # coincide, por lo que falla.
    perdedor = aplicar_cobro_atomico(db, lectura_b, Decimal("200.00"))

    assert ganador is True
    assert perdedor is False
    db.refresh(cuota)
    assert cuota.valor_pagado == Decimal("200.00")


def test_aplicar_cobro_atomico_usa_redondeo_money(db):
    """Verifica que los cobros con decimales se redondean consistentemente."""
    cuota = _crear_cuota(db, valor=Decimal("100.00"), valor_pagado=Decimal("0.00"))

    aplicar_cobro_atomico(db, cuota, Decimal("33.33"))

    db.refresh(cuota)
    assert cuota.valor_pagado == Decimal("33.33")
    assert cuota.estado == "Parcial"
