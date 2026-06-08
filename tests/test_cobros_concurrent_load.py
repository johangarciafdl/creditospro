"""Tests de concurrencia: muchas peticiones simultaneas al cobro atomico.

Usa threads con sesiones independientes de SQLAlchemy para simular
dos cobradores haciendo cobros al mismo tiempo sobre la misma cuota.
"""
import datetime
import threading
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import (
    Base, Cuota, Prestamo, Cliente, Zona, Empresa, Cobro,
)
from app.routers.cobros import aplicar_cobro_atomico
from app.utils.money import money


@pytest.fixture()
def concurrent_db(tmp_path):
    """Crea una BD SQLite en archivo (no :memory:) para que todos los
    threads compartan el mismo archivo fisico y vean los mismos datos.
    """
    db_file = tmp_path / "concurrent_test.db"
    url = f"sqlite:///{db_file}"
    engine = create_engine(url, connect_args={"check_same_thread": False}, pool_size=5)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)

    with Session() as db:
        db.add(Empresa(id=1, nombre="Test", activa=True))
        db.add(Zona(id=1, empresa_id=1, codigo="Z1", nombre="Zona 1", activa=True))
        db.add(Cliente(
            id=1, empresa_id=1, cedula="123", nombre="Juan",
            telefono="555", zona_id=1,
        ))
        db.add(Prestamo(
            id=1, empresa_id=1, cliente_id=1, zona_id=1,
            capital=1000, interes_total=200, total_pagar=1200,
            num_cuotas=3, valor_cuota=400, plazo_dias=30,
            fecha_inicio=datetime.date(2026, 1, 1),
            estado="Activo",
        ))
        db.add(Cuota(
            id=1, empresa_id=1, prestamo_id=1, numero=1,
            valor=Decimal("400.00"), valor_pagado=Decimal("0.00"),
            fecha_vencimiento=datetime.date(2026, 2, 1),
            estado="Pendiente",
        ))
        db.commit()

    yield engine, Session

    engine.dispose()
    try:
        db_file.unlink()
    except FileNotFoundError:
        pass


def test_dos_cobros_simultaneos_solo_uno_gana(concurrent_db):
    """Dos threads intentan cobrar la misma cuota a la vez.
    Solo uno debe ganar (devolver True), el otro debe perder (False).
    El valor_pagado final debe ser exactamente el valor del primer cobro.
    """
    engine, Session = concurrent_db
    barrier = threading.Barrier(2)
    results = [None, None]
    errors = [None, None]

    def worker(idx: int):
        db = Session()
        try:
            # Ambos leen la cuota
            cuota = db.query(Cuota).filter(Cuota.id == 1).first()
            snapshot = money(cuota.valor_pagado)

            # Esperar a que ambos hayan leido antes de proceder
            barrier.wait(timeout=5)

            # Intentar cobrar
            try:
                ok = aplicar_cobro_atomico(db, cuota, Decimal("100.00"))
                results[idx] = ok
                db.commit()
            except Exception as e:
                errors[idx] = str(e)
                db.rollback()
        finally:
            db.close()

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10)

    assert errors[0] is None and errors[1] is None, f"Errors: {errors}"
    # Exactamente uno True y uno False
    assert sum(1 for r in results if r) == 1, f"results={results}"
    assert sum(1 for r in results if not r) == 1, f"results={results}"

    # El valor_pagado final debe ser 100 (solo un cobro exitoso)
    with Session() as db:
        cuota = db.query(Cuota).filter(Cuota.id == 1).first()
        assert cuota.valor_pagado == Decimal("100.00"), (
            f"valor_pagado final incorrecto: {cuota.valor_pagado}"
        )

        # Solo debe haber 1 cobro en la tabla
        cobros = db.query(Cobro).count()
        # Nota: aplicar_cobro_atomico no inserta Cobro, eso lo hace el
        # endpoint. Aqui solo validamos que el update es atomico.
        assert cobros == 0


def test_diez_cobros_de_a_uno_suman_diez(concurrent_db):
    """10 threads hacen cobros secuenciales de $10.
    La cuota de $100 debe quedar exactamente pagada.
    """
    engine, Session = concurrent_db
    # Reducir valor de la cuota a 100 para este test
    with Session() as db:
        cuota = db.query(Cuota).filter(Cuota.id == 1).first()
        cuota.valor = Decimal("100.00")
        db.commit()

    barrier = threading.Barrier(10)
    successes = []
    lock = threading.Lock()

    def worker(idx: int):
        db = Session()
        try:
            for intento in range(50):
                cuota = db.query(Cuota).filter(Cuota.id == 1).first()
                if not cuota or money(cuota.valor_pagado) >= money(cuota.valor):
                    return
                if aplicar_cobro_atomico(db, cuota, Decimal("10.00")):
                    db.commit()
                    with lock:
                        successes.append(idx)
                    return
                db.rollback()
        finally:
            db.close()

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)

    # Todos los 10 deben haber logrado cobrar
    assert len(successes) == 10, f"Solo {len(successes)}/10 lograron cobrar"

    with Session() as db:
        cuota = db.query(Cuota).filter(Cuota.id == 1).first()
        assert cuota.valor_pagado == Decimal("100.00")
        assert cuota.estado == "Pagada"
