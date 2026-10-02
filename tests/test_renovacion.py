"""Renovar: prestarle de nuevo a quien aun debe, descontando lo que debe.

Caso: debe 60.000 (2 cuotas de 30.000) y se le renueva por 200.000.
- Las dos cuotas quedan pagadas con un cobro "Renovacion" de 60.000.
- El prestamo viejo queda Pagado; el nuevo sale por 200.000.
- En la caja del cobrador sale de verdad solo lo que entrega: 140.000.
"""
import datetime
import tempfile
from decimal import Decimal
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="module")
def entorno():
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    bd = Path(tempfile.gettempdir()) / "creditospro_renovacion_test.db"
    if bd.exists():
        bd.unlink()

    from app.database import Base, Cliente, Cuota, Empresa, Prestamo, Usuario, Zona, hoy_local
    from app.main import app
    from app.utils.company_activation import assign_company_key
    from app.utils.security import get_password_hash

    motor = create_engine(f"sqlite:///{bd}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(motor)
    Sesion = sessionmaker(bind=motor, autoflush=False)

    def _sesion():
        db = Sesion()
        try:
            yield db
        finally:
            db.close()

    from conftest import sustituir_sesion, vaciar_limitador
    claves = sustituir_sesion(app, _sesion)

    hoy = hoy_local()
    d = {"hoy": hoy}
    db = Sesion()
    try:
        e = Empresa(nombre="RenuevaSA", activa=True)
        db.add(e); db.flush()
        d["clave"] = assign_company_key(db, e)
        d["empresa_id"] = e.id
        z = Zona(empresa_id=e.id, codigo="RN", nombre="Centro")
        otra = Zona(empresa_id=e.id, codigo="RO", nombre="Otra")
        db.add_all([z, otra]); db.flush()
        cob = Usuario(empresa_id=e.id, username="renuevacob", nombre="Renueva Cob", rol="cobrador",
                      activo=True, password_hash=get_password_hash("ClaveDePrueba123!"))
        db.add(cob); db.flush()
        cob.zonas_asignadas.append(z)
        d["cobrador_id"] = cob.id

        def cliente_con_deuda(nombre, cedula, zona):
            c = Cliente(empresa_id=e.id, cedula=cedula, nombre=nombre, telefono="3001112233",
                        zona_id=zona.id, activo=True)
            db.add(c); db.flush()
            p = Prestamo(empresa_id=e.id, cliente_id=c.id, zona_id=zona.id,
                         capital=Decimal("100000"), tasa_interes=Decimal("20"),
                         total_pagar=Decimal("120000"), num_cuotas=4, valor_cuota=Decimal("30000"),
                         estado="Activo", fecha_inicio=hoy - datetime.timedelta(days=10),
                         fecha_fin=hoy + datetime.timedelta(days=10))
            db.add(p); db.flush()
            for n in range(4):
                pagada = n < 2
                db.add(Cuota(empresa_id=e.id, prestamo_id=p.id, numero=n + 1,
                             valor=Decimal("30000"),
                             valor_pagado=Decimal("30000" if pagada else "0"),
                             estado="Pagada" if pagada else "Pendiente",
                             fecha_vencimiento=hoy + datetime.timedelta(days=n - 2)))
            return c.id, p.id

        d["cliente"], d["prestamo"] = cliente_con_deuda("Renata Deudora", "1000201", z)
        d["cliente_otra"], d["prestamo_otra"] = cliente_con_deuda("Otra Zona", "1000202", otra)
        db.commit()
    finally:
        db.close()

    vaciar_limitador()
    cli = TestClient(app)
    cli.__enter__()
    assert cli.post("/license/activate", data={"license_key": d["clave"]}).status_code == 200
    assert cli.post("/auth/login", data={"username": "renuevacob",
                                         "password": "ClaveDePrueba123!"}).status_code == 200
    cli.get("/ruta")
    cli.headers["x-csrf-token"] = cli.cookies.get("cp_csrf", "")
    yield cli, d, Sesion
    cli.__exit__(None, None, None)
    for clave in claves:
        app.dependency_overrides.pop(clave, None)
    motor.dispose()
    bd.unlink(missing_ok=True)


def _renovar(cli, d, capital, prestamo=None):
    return cli.post("/ruta/renovar", data={
        "prestamo_id": prestamo or d["prestamo"], "capital": str(capital),
        "tasa_interes": "20", "num_cuotas": "10", "plazo_dias": "1"})


def test_el_buscador_dice_cuanto_debe(entorno):
    cli, d, _ = entorno
    c = cli.get("/ruta/buscar-cliente", params={"q": "Renata"}).json()["clientes"][0]
    assert c["debe"] == 60000.0 and c["prestamo_activo_id"] == d["prestamo"]


def test_no_se_renueva_por_menos_de_lo_que_debe(entorno):
    cli, d, _ = entorno
    r = _renovar(cli, d, 60000)
    assert r.status_code == 400 and "mayor que lo que debe" in r.json()["error"]


def test_no_se_renueva_en_una_zona_que_no_es_suya(entorno):
    cli, d, _ = entorno
    assert _renovar(cli, d, 200000, d["prestamo_otra"]).status_code == 403


def test_renovar_descuenta_lo_que_debe_y_cuadra_la_caja(entorno):
    cli, d, Sesion = entorno
    from app.database import Cobro, Cuota, Prestamo
    antes = cli.get("/caja/resumen").json()["cuadre"]
    r = _renovar(cli, d, 200000)
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["saldo_descontado"] == 60000.0 and j["entregado"] == 140000.0
    db = Sesion()
    try:
        viejo = db.get(Prestamo, d["prestamo"])
        assert viejo.estado == "Pagado"
        assert all(c.estado == "Pagada" for c in
                   db.query(Cuota).filter(Cuota.prestamo_id == viejo.id))
        cobros = db.query(Cobro).filter(Cobro.prestamo_id == viejo.id).all()
        assert sum(c.valor_cobrado for c in cobros) == Decimal("60000")
        assert {c.metodo_pago for c in cobros} == {"Renovacion"}
        nuevo = db.get(Prestamo, j["prestamo_id"])
        assert nuevo.capital == Decimal("200000") and nuevo.cliente_id == d["cliente"]
        assert "#%d" % viejo.id in nuevo.observaciones
    finally:
        db.close()
    despues = cli.get("/caja/resumen").json()["cuadre"]
    # Antes no se habia movido (sin base); ahora lleva la base automatica de
    # 500.000. De ella sale solo lo que se entrego en mano:
    # 500.000 + 60.000 cobrados - 200.000 prestados = 500.000 - 140.000.
    assert antes["esperado"] == 0.0
    assert despues["cobrado"] == 60000.0 and despues["prestado"] == 200000.0
    assert despues["esperado"] == despues["base"] - 140000.0


def test_un_prestamo_ya_pagado_no_se_renueva(entorno):
    cli, d, _ = entorno
    r = _renovar(cli, d, 300000)
    assert r.status_code == 400 and "no debe nada" in r.json()["error"]


def test_el_formulario_ofrece_renovar():
    html = Path("templates/app_cobrador.html").read_text(encoding="utf-8")
    for pieza in ('id="p-renovar"', "'/ruta/renovar'", "Le entregas en mano"):
        assert pieza in html, pieza
