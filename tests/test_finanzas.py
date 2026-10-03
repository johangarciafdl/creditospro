"""Las cuentas del dueño: ciclos de 6 semanas, reparto y caja general.

Escenario con numeros redondos para poder hacer la cuenta a mano:

- Ciclo 1: empieza hace 50 dias, asi que ya termino (42 dias) y el ciclo 2
  esta en curso.
- Zona Norte: un prestamo de 100.000 al 20 % (120.000), desembolsado dentro
  del ciclo 1, con 60.000 cobrados en el ciclo. Interes = 60.000 * 1/6 = 10.000.
- Zona Sur: un prestamo de 300.000 al 20 % (360.000), con 360.000 cobrados en
  el ciclo pero desembolsado ANTES del ciclo. Interes = 60.000.
- Un gasto de 20.000 del cobrador dentro del ciclo.

  cobrado 420.000 - prestado 100.000 - gastos 20.000 = resultado 300.000
  intereses 70.000 - gastos 20.000 = ganancia 50.000
"""
import datetime
import json
import tempfile
from decimal import Decimal
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="module")
def entorno():
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    bd = Path(tempfile.gettempdir()) / "creditospro_finanzas_test.db"
    if bd.exists():
        bd.unlink()

    from app.database import (Base, Cliente, Cobro, Cuota, CuadreSemanal, Empresa,
                              Prestamo, Usuario, Zona, hoy_local)
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
    # Los ciclos empiezan un domingo (sus semanas son las del cuadre semanal).
    hace50 = hoy - datetime.timedelta(days=50)
    inicio = hace50 - datetime.timedelta(days=(hace50.weekday() + 1) % 7)
    en_ciclo1 = inicio + datetime.timedelta(days=10)
    d = {"hoy": hoy, "inicio": inicio, "en_ciclo1": en_ciclo1}
    db = Sesion()
    try:
        e = Empresa(nombre="FinanzasSA", activa=True)
        db.add(e); db.flush()
        d["empresa_id"] = e.id
        d["clave"] = assign_company_key(db, e)
        norte = Zona(empresa_id=e.id, codigo="FN", nombre="Norte")
        sur = Zona(empresa_id=e.id, codigo="FS", nombre="Sur")
        db.add_all([norte, sur]); db.flush()
        admin = Usuario(empresa_id=e.id, username="finjefa", nombre="Fin Jefa", rol="admin",
                        activo=True, password_hash=get_password_hash("ClaveDePrueba123!"))
        cob = Usuario(empresa_id=e.id, username="fincobra", nombre="Fin Cobra", rol="cobrador",
                      activo=True, password_hash=get_password_hash("ClaveDePrueba123!"))
        db.add_all([admin, cob]); db.flush()
        cob.zonas_asignadas.extend([norte, sur])
        d["admin_id"], d["cobrador_id"] = admin.id, cob.id

        def prestamo(zona, capital, total, desembolso, cobrado):
            c = Cliente(empresa_id=e.id, cedula=f"10{capital}", nombre=f"Cliente {zona.nombre} Uno",
                        telefono="3001112233", zona_id=zona.id, activo=True)
            db.add(c); db.flush()
            p = Prestamo(empresa_id=e.id, cliente_id=c.id, zona_id=zona.id,
                         capital=Decimal(capital), tasa_interes=Decimal("20"),
                         total_pagar=Decimal(total), num_cuotas=1, valor_cuota=Decimal(total),
                         estado="Activo", fecha_inicio=desembolso, fecha_fin=hoy,
                         fecha_desembolso=desembolso, desembolsado_por_id=cob.id)
            db.add(p); db.flush()
            cu = Cuota(empresa_id=e.id, prestamo_id=p.id, numero=1, valor=Decimal(total),
                       valor_pagado=Decimal(cobrado), estado="Parcial", fecha_vencimiento=hoy)
            db.add(cu); db.flush()
            db.add(Cobro(empresa_id=e.id, cuota_id=cu.id, prestamo_id=p.id, cliente_id=c.id,
                         zona_id=zona.id, valor_cobrado=Decimal(cobrado), fecha=en_ciclo1,
                         usuario_id=cob.id))

        prestamo(norte, "100000", "120000", en_ciclo1, "60000")
        prestamo(sur, "300000", "360000", inicio - datetime.timedelta(days=5), "360000")
        # Los gastos salen del cuadre semanal verificado de la zona.
        db.add(CuadreSemanal(empresa_id=e.id, zona_id=norte.id,
                             semana=en_ciclo1 - datetime.timedelta(days=(en_ciclo1.weekday() + 1) % 7),
                             gastos=Decimal("20000")))
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
        cli.get("/finanzas")
        cli.headers["x-csrf-token"] = cli.cookies.get("cp_csrf", "")
        return cli

    jefa = entrar("finjefa")
    cobra = entrar("fincobra")
    yield jefa, cobra, d, Sesion
    for c in (jefa, cobra):
        c.__exit__(None, None, None)
    for clave in claves:
        app.dependency_overrides.pop(clave, None)
    motor.dispose()
    bd.unlink(missing_ok=True)


def _datos(cli, ciclo=0):
    r = cli.get("/finanzas/datos", params={"ciclo": ciclo} if ciclo else None)
    assert r.status_code == 200, r.text
    return r.json()


# ── Ciclos ─────────────────────────────────────────────────────────────────

def test_los_ciclos_son_bloques_de_6_semanas():
    from app.utils import finanzas as fz
    inicio = datetime.date(2026, 10, 5)
    assert fz.ciclo(inicio, 1) == (inicio, datetime.date(2026, 11, 15))
    assert fz.ciclo(inicio, 2)[0] == datetime.date(2026, 11, 16)
    assert fz.numero_de(inicio, datetime.date(2026, 11, 15)) == 1
    assert fz.numero_de(inicio, datetime.date(2026, 11, 16)) == 2
    assert fz.numero_de(inicio, datetime.date(2026, 10, 4)) == 0


def test_sin_configurar_no_hay_ciclos(entorno):
    jefa, _, _, _ = entorno
    assert _datos(jefa)["configurado"] is False


def test_solo_el_admin_ve_y_toca_las_finanzas(entorno):
    _, cobra, _, _ = entorno
    assert cobra.get("/finanzas/datos").status_code == 403
    assert cobra.post("/finanzas/config", data={"ciclo_inicio": "2026-01-01"}).status_code == 403
    assert cobra.get("/finanzas", follow_redirects=False).status_code == 302


def test_configurar_y_las_cuentas_del_ciclo(entorno):
    jefa, _, d, _ = entorno
    martes = d["inicio"] + datetime.timedelta(days=1)
    assert jefa.post("/finanzas/config", data={"ciclo_inicio": martes.isoformat()}).status_code == 400
    r = jefa.post("/finanzas/config", data={"ciclo_inicio": d["inicio"].isoformat()})
    assert r.status_code == 200, r.text
    datos = _datos(jefa, 1)
    c = datos["ciclo"]
    assert [x["estado"] for x in datos["ciclos"]] == ["en_curso", "por_cerrar"]
    assert c["cobrado"] == 420000.0
    assert c["prestado"] == 100000.0          # el de Sur salio antes del ciclo
    assert c["gastos"] == 20000.0
    assert c["intereses"] == 70000.0          # 10.000 + 60.000
    assert c["resultado"] == 300000.0
    assert c["ganancia"] == 50000.0
    zonas = {z["zona"]: z for z in c["zonas"]}
    assert zonas["Norte"]["intereses"] == 10000.0 and zonas["Norte"]["flujo"] == -40000.0
    assert zonas["Sur"]["intereses"] == 60000.0 and zonas["Sur"]["flujo"] == 360000.0
    assert c["se_puede_cerrar"] is True


def test_el_ciclo_en_curso_no_se_cierra(entorno):
    jefa, _, _, _ = entorno
    r = jefa.post("/finanzas/ciclo/2/cerrar", data={})
    assert r.status_code == 400 and "termin" in r.json()["error"]


# ── Caja general ───────────────────────────────────────────────────────────

def test_la_caja_general_se_activa_una_vez(entorno):
    jefa, _, _, _ = entorno
    assert _datos(jefa)["caja"]["activa"] is False
    r = jefa.post("/finanzas/caja/movimiento", data={"tipo": "retiro", "valor": "1000"})
    assert r.status_code == 400, "sin saldo inicial no se anota nada"
    assert jefa.post("/finanzas/caja/inicial", data={"valor": "1.000.000"}).status_code == 200
    assert jefa.post("/finanzas/caja/inicial", data={"valor": "5"}).status_code == 400
    k = _datos(jefa)["caja"]
    assert k["activa"] and k["caja"] == 1000000.0 and k["reserva"] == 0.0


def test_la_caja_general_suma_el_efectivo_de_los_cuadres(entorno):
    """Desde que se activa, cada cuadre semanal verificado suma el efectivo
    que devolvio la zona y resta la base que se llevo."""
    jefa, _, d, Sesion = entorno
    from app.database import CuadreSemanal, MovimientoCajaGeneral, ahora_utc
    from app.utils import finanzas as fz
    db = Sesion()
    try:
        antes = fz.caja_general(db, d["empresa_id"], d["hoy"])["caja"]
        db.add(CuadreSemanal(empresa_id=d["empresa_id"], zona_id=1, semana=d["hoy"],
                             base=Decimal("500000"), efectivo=Decimal("650000"),
                             verificado_en=ahora_utc() + datetime.timedelta(seconds=5)))
        db.flush()
        k = fz.caja_general(db, d["empresa_id"], d["hoy"])
        assert k["entregas"] - k["bases"] == Decimal("150000")
        assert k["caja"] == antes + Decimal("150000")
        db.rollback()
        assert db.query(MovimientoCajaGeneral).count() == 1
    finally:
        db.close()

def test_movimientos_a_mano_y_reserva(entorno):
    jefa, _, _, _ = entorno
    for tipo, valor in (("aporte", "200000"), ("a_reserva", "100000"), ("retiro", "50000")):
        r = jefa.post("/finanzas/caja/movimiento", data={"tipo": tipo, "valor": valor,
                                                        "concepto": "prueba de caja"})
        assert r.status_code == 200, r.text
    k = _datos(jefa)["caja"]
    assert k["caja"] == 1000000 + 200000 - 100000 - 50000
    assert k["reserva"] == 100000
    assert jefa.post("/finanzas/caja/movimiento", data={"tipo": "saldo_inicial",
                                                       "valor": "1"}).status_code == 400
    # El saldo inicial no se retira; un aporte si.
    movs = k["movimientos"]
    inicial = next(m for m in movs if m["tipo"] == "saldo_inicial")
    aporte = next(m for m in movs if m["tipo"] == "aporte")
    assert jefa.post(f"/finanzas/caja/movimiento/{inicial['id']}/borrar").status_code == 400
    assert jefa.post(f"/finanzas/caja/movimiento/{aporte['id']}/borrar").status_code == 200
    assert _datos(jefa)["caja"]["caja"] == 1000000 - 100000 - 50000


# ── El reparto y el cierre ────────────────────────────────────────────────

def test_el_reparto_tiene_que_sumar_el_resultado(entorno):
    jefa, _, d, _ = entorno
    r = jefa.post("/finanzas/ciclo/1/cerrar", data={
        "base": "100000", "retiro": "100000", "reserva": "0", "pagos": "{}"})
    assert r.status_code == 400 and "Deben ser iguales" in r.json()["error"]
    r = jefa.post("/finanzas/ciclo/1/cerrar", data={
        "base": "0", "retiro": "0", "reserva": "0",
        "pagos": json.dumps({"999999": 300000})})
    assert r.status_code == 400, "un cobrador de otra empresa"


def test_cerrar_el_ciclo_reparte_y_queda_fijo(entorno):
    jefa, _, d, _ = entorno
    antes = _datos(jefa)["caja"]["caja"]
    r = jefa.post("/finanzas/ciclo/1/cerrar", data={
        "base": "100000", "retiro": "120000", "reserva": "50000",
        "pagos": json.dumps({str(d["cobrador_id"]): 30000})})
    assert r.status_code == 200, r.text
    datos = _datos(jefa, 1)
    c = datos["ciclo"]
    assert c["cerrado"] is True and c["resultado"] == 300000.0
    assert c["reparto"]["retiro"] == 120000.0 and c["reparto"]["base"] == 100000.0
    assert c["reparto"]["pagos"][0]["valor"] == 30000.0
    assert [x["estado"] for x in datos["ciclos"]] == ["en_curso", "cerrado"]
    # Sale de la caja: retiro + reserva + pago. La base se queda.
    k = datos["caja"]
    assert k["caja"] == antes - 120000 - 50000 - 30000
    assert k["reserva"] == 100000 + 50000
    # Lo que salio de un cierre no se retira a mano.
    del_cierre = [m for m in k["movimientos"] if m["de_liquidacion"]]
    assert len(del_cierre) == 3
    assert jefa.post(f"/finanzas/caja/movimiento/{del_cierre[0]['id']}/borrar").status_code == 400
    # No se cierra dos veces, ni se mueve la fecha de inicio.
    assert jefa.post("/finanzas/ciclo/1/cerrar", data={}).status_code == 400
    assert jefa.post("/finanzas/config", data={"ciclo_inicio": "2026-01-01"}).status_code == 400


def test_el_ciclo_cerrado_no_cambia_si_se_toca_un_cobro_viejo(entorno):
    """La liquidacion guarda la foto: corregir despues un cobro no reescribe
    lo que ya se repartio."""
    jefa, _, d, Sesion = entorno
    from app.database import Cobro
    db = Sesion()
    try:
        cobro = db.query(Cobro).filter(Cobro.empresa_id == d["empresa_id"]).first()
        cobro.valor_cobrado = Decimal("1")
        db.commit()
    finally:
        db.close()
    assert _datos(jefa, 1)["ciclo"]["cobrado"] == 420000.0


def test_la_pantalla_existe_y_esta_en_el_menu(entorno):
    jefa, cobra, _, _ = entorno
    html = jefa.get("/finanzas").text
    assert 'id="sel-ciclo"' in html and "cerrarCiclo" in html and "activarCaja" in html
    assert 'href="/finanzas"' in jefa.get("/dashboard").text
    assert 'href="/finanzas"' not in cobra.get("/caja").text
