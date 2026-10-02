"""El cierre del dia: el cobrador declara, el administrador confirma.

Confirmado, la caja de ese dia queda cerrada: no se le anotan ni retiran
movimientos y no se presta con esa fecha. Los cobros SI entran (pueden llegar
tarde de la cola sin señal; rechazarlos perderia el registro de un pago) y el
cierre los muestra como llegados despues.
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

    bd = Path(tempfile.gettempdir()) / "creditospro_cierre_test.db"
    if bd.exists():
        bd.unlink()

    from app.database import (Base, Cliente, Cuota, Empresa, Prestamo, Usuario, Zona,
                              hoy_local)
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
        e = Empresa(nombre="CierreSA", activa=True)
        db.add(e); db.flush()
        d["empresa_id"] = e.id
        d["clave"] = assign_company_key(db, e)
        z = Zona(empresa_id=e.id, codigo="CZ", nombre="Centro")
        db.add(z); db.flush()
        d["zona"] = z.id
        admin = Usuario(empresa_id=e.id, username="cierrejefa", nombre="Cierre Jefa", rol="admin",
                        activo=True, password_hash=get_password_hash("ClaveDePrueba123!"))
        cob = Usuario(empresa_id=e.id, username="cierrecobra", nombre="Cierre Cobra",
                      rol="cobrador", activo=True,
                      password_hash=get_password_hash("ClaveDePrueba123!"))
        db.add_all([admin, cob]); db.flush()
        cob.zonas_asignadas.append(z)
        d["cobrador_id"] = cob.id
        c = Cliente(empresa_id=e.id, cedula="1000777", nombre="Cliente Cierre",
                    telefono="3001112233", zona_id=z.id, activo=True)
        db.add(c); db.flush()
        p = Prestamo(empresa_id=e.id, cliente_id=c.id, zona_id=z.id, capital=Decimal("100000"),
                     tasa_interes=Decimal("20"), total_pagar=Decimal("120000"), num_cuotas=4,
                     valor_cuota=Decimal("30000"), estado="Activo",
                     fecha_inicio=hoy - datetime.timedelta(days=10), fecha_fin=hoy)
        db.add(p); db.flush()
        cuotas = []
        for n in range(4):
            cu = Cuota(empresa_id=e.id, prestamo_id=p.id, numero=n + 1, valor=Decimal("30000"),
                       valor_pagado=Decimal("0"), estado="Pendiente",
                       fecha_vencimiento=hoy - datetime.timedelta(days=3 - n))
            db.add(cu); db.flush()
            cuotas.append(cu.id)
        d["cuotas"] = cuotas
        db.commit()
    finally:
        db.close()

    def entrar(usuario):
        vaciar_limitador()
        cli = TestClient(app)
        cli.__enter__()
        assert cli.post("/license/activate", data={"license_key": d["clave"]}).status_code == 200
        assert cli.post("/auth/login", data={"username": usuario,
                                             "password": "ClaveDePrueba123!"}).status_code == 200
        cli.get("/caja")
        cli.headers["x-csrf-token"] = cli.cookies.get("cp_csrf", "")
        return cli

    jefa, cobra = entrar("cierrejefa"), entrar("cierrecobra")
    yield jefa, cobra, d, Sesion
    for c in (jefa, cobra):
        c.__exit__(None, None, None)
    for clave in claves:
        app.dependency_overrides.pop(clave, None)
    motor.dispose()
    bd.unlink(missing_ok=True)


def _cuadre(cli, d):
    r = cli.get("/caja/resumen", params={"usuario_id": d["cobrador_id"],
                                         "fecha": d["hoy"].isoformat()})
    assert r.status_code == 200, r.text
    return r.json()["cuadre"]


def test_un_dia_de_trabajo_y_el_cobrador_declara(entorno):
    jefa, cobra, d, _ = entorno
    r = cobra.post("/cobros/registrar", data={"cuota_id": d["cuotas"][0],
                                              "valor_cobrado": "30000", "metodo_pago": "Efectivo"})
    assert r.status_code == 200, r.text
    r = cobra.post("/caja/movimiento", data={"usuario_id": d["cobrador_id"], "tipo": "gasto",
                                             "valor": "8000", "fecha": d["hoy"].isoformat(),
                                             "concepto": "almuerzo"})
    assert r.status_code == 200, r.text
    # base automatica 500.000 + 30.000 - 8.000 = 522.000
    assert _cuadre(jefa, d)["esperado"] == 522000.0
    r = cobra.post("/caja/cierre/declarar", data={"entrego": "520.000", "nota": "falta un billete"})
    assert r.status_code == 200, r.text
    k = _cuadre(jefa, d)["cierre"]
    assert k["estado"] == "declarado" and k["declarado"] == 520000.0
    # Mientras no confirme el admin, lo puede corregir.
    assert cobra.post("/caja/cierre/declarar", data={"entrego": "521000"}).status_code == 200
    assert _cuadre(jefa, d)["cierre"]["declarado"] == 521000.0


def test_solo_el_admin_confirma_y_el_cobrador_solo_declara(entorno):
    jefa, cobra, d, _ = entorno
    r = cobra.post("/caja/cierre/confirmar", data={"usuario_id": d["cobrador_id"],
                                                   "fecha": d["hoy"].isoformat(), "recibido": "1"})
    assert r.status_code == 403
    assert jefa.post("/caja/cierre/declarar", data={"entrego": "1"}).status_code == 400


def test_el_admin_confirma_y_queda_la_diferencia(entorno):
    jefa, _, d, _ = entorno
    r = jefa.post("/caja/cierre/confirmar", data={"usuario_id": d["cobrador_id"],
                                                  "fecha": d["hoy"].isoformat(),
                                                  "recibido": "521000"})
    assert r.status_code == 200, r.text
    assert "faltante de 1.000" in r.json()["mensaje"]
    c = _cuadre(jefa, d)
    assert c["cierre"]["estado"] == "confirmado"
    assert c["cierre"]["diferencia"] == -1000.0
    # La entrega quedo anotada: lo que le queda encima es el faltante.
    assert c["entregado"] == 521000.0 and c["esperado"] == 1000.0
    assert jefa.post("/caja/cierre/confirmar", data={"usuario_id": d["cobrador_id"],
                                                     "fecha": d["hoy"].isoformat(),
                                                     "recibido": "1"}).status_code == 409


def test_cerrada_no_se_anota_ni_se_retira_ni_se_presta(entorno):
    jefa, cobra, d, _ = entorno
    r = cobra.post("/caja/movimiento", data={"usuario_id": d["cobrador_id"], "tipo": "gasto",
                                             "valor": "1000", "fecha": d["hoy"].isoformat(),
                                             "concepto": "taxi"})
    assert r.status_code == 409
    gasto = next(m for m in _cuadre(jefa, d)["movimientos"] if m["tipo"] == "gasto")
    assert jefa.post(f"/caja/movimiento/{gasto['id']}/borrar").status_code == 409
    assert cobra.post("/caja/cierre/declarar", data={"entrego": "5"}).status_code == 409
    r = cobra.post("/ruta/prestar", data={
        "zona_id": d["zona"], "capital": "50000", "tasa_interes": "20", "num_cuotas": "10",
        "plazo_dias": "1", "cedula": "1000888", "nombre": "Nuevo Cliente", "telefono": "3005550000"})
    assert r.status_code == 409, r.text


def test_un_cobro_que_llega_tarde_entra_y_se_ve_aparte(entorno):
    """Un cobro hecho sin señal que se sincroniza despues del cierre no se
    pierde: entra, y el cierre dice cuanto llego despues."""
    jefa, cobra, d, _ = entorno
    r = cobra.post("/cobros/registrar", data={"cuota_id": d["cuotas"][1],
                                              "valor_cobrado": "30000", "metodo_pago": "Efectivo"})
    assert r.status_code == 200, r.text
    assert _cuadre(jefa, d)["cierre"]["despues"] == 30000.0


def test_la_pantalla_trae_el_cierre():
    html = Path("templates/caja.html").read_text(encoding="utf-8")
    for pieza in ("id=\"card-cierre\"", "declararCierre(", "confirmarCierre(",
                  "Llegaron cobros después del cierre"):
        assert pieza in html, pieza
