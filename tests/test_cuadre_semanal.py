"""El cuadre semanal por zona (admin) y el comprobante por WhatsApp.

El cuadre reemplaza al cierre diario: el admin cuadra cada zona una vez por
semana. Calcular no guarda; Verificar guarda y deja fijo; Reabrir lo deshace
(salvo que la semana este en un ciclo de 6 semanas cerrado).
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


def test_el_cobro_devuelve_el_comprobante_para_whatsapp(entorno):
    """El texto lo arma el servidor con las cifras despues del cobro; el
    cobrador decide si lo manda, desde su WhatsApp."""
    _, cobra, d, _ = entorno
    for i in (0, 1):
        assert cobra.post("/cobros/registrar", data={
            "cuota_id": d["cuotas"][i], "valor_cobrado": "30000",
            "metodo_pago": "Efectivo"}).status_code == 200
    r = cobra.post("/cobros/registrar", data={"cuota_id": d["cuotas"][2],
                                              "valor_cobrado": "30000", "metodo_pago": "Efectivo"})
    assert r.status_code == 200, r.text
    c = r.json()["comprobante"]
    assert c["whatsapp"] == "573001112233"
    assert "$30.000" in c["texto"] and "cuota 3 de 4" in c["texto"]
    # 120.000 - 30.000 x 3 cobradas = 30.000
    assert "Te faltan $30.000" in c["texto"]
    assert "CierreSA" in c["texto"]
    js = Path("templates/_modal_cobro_js.html").read_text(encoding="utf-8")
    assert "ofrecerComprobante(d.comprobante)" in js and "https://wa.me/" in js



# ── Cuadre semanal ────────────────────────────────────────────────────────

def _lunes(d):
    """El domingo con que empieza la semana (el cuadre se hace los sabados)."""
    from app.utils.cuadre_semanal import inicio_semana
    return inicio_semana(d["hoy"])


def _form(d, **v):
    base = {"zona_id": d["zona"], "semana": _lunes(d).isoformat(), "cobro": "90000",
            "prestamos": "0", "gastos": "10000", "salarios": "20000", "base": "500000",
            "descuento": "5000", "efectivo": "550000"}
    base.update(v)
    return base


def test_el_sistema_propone_cobro_y_prestamos_de_la_semana(entorno):
    jefa, _, d, _ = entorno
    r = jefa.get("/caja/semanal/datos", params={"zona_id": d["zona"]})
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["semana"] == _lunes(d).isoformat() and j["verificado"] is None
    assert j["propuesta"]["cobro"] == 90000.0         # los 3 cobros del comprobante
    assert j["propuesta"]["prestamos"] == 0.0
    assert len(j["semanas"]) == 8


def test_calcular_no_guarda_nada(entorno):
    jefa, _, d, Sesion = entorno
    from app.database import CuadreSemanal
    r = jefa.post("/caja/semanal/calcular", data=_form(d))
    assert r.status_code == 200, r.text
    c = r.json()["calculo"]
    # 500.000 + 90.000 - 0 - 10.000 - 20.000 - 5.000 = 555.000
    assert c["esperado"] == 555000.0 and c["diferencia"] == -5000.0
    # 90.000 cobrados de un prestamo de 100.000 al 20 %: 1/6 es interes = 15.000
    assert c["intereses"] == 15000.0 and c["utilidad"] == 15000.0 - 35000.0
    db = Sesion()
    try:
        assert db.query(CuadreSemanal).count() == 0
    finally:
        db.close()


def test_solo_el_admin_cuadra(entorno):
    _, cobra, d, _ = entorno
    assert cobra.post("/caja/semanal/verificar", data=_form(d)).status_code == 403
    assert cobra.get("/caja/semanal/datos", params={"zona_id": d["zona"]}).status_code == 403


def test_verificar_guarda_y_deja_fijo(entorno):
    jefa, _, d, _ = entorno
    r = jefa.post("/caja/semanal/verificar", data=_form(d, nota="semana normal"))
    assert r.status_code == 200 and "faltante de 5.000" in r.json()["mensaje"], r.text
    v = jefa.get("/caja/semanal/datos", params={"zona_id": d["zona"]}).json()["verificado"]
    assert v["efectivo"] == 550000.0 and v["diferencia"] == -5000.0 and v["nota"] == "Semana normal"
    assert jefa.post("/caja/semanal/verificar", data=_form(d)).status_code == 409


def test_reabrir_para_corregir(entorno):
    jefa, _, d, Sesion = entorno
    from app.database import AuditLog
    r = jefa.post("/caja/semanal/reabrir", data={"zona_id": d["zona"],
                                                 "semana": _lunes(d).isoformat()})
    assert r.status_code == 200, r.text
    assert jefa.get("/caja/semanal/datos", params={"zona_id": d["zona"]}).json()["verificado"] is None
    db = Sesion()
    try:
        assert db.query(AuditLog).filter(AuditLog.action == "cuadre_semanal_reabierto").count() == 1
    finally:
        db.close()
    assert jefa.post("/caja/semanal/verificar", data=_form(d, efectivo="555000")).status_code == 200


def test_no_se_reabre_una_semana_de_un_ciclo_cerrado(entorno):
    jefa, _, d, Sesion = entorno
    from app.database import Liquidacion
    db = Sesion()
    try:
        db.add(Liquidacion(empresa_id=d["empresa_id"], numero=99, desde=_lunes(d),
                           hasta=_lunes(d) + datetime.timedelta(days=41)))
        db.commit()
    finally:
        db.close()
    r = jefa.post("/caja/semanal/reabrir", data={"zona_id": d["zona"],
                                                 "semana": _lunes(d).isoformat()})
    assert r.status_code == 409


def test_la_pantalla_del_cuadre():
    html = Path("templates/caja_semanal.html").read_text(encoding="utf-8")
    for pieza in ("f-cobro", "f-prestamos", "f-gastos", "f-salarios", "f-base", "f-descuento",
                  "f-efectivo", "/caja/semanal/calcular", "/caja/semanal/verificar", "reabrir("):
        assert pieza in html, pieza
