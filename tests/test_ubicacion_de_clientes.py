"""La posicion de cada cliente, deducida de sus visitas, y la ruta por cercania.

Casi ningun cliente tiene direccion ni coordenadas en su ficha, asi que la
ruta por cercania se apoya en el GPS de las visitas: cobros, visitas sin pago
y el alta desde la calle. Aqui se comprueba que esas tres vias guardan la
posicion, que un GPS malo nunca impide guardar la visita, que la posicion
deducida resiste a un punto raro (mediana, no media), y que la ruta la entrega
fila por fila sin tocar la ficha de clientes que ya existian.
"""
import datetime
import tempfile
from decimal import Decimal
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.utils.ubicacion import distancia_m, leer_coordenadas, posiciones_de_clientes

# Un punto de Medellin y otros a pocas cuadras.
LAT, LNG = 6.2442, -75.5812


# ── leer_coordenadas ──────────────────────────────────────────────────────

@pytest.mark.parametrize("lat,lng,esperado", [
    ("6.2442", "-75.5812", (6.2442, -75.5812)),
    (6.2442, -75.5812, (6.2442, -75.5812)),
    ("", "", (None, None)),
    ("6.2442", "", (None, None)),          # media coordenada no situa nada
    ("abc", "-75.5", (None, None)),
    ("95", "-75.5", (None, None)),         # fuera de rango
    ("6.2", "-190", (None, None)),
    ("0", "0", (None, None)),              # la "isla nula" de los GPS sin senal
    (None, None, (None, None)),
])
def test_leer_coordenadas(lat, lng, esperado):
    assert leer_coordenadas(lat, lng) == esperado


def test_distancia_de_una_cuadra():
    # ~0.001 grados de latitud son ~111 m
    d = distancia_m(LAT, LNG, LAT + 0.001, LNG)
    assert 105 < d < 117


# ── Entorno con base propia ───────────────────────────────────────────────

@pytest.fixture(scope="module")
def entorno():
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    bd = Path(tempfile.gettempdir()) / "creditospro_ubicacion_test.db"
    if bd.exists():
        bd.unlink()

    from app.database import (Base, Cliente, Cuota, Empresa, Prestamo, Usuario,
                              Zona, hoy_local)
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
        e = Empresa(nombre="UbicaSA", activa=True)
        db.add(e); db.flush()
        d["empresa_id"] = e.id
        d["clave"] = assign_company_key(db, e)
        z = Zona(empresa_id=e.id, codigo="UZ1", nombre="Centro")
        db.add(z); db.flush()
        d["zona"] = z.id

        cobrador = Usuario(empresa_id=e.id, username="ubicobra", nombre="Ubi Cobra",
                           rol="cobrador", activo=True,
                           password_hash=get_password_hash("ClaveDePrueba123!"))
        db.add(cobrador); db.flush()
        cobrador.zonas_asignadas.append(z)

        def _cliente_con_cuota(nombre, cedula, **extra):
            c = Cliente(empresa_id=e.id, cedula=cedula, nombre=nombre,
                        telefono="3001112233", zona_id=z.id, activo=True, **extra)
            db.add(c); db.flush()
            p = Prestamo(empresa_id=e.id, cliente_id=c.id, zona_id=z.id,
                         capital=Decimal("100000"), tasa_interes=Decimal("20"),
                         total_pagar=Decimal("120000"), num_cuotas=2,
                         valor_cuota=Decimal("60000"), estado="Activo",
                         fecha_inicio=hoy - datetime.timedelta(days=30),
                         fecha_fin=hoy + datetime.timedelta(days=30))
            db.add(p); db.flush()
            cu = Cuota(empresa_id=e.id, prestamo_id=p.id, numero=1,
                       valor=Decimal("60000"), valor_pagado=Decimal("0"),
                       estado="Pendiente", fecha_vencimiento=hoy)
            db.add(cu); db.flush()
            return c, p, cu

        c, p, cu = _cliente_con_cuota("Visitado ConGPS", "U1")
        d["visitado"], d["prestamo_visitado"], d["cuota_visitado"] = c.id, p.id, cu.id
        c, _, cu = _cliente_con_cuota("Ficha ConPosicion", "U2", lat=6.25, lng=-75.59)
        d["con_ficha"], d["cuota_ficha"] = c.id, cu.id
        c, _, cu = _cliente_con_cuota("Nadie SabeDonde", "U3")
        d["sin_posicion"], d["cuota_sin_posicion"] = c.id, cu.id
        db.commit()
    finally:
        db.close()

    vaciar_limitador()
    cli = TestClient(app)
    cli.__enter__()
    assert cli.post("/license/activate", data={"license_key": d["clave"]}).status_code == 200
    assert cli.post("/auth/login", data={"username": "ubicobra",
                                         "password": "ClaveDePrueba123!"}).status_code == 200
    cli.get("/ruta")
    cli.headers["x-csrf-token"] = cli.cookies.get("cp_csrf", "")
    yield cli, d, Sesion

    cli.__exit__(None, None, None)
    for clave in claves:
        app.dependency_overrides.pop(clave, None)
    motor.dispose()
    bd.unlink(missing_ok=True)


def _no_pago(cli, cuota_id, **extra):
    datos = {"cuota_id": cuota_id, "motivo": "no estaba"}
    datos.update(extra)
    r = cli.post("/cobros/no-pago", data=datos)
    assert r.status_code == 200, r.text
    assert r.json().get("ok"), r.text
    return r.json()


def test_la_visita_sin_pago_guarda_el_gps(entorno):
    cli, d, Sesion = entorno
    from app.database import NoPago
    _no_pago(cli, d["cuota_visitado"], lat=str(LAT), lng=str(LNG))
    db = Sesion()
    try:
        np = db.query(NoPago).filter(NoPago.cuota_id == d["cuota_visitado"]).one()
        assert (np.lat, np.lng) == (LAT, LNG)
    finally:
        db.close()


def test_la_visita_sin_pago_sin_gps_o_con_gps_malo_se_guarda_igual(entorno):
    """Un GPS que no contesta no puede impedir dejar constancia."""
    cli, d, Sesion = entorno
    from app.database import NoPago
    _no_pago(cli, d["cuota_sin_posicion"], lat="basura", lng="")
    db = Sesion()
    try:
        np = db.query(NoPago).filter(NoPago.cuota_id == d["cuota_sin_posicion"]).one()
        assert np.lat is None and np.lng is None
    finally:
        db.close()


def test_la_ruta_trae_la_posicion_y_cuantos_hay_ubicados(entorno):
    cli, d, _ = entorno
    r = cli.get("/ruta/zona", params={"zona_id": d["zona"]})
    assert r.status_code == 200, r.text
    cuerpo = r.json()
    filas = {f["cliente_id"]: f for f in cuerpo["clientes"]}
    assert (filas[d["visitado"]]["lat"], filas[d["visitado"]]["lng"]) == (LAT, LNG)
    assert (filas[d["con_ficha"]]["lat"], filas[d["con_ficha"]]["lng"]) == (6.25, -75.59)
    assert filas[d["sin_posicion"]]["lat"] is None
    assert filas[d["sin_posicion"]]["lng"] is None
    assert cuerpo["resumen"]["ubicados"] == 2
    assert cuerpo["resumen"]["clientes"] == 3


def test_la_posicion_es_la_mediana_y_un_punto_raro_no_la_mueve(entorno):
    """Un cobro registrado luego desde la casa del cobrador no arrastra la
    posicion del cliente a medio camino."""
    _, d, Sesion = entorno
    from app.database import Cobro, Cuota
    db = Sesion()
    try:
        cu = db.get(Cuota, d["cuota_visitado"])
        base = datetime.datetime(2026, 9, 1, 12, 0)
        puntos = [(LAT + 0.0001, LNG), (LAT - 0.0001, LNG), (LAT, LNG + 0.0001),
                  (LAT + 0.05, LNG + 0.05)]           # el ultimo, a kilometros
        for i, (la, lo) in enumerate(puntos):
            db.add(Cobro(empresa_id=d["empresa_id"], cuota_id=cu.id,
                         prestamo_id=cu.prestamo_id, cliente_id=d["visitado"],
                         zona_id=d["zona"], valor_cobrado=Decimal("1000"),
                         hora=base + datetime.timedelta(hours=i),
                         lat_cobro=la, lng_cobro=lo))
        db.flush()
        pos = posiciones_de_clientes(db, d["empresa_id"], [d["visitado"]])[d["visitado"]]
        assert pos["fuente"] == "visitas"
        assert pos["visitas"] == 5                  # 4 cobros + la visita sin pago
        assert distancia_m(pos["lat"], pos["lng"], LAT, LNG) < 30
        db.rollback()                               # no deja cobros de prueba
    finally:
        db.close()


def test_la_ficha_manda_sobre_las_visitas(entorno):
    _, d, Sesion = entorno
    from app.database import NoPago, Cuota
    db = Sesion()
    try:
        cu = db.get(Cuota, d["cuota_ficha"])
        db.add(NoPago(empresa_id=d["empresa_id"], cuota_id=cu.id,
                      prestamo_id=cu.prestamo_id, cliente_id=d["con_ficha"],
                      zona_id=d["zona"], fecha=d["hoy"], lat=7.0, lng=-74.0))
        db.flush()
        pos = posiciones_de_clientes(db, d["empresa_id"], [d["con_ficha"]])[d["con_ficha"]]
        assert (pos["lat"], pos["lng"], pos["fuente"]) == (6.25, -75.59, "ficha")
        db.rollback()
    finally:
        db.close()


def test_solo_las_ultimas_visitas_cuentan(entorno):
    """Si el cliente se mudo, las visitas viejas dejan de pesar."""
    _, d, Sesion = entorno
    from app.database import Cobro, Cuota
    from app.utils.ubicacion import VISITAS_POR_CLIENTE
    db = Sesion()
    try:
        cu = db.get(Cuota, d["cuota_sin_posicion"])
        viejo = datetime.datetime(2025, 1, 1, 12, 0)
        nuevo = datetime.datetime(2026, 9, 1, 12, 0)
        for i in range(VISITAS_POR_CLIENTE * 2):          # la casa vieja
            db.add(Cobro(empresa_id=d["empresa_id"], cuota_id=cu.id,
                         prestamo_id=cu.prestamo_id, cliente_id=d["sin_posicion"],
                         zona_id=d["zona"], valor_cobrado=Decimal("100"),
                         hora=viejo + datetime.timedelta(minutes=i),
                         lat_cobro=5.0, lng_cobro=-74.0))
        for i in range(VISITAS_POR_CLIENTE):              # la casa nueva
            db.add(Cobro(empresa_id=d["empresa_id"], cuota_id=cu.id,
                         prestamo_id=cu.prestamo_id, cliente_id=d["sin_posicion"],
                         zona_id=d["zona"], valor_cobrado=Decimal("100"),
                         hora=nuevo + datetime.timedelta(minutes=i),
                         lat_cobro=LAT, lng_cobro=LNG))
        db.flush()
        pos = posiciones_de_clientes(db, d["empresa_id"], [d["sin_posicion"]])[d["sin_posicion"]]
        assert (pos["lat"], pos["lng"]) == (LAT, LNG)
        assert pos["visitas"] == VISITAS_POR_CLIENTE
        db.rollback()
    finally:
        db.close()


def test_el_punto_desde_donde_se_cobra_a_muchos_no_ubica_a_nadie(entorno):
    """Si el cobrador registra los pagos desde su casa, ese punto no es la
    casa de esos clientes: se descarta, y quedan sin ubicar."""
    _, d, Sesion = entorno
    from app.database import Cliente, Cobro, Cuota
    from app.utils.ubicacion import CLIENTES_POR_PUNTO_SOSPECHOSO
    db = Sesion()
    try:
        cu = db.get(Cuota, d["cuota_visitado"])
        oficina = (6.3179, -75.5579)
        ids = []
        for i in range(CLIENTES_POR_PUNTO_SOSPECHOSO):
            c = Cliente(empresa_id=d["empresa_id"], cedula=f"OF{i}", nombre=f"Oficina {i}",
                        telefono="3000000000", zona_id=d["zona"], activo=True)
            db.add(c); db.flush()
            ids.append(c.id)
            # unos metros de baile del GPS, como en la realidad
            db.add(Cobro(empresa_id=d["empresa_id"], cuota_id=cu.id,
                         prestamo_id=cu.prestamo_id, cliente_id=c.id, zona_id=d["zona"],
                         valor_cobrado=Decimal("100"),
                         lat_cobro=oficina[0] + i * 0.00003, lng_cobro=oficina[1]))
        # Y uno de ellos tiene ademas visitas reales en su puerta.
        for k in range(3):
            db.add(Cobro(empresa_id=d["empresa_id"], cuota_id=cu.id,
                         prestamo_id=cu.prestamo_id, cliente_id=ids[0], zona_id=d["zona"],
                         valor_cobrado=Decimal("100"), lat_cobro=LAT, lng_cobro=LNG))
        db.flush()
        pos = posiciones_de_clientes(db, d["empresa_id"], ids)
        assert set(pos) == {ids[0]}, "los demas solo tienen el punto de la oficina"
        assert (pos[ids[0]]["lat"], pos[ids[0]]["lng"]) == (LAT, LNG)
        db.rollback()
    finally:
        db.close()


def test_dos_vecinos_en_el_mismo_punto_si_se_ubican(entorno):
    """Por debajo del umbral es una casa compartida o un conjunto, no la
    oficina: se respeta."""
    _, d, Sesion = entorno
    from app.database import Cliente, Cobro, Cuota
    db = Sesion()
    try:
        cu = db.get(Cuota, d["cuota_visitado"])
        ids = []
        for i in range(2):
            c = Cliente(empresa_id=d["empresa_id"], cedula=f"VE{i}", nombre=f"Vecino {i}",
                        telefono="3000000000", zona_id=d["zona"], activo=True)
            db.add(c); db.flush()
            ids.append(c.id)
            db.add(Cobro(empresa_id=d["empresa_id"], cuota_id=cu.id,
                         prestamo_id=cu.prestamo_id, cliente_id=c.id, zona_id=d["zona"],
                         valor_cobrado=Decimal("100"), lat_cobro=6.30, lng_cobro=-75.50))
        db.flush()
        assert set(posiciones_de_clientes(db, d["empresa_id"], ids)) == set(ids)
        db.rollback()
    finally:
        db.close()


def test_no_mezcla_visitas_de_otra_empresa(entorno):
    _, d, Sesion = entorno
    db = Sesion()
    try:
        assert posiciones_de_clientes(db, d["empresa_id"] + 999, [d["visitado"]]) == {}
        assert posiciones_de_clientes(db, d["empresa_id"], []) == {}
    finally:
        db.close()


def test_el_cliente_creado_en_la_calle_guarda_donde_se_creo(entorno):
    cli, d, Sesion = entorno
    from app.database import Cliente
    r = cli.post("/clientes/nuevo", data={
        "cedula": "U900", "nombre": "Nuevo EnLaCalle", "telefono": "3005556677",
        "zona_id": str(d["zona"]), "lat": "6.2501", "lng": "-75.5701"})
    assert r.status_code == 200 and r.json().get("ok"), r.text
    db = Sesion()
    try:
        c = db.query(Cliente).filter(Cliente.cedula == "U900").one()
        assert (c.lat, c.lng) == (6.2501, -75.5701)
    finally:
        db.close()


def test_prestar_a_un_cliente_nuevo_guarda_la_posicion(entorno):
    cli, d, Sesion = entorno
    from app.database import Cliente
    r = cli.post("/ruta/prestar", data={
        "zona_id": d["zona"], "capital": "100000", "tasa_interes": "20",
        "num_cuotas": "20", "plazo_dias": "1",
        "cedula": "U901", "nombre": "Prestado EnLaCalle", "telefono": "3005556678",
        "lat": "6.2601", "lng": "-75.5601"})
    assert r.status_code == 200 and r.json().get("ok"), r.text
    db = Sesion()
    try:
        c = db.query(Cliente).filter(Cliente.cedula == "U901").one()
        assert (c.lat, c.lng) == (6.2601, -75.5601)
    finally:
        db.close()


def test_prestar_a_un_cliente_que_ya_existe_no_toca_su_ficha(entorno):
    """La posicion solo se pone al crear: corregir una ficha es del admin."""
    cli, d, Sesion = entorno
    from app.database import Cliente
    r = cli.post("/ruta/prestar", data={
        "zona_id": d["zona"], "capital": "100000", "tasa_interes": "20",
        "num_cuotas": "20", "plazo_dias": "1",
        "cliente_id": str(d["con_ficha"]), "lat": "1.0", "lng": "-70.0"})
    assert r.status_code == 200, r.text
    db = Sesion()
    try:
        c = db.get(Cliente, d["con_ficha"])
        assert (c.lat, c.lng) == (6.25, -75.59)
    finally:
        db.close()


# ── La pantalla ───────────────────────────────────────────────────────────

def test_la_vista_simple_trae_la_ruta_por_cercania(entorno):
    cli, _, _ = entorno
    html = Path("templates/app_cobrador.html").read_text(encoding="utf-8")
    for pieza in ("alternarCercania", "ordenarPorCercania", "_ordenarParadas",
                  "google.com/maps/dir/?api=1&destination=",
                  "window.MODAL_CON_NO_PAGO = true", "_anexarPosAlta(fd)"):
        assert pieza in html, f"falta {pieza}"


def test_las_pantallas_clasicas_no_encienden_el_no_pago_del_modal():
    """Cobros y Clientes ya tienen su boton; ahi el modal queda como estaba."""
    for plantilla in Path("templates").glob("*.html"):
        if plantilla.name == "app_cobrador.html":
            continue
        assert "MODAL_CON_NO_PAGO = true" not in plantilla.read_text(encoding="utf-8"), \
            plantilla.name
