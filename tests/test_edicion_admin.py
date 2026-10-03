"""Correcciones del admin: cobros, prestamos y clientes.

Un prestamo de 100.000 al 20 % = 120.000 en 4 cuotas de 30.000.
"""
import datetime
import tempfile
from decimal import Decimal
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def entorno():
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    bd = Path(tempfile.gettempdir()) / "creditospro_edicion_test.db"
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
        e = Empresa(nombre="EdicionSA", activa=True)
        db.add(e); db.flush()
        d["clave"] = assign_company_key(db, e)
        z = Zona(empresa_id=e.id, codigo="ED", nombre="Centro")
        db.add(z); db.flush()
        d["zona"] = z.id
        for u, rol in (("edjefa", "admin"), ("edcobra", "cobrador")):
            usr = Usuario(empresa_id=e.id, username=u, nombre=u.title(), rol=rol, activo=True,
                          password_hash=get_password_hash("ClaveDePrueba123!"))
            db.add(usr); db.flush()
            if rol == "cobrador":
                usr.zonas_asignadas.append(z)
        c = Cliente(empresa_id=e.id, cedula="1000501", nombre="Edith Prueba", telefono="3001112233",
                    zona_id=z.id, activo=True)
        db.add(c); db.flush()
        d["cliente"] = c.id
        p = Prestamo(empresa_id=e.id, cliente_id=c.id, zona_id=z.id, capital=Decimal("100000"),
                     tasa_interes=Decimal("20"), total_pagar=Decimal("120000"), num_cuotas=4,
                     valor_cuota=Decimal("30000"), plazo_dias=1, estado="Activo",
                     fecha_inicio=hoy - datetime.timedelta(days=4), fecha_fin=hoy)
        db.add(p); db.flush()
        d["prestamo"] = p.id
        d["cuotas"] = []
        for n in range(4):
            cu = Cuota(empresa_id=e.id, prestamo_id=p.id, numero=n + 1, valor=Decimal("30000"),
                       valor_pagado=Decimal("0"), estado="Pendiente",
                       fecha_vencimiento=hoy - datetime.timedelta(days=3 - n))
            db.add(cu); db.flush()
            d["cuotas"].append(cu.id)
        db.commit()
    finally:
        db.close()

    def entrar(u):
        vaciar_limitador()
        cli = TestClient(app)
        cli.__enter__()
        assert cli.post("/license/activate", data={"license_key": d["clave"]}).status_code == 200
        assert cli.post("/auth/login", data={"username": u, "password": "ClaveDePrueba123!"}).status_code == 200
        cli.get("/ruta")
        cli.headers["x-csrf-token"] = cli.cookies.get("cp_csrf", "")
        return cli

    jefa, cobra = entrar("edjefa"), entrar("edcobra")
    yield jefa, cobra, d, Sesion
    for c in (jefa, cobra):
        c.__exit__(None, None, None)
    for k in claves:
        app.dependency_overrides.pop(k, None)
    motor.dispose()
    bd.unlink(missing_ok=True)


def _cobrar(cli, d, i, valor):
    r = cli.post("/cobros/registrar", data={"cuota_id": d["cuotas"][i], "valor_cobrado": str(valor),
                                            "metodo_pago": "Efectivo"})
    assert r.status_code == 200, r.text


def _pagados(Sesion, d):
    from app.database import Cuota
    db = Sesion()
    try:
        return [(int(c.valor_pagado), c.estado) for c in
                db.query(Cuota).filter(Cuota.prestamo_id == d["prestamo"]).order_by(Cuota.numero)]
    finally:
        db.close()


def _cobro_ids(Sesion, d):
    from app.database import Cobro
    db = Sesion()
    try:
        return [c.id for c in db.query(Cobro).filter(Cobro.prestamo_id == d["prestamo"]).order_by(Cobro.id)]
    finally:
        db.close()


def test_corregir_un_cobro_rehace_las_cuotas(entorno):
    jefa, cobra, d, Sesion = entorno
    _cobrar(cobra, d, 0, 30000)
    _cobrar(cobra, d, 1, 30000)
    segundo = _cobro_ids(Sesion, d)[1]
    r = jefa.post(f"/admin/cobros/{segundo}/editar", data={"valor": "20.000"})
    assert r.status_code == 200, r.text
    assert _pagados(Sesion, d)[:2] == [(30000, "Pagada"), (20000, "Parcial")]


def test_eliminar_un_cobro(entorno):
    jefa, cobra, d, Sesion = entorno
    _cobrar(cobra, d, 0, 45000)                 # cubre la 1 y la mitad de la 2
    assert _pagados(Sesion, d)[1][0] == 15000
    r = jefa.post(f"/admin/cobros/{_cobro_ids(Sesion, d)[0]}/eliminar")
    assert r.status_code == 200, r.text
    assert all(p == 0 for p, _ in _pagados(Sesion, d))


def test_lo_pagado_sin_cobro_se_conserva(entorno):
    """Lo importado (pagado sin cobro registrado) no se pierde al corregir."""
    jefa, cobra, d, Sesion = entorno
    from app.database import Cuota
    db = Sesion()
    try:
        cu = db.get(Cuota, d["cuotas"][0])
        cu.valor_pagado, cu.estado = Decimal("30000"), "Pagada"
        db.commit()
    finally:
        db.close()
    _cobrar(cobra, d, 1, 30000)
    r = jefa.post(f"/admin/cobros/{_cobro_ids(Sesion, d)[0]}/editar", data={"valor": "10000"})
    assert r.status_code == 200, r.text
    assert _pagados(Sesion, d)[:2] == [(30000, "Pagada"), (10000, "Parcial")]


def test_corregir_el_prestamo_rehace_el_plan_y_respeta_lo_pagado(entorno):
    jefa, cobra, d, Sesion = entorno
    _cobrar(cobra, d, 0, 50000)
    r = jefa.post(f"/admin/prestamos/{d['prestamo']}/editar", data={
        "capital": "100.000", "tasa_interes": "20", "num_cuotas": "2", "plazo_dias": "1",
        "fecha_inicio": (d["hoy"] - datetime.timedelta(days=2)).isoformat()})
    assert r.status_code == 200, r.text
    pagados = _pagados(Sesion, d)
    assert len(pagados) == 2 and pagados[0] == (50000, "Parcial")
    # Bajar el prestamo por debajo de lo pagado no se permite.
    r = jefa.post(f"/admin/prestamos/{d['prestamo']}/editar", data={
        "capital": "30000", "tasa_interes": "0", "num_cuotas": "1", "plazo_dias": "1",
        "fecha_inicio": d["hoy"].isoformat()})
    assert r.status_code == 400 and "supera" in r.json()["error"]


def test_anular_un_prestamo_lo_saca_de_la_ruta_pero_conserva_sus_cobros(entorno):
    jefa, cobra, d, Sesion = entorno
    from app.database import Cobro, Prestamo
    _cobrar(cobra, d, 0, 30000)
    r = jefa.post(f"/admin/prestamos/{d['prestamo']}/anular", data={"motivo": "registrado por error"})
    assert r.status_code == 200, r.text
    db = Sesion()
    try:
        p = db.get(Prestamo, d["prestamo"])
        assert p.estado == "Anulado" and p.anulado_por and p.motivo_anulacion
        assert db.query(Cobro).filter(Cobro.prestamo_id == p.id).count() == 1
    finally:
        db.close()
    assert [c for _, c in _pagados(Sesion, d)] == ["Pagada", "Anulada", "Anulada", "Anulada"]
    tarjeta = cobra.get("/ruta/zona", params={"zona_id": d["zona"]}).json()["clientes"][0]
    assert tarjeta["prestamos"] == [] and tarjeta["estado"] == "gris"
    assert cobra.get("/cobros/pendientes-ajax", params={"zona_id": d["zona"]}).json()["pendientes"] == []
    assert jefa.post(f"/admin/prestamos/{d['prestamo']}/anular", data={}).status_code == 400


def test_retirar_un_cliente(entorno):
    jefa, cobra, d, Sesion = entorno
    from app.database import Cliente, Prestamo
    r = jefa.post(f"/admin/clientes/{d['cliente']}/retirar", data={"motivo": "se fue de la zona"})
    assert r.status_code == 200 and "1 préstamo" in r.json()["mensaje"], r.text
    db = Sesion()
    try:
        c = db.get(Cliente, d["cliente"])
        assert c.activo is False and c.motivo_retiro == "Se fue de la zona"
        assert db.get(Prestamo, d["prestamo"]).estado == "Anulado"
    finally:
        db.close()
    assert cobra.get("/ruta/zona", params={"zona_id": d["zona"]}).json()["clientes"] == []


def test_solo_el_admin_corrige(entorno):
    _, cobra, d, Sesion = entorno
    _cobrar(cobra, d, 0, 30000)
    cid = _cobro_ids(Sesion, d)[0]
    for url, datos in ((f"/admin/cobros/{cid}/editar", {"valor": "1"}),
                       (f"/admin/cobros/{cid}/eliminar", {}),
                       (f"/admin/prestamos/{d['prestamo']}/anular", {}),
                       (f"/admin/clientes/{d['cliente']}/retirar", {})):
        assert cobra.post(url, data=datos).status_code == 403, url


def test_la_ficha_ofrece_las_correcciones_solo_al_admin(entorno):
    jefa, cobra, d, _ = entorno
    _cobrar(cobra, d, 0, 30000)
    del_admin = jefa.get(f"/clientes/{d['cliente']}").text
    del_cobrador = cobra.get(f"/clientes/{d['cliente']}").text
    for pieza in ("retirarCliente()", "abrirEditarPrestamo(", "anularPrestamo(", "editarCobro(",
                  'id="modal-editar-prestamo"'):
        assert pieza in del_admin, pieza
        assert pieza not in del_cobrador.split("<script")[0], pieza


def test_el_tablero_no_cuenta_lo_anulado(entorno):
    jefa, _, d, Sesion = entorno
    from app.utils.tablero import tablero_zona
    assert jefa.post(f"/admin/prestamos/{d['prestamo']}/anular", data={}).status_code == 200
    db = Sesion()
    try:
        from app.database import Zona
        t = tablero_zona(db, db.get(Zona, d["zona"]).empresa_id, d["zona"], d["hoy"])
        assert t["saldo_total"] == 0 and t["cartera"]["clientes"] == 0
    finally:
        db.close()
