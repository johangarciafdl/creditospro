"""El cuadre de caja: cuanto dinero deberia tener encima el cobrador.

    esperado = base + cobrado - gastos - prestado - entregado +/- ajustes

Lo que se vigila aqui, por orden de lo que costaria caro:

1. Que la cuenta sea la cuenta. Un cuadre que suma donde deberia restar no
   falla nunca: le cuadra a quien no deberia, y eso solo se descubre contando
   billetes semanas despues.
2. Que el cobrador NO pueda escribir su propia caja. Si puede anotarse la
   base, cualquier dia le cuadra -- seria pedirle la cuenta a quien la rinde.
3. Que si pueda VER la suya. Si solo la viera el administrador, el cobrador
   se enteraria de que va descuadrado cuando ya no puede reconstruir el dia.
4. Que el desembolso de un prestamo se le descuente a la caja de quien
   entrego el dinero, no a la de quien aprobo el prestamo desde la oficina.
"""
import datetime
import tempfile
from decimal import Decimal
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="module")
def entorno():
    """Una empresa con dos cobradores y un admin; y otra empresa aparte."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    bd = Path(tempfile.gettempdir()) / "creditospro_caja_test.db"
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
        e = Empresa(nombre="CajaSA", activa=True)
        db.add(e); db.flush()
        d["empresa_id"] = e.id
        d["clave"] = assign_company_key(db, e)

        z = Zona(empresa_id=e.id, codigo="CZ1", nombre="Centro")
        db.add(z); db.flush()
        d["zona_id"] = z.id

        for usuario, rol, etiqueta in (("jefacaja", "admin", "admin"),
                                       ("luis", "cobrador", "luis"),
                                       ("marta", "cobrador", "marta")):
            u = Usuario(empresa_id=e.id, username=usuario, nombre=usuario.title(),
                        rol=rol, activo=True,
                        password_hash=get_password_hash("ClaveDePrueba123!"))
            db.add(u); db.flush()
            if rol == "cobrador":
                u.zonas_asignadas.append(z)
            d[etiqueta + "_id"] = u.id

        c = Cliente(empresa_id=e.id, cedula="CJ1", nombre="Cliente Caja",
                    telefono="3001112233", zona_id=z.id, activo=True)
        db.add(c); db.flush()
        d["cliente_id"] = c.id

        p = Prestamo(empresa_id=e.id, cliente_id=c.id, zona_id=z.id,
                     capital=Decimal("200000"), tasa_interes=Decimal("20"),
                     total_pagar=Decimal("240000"), num_cuotas=4,
                     valor_cuota=Decimal("60000"), estado="Activo",
                     fecha_inicio=hoy - datetime.timedelta(days=10),
                     fecha_fin=hoy + datetime.timedelta(days=20))
        db.add(p); db.flush()
        for numero, dias in ((1, -3), (2, 0), (3, 4), (4, 8)):
            db.add(Cuota(empresa_id=e.id, prestamo_id=p.id, numero=numero,
                         valor=Decimal("60000"), valor_pagado=Decimal("0"),
                         estado="Pendiente",
                         fecha_vencimiento=hoy + datetime.timedelta(days=dias)))
        db.flush()
        d["cuotas"] = [c_.id for c_ in db.query(Cuota).filter(
            Cuota.prestamo_id == p.id).order_by(Cuota.numero).all()]

        # Otra empresa, para comprobar que nadie mira la caja de fuera.
        e2 = Empresa(nombre="OtraCajaSA", activa=True)
        db.add(e2); db.flush()
        d["empresa_b"] = e2.id
        d["clave_b"] = assign_company_key(db, e2)
        u2 = Usuario(empresa_id=e2.id, username="ajenocaja", nombre="Ajeno",
                     rol="admin", activo=True,
                     password_hash=get_password_hash("ClaveDePrueba123!"))
        db.add(u2); db.flush()
        d["ajeno_id"] = u2.id
        db.commit()
    finally:
        db.close()

    def entrar(clave, usuario):
        vaciar_limitador()
        cli = TestClient(app)
        cli.__enter__()
        assert cli.post("/license/activate",
                        data={"license_key": clave}).status_code == 200
        assert cli.post("/auth/login", data={"username": usuario,
                                             "password": "ClaveDePrueba123!"}
                        ).status_code == 200, f"{usuario} no pudo entrar"
        cli.get("/caja")
        cli.headers["x-csrf-token"] = cli.cookies.get("cp_csrf", "")
        return cli

    sesiones = {
        "admin": entrar(d["clave"], "jefacaja"),
        "luis": entrar(d["clave"], "luis"),
        "marta": entrar(d["clave"], "marta"),
        "ajeno": entrar(d["clave_b"], "ajenocaja"),
    }
    yield sesiones, d, Sesion

    for cli in sesiones.values():
        cli.__exit__(None, None, None)
    for clave in claves:
        app.dependency_overrides.pop(clave, None)
    motor.dispose()
    bd.unlink(missing_ok=True)


@pytest.fixture(autouse=True)
def caja_limpia(entorno):
    """Cada prueba parte de una caja vacia: si no, el cuadre de una se suma
    al de la siguiente y los numeros dejan de significar nada."""
    _, d, Sesion = entorno
    from app.database import Cobro, Cuota, MovimientoCaja, Prestamo
    db = Sesion()
    try:
        db.query(MovimientoCaja).delete()
        db.query(Cobro).delete()
        # Y las cuotas como estaban. Borrar solo los cobros dejaba la cuota
        # marcada como pagada, asi que el cobro de la prueba siguiente se
        # rechazaba y "cobrado" salia en cero -- un cero que parece un fallo
        # del cuadre y es un fallo del montaje.
        db.query(Cuota).update({"valor_pagado": Decimal("0"), "estado": "Pendiente",
                                "fecha_pago": None})
        db.query(Prestamo).filter(Prestamo.desembolsado_por_id.isnot(None)).update(
            {"desembolsado_por_id": None, "fecha_desembolso": None})
        db.commit()
    finally:
        db.close()
    yield


def _cuadre(cli, d, usuario_id=None, fecha=None):
    params = {"fecha": (fecha or d["hoy"]).isoformat()}
    if usuario_id:
        params["usuario_id"] = usuario_id
    r = cli.get("/caja/resumen", params=params)
    assert r.status_code == 200, r.text
    return r.json()


def _anotar(cli, d, usuario_id, tipo, valor, fecha=None, concepto=""):
    return cli.post("/caja/movimiento", data={
        "usuario_id": usuario_id, "tipo": tipo, "valor": str(valor),
        "fecha": (fecha or d["hoy"]).isoformat(), "concepto": concepto,
    })


# ── La cuenta es la cuenta ────────────────────────────────────────────────

def test_una_caja_sin_movimiento_esta_en_cero(entorno):
    """Y nada se descuenta solo: todo lo que sale tiene su linea escrita."""
    s, d, _ = entorno
    c = _cuadre(s["luis"], d)["cuadre"]
    assert c["esperado"] == 0.0
    assert c["gastos"] == 0.0
    assert c["hubo_movimiento"] is False


def test_la_base_entra_entera_y_no_se_descuenta_nada_solo(entorno):
    """Antes habia un viatico fijo que se restaba sin que nadie lo escribiera.

    Se quito: un automatismo que resta dinero sin dejar linea es imposible de
    cuadrar el dia que no fue como siempre -- el que no salio, el que almorzo
    en casa, el que gasto el doble en transporte.
    """
    s, d, _ = entorno
    assert _anotar(s["admin"], d, d["luis_id"], "base", 500000).status_code == 200
    c = _cuadre(s["admin"], d, d["luis_id"])["cuadre"]
    assert c["base"] == 500000.0
    assert c["gastos"] == 0.0, "nada se descuenta hasta que alguien lo anote"
    assert c["esperado"] == 500000.0


def test_lo_cobrado_suma_y_lo_entregado_resta(entorno):
    s, d, _ = entorno
    _anotar(s["admin"], d, d["luis_id"], "base", 500000)
    r = s["luis"].post("/cobros/registrar", data={
        "cuota_id": d["cuotas"][0], "valor_cobrado": "60000",
        "metodo_pago": "Efectivo"})
    assert r.status_code == 200, r.text
    _anotar(s["admin"], d, d["luis_id"], "entrega", 300000)

    c = _cuadre(s["admin"], d, d["luis_id"])["cuadre"]
    assert c["cobrado"] == 60000.0 and c["num_cobros"] == 1
    assert c["entregado"] == 300000.0
    # 500.000 + 60.000 - 300.000
    assert c["esperado"] == 260000.0


def test_los_ajustes_van_en_el_sentido_que_dicen(entorno):
    """Un ajuste guardado con el signo dentro del numero se equivoca callado."""
    s, d, _ = entorno
    _anotar(s["admin"], d, d["luis_id"], "base", 100000)
    _anotar(s["admin"], d, d["luis_id"], "ajuste_mas", 20000, concepto="le faltaron")
    _anotar(s["admin"], d, d["luis_id"], "ajuste_menos", 5000, concepto="le sobraron")
    c = _cuadre(s["admin"], d, d["luis_id"])["cuadre"]
    assert c["ajustes"] == 15000.0
    assert c["esperado"] == 115000.0


def test_cada_cobrador_tiene_su_propia_caja(entorno):
    """La base de Luis no puede aparecer en la caja de Marta."""
    s, d, _ = entorno
    _anotar(s["admin"], d, d["luis_id"], "base", 500000)
    assert _cuadre(s["admin"], d, d["luis_id"])["cuadre"]["base"] == 500000.0
    assert _cuadre(s["admin"], d, d["marta_id"])["cuadre"]["base"] == 0.0


def test_la_caja_es_de_un_dia_y_no_se_arrastra(entorno):
    s, d, _ = entorno
    ayer = d["hoy"] - datetime.timedelta(days=1)
    _anotar(s["admin"], d, d["luis_id"], "base", 400000, fecha=ayer)
    assert _cuadre(s["admin"], d, d["luis_id"], fecha=ayer)["cuadre"]["base"] == 400000.0
    assert _cuadre(s["admin"], d, d["luis_id"])["cuadre"]["base"] == 0.0


# ── El desembolso sale de la caja de quien entrega, no de quien aprueba ───

def test_el_prestamo_se_descuenta_de_la_caja_de_quien_entrega(entorno):
    """El admin aprueba desde la oficina; los billetes los pone el cobrador."""
    s, d, Sesion = entorno
    from app.database import Prestamo

    _anotar(s["admin"], d, d["luis_id"], "base", 500000)
    r = s["admin"].post("/prestamos/nuevo", data={
        "cliente_id": d["cliente_id"], "zona_id": d["zona_id"],
        "capital": "150000", "tasa_interes": "20", "num_cuotas": "4",
        "plazo_dias": "7", "fecha_inicio": d["hoy"].isoformat(),
        "desembolsado_por": d["luis_id"],
    })
    assert r.status_code == 200, r.text
    assert r.json().get("ok"), r.text

    db = Sesion()
    try:
        p = db.query(Prestamo).order_by(Prestamo.id.desc()).first()
        assert p.desembolsado_por_id == d["luis_id"]
        assert p.fecha_desembolso == d["hoy"]
    finally:
        db.close()

    luis = _cuadre(s["admin"], d, d["luis_id"])["cuadre"]
    assert luis["prestado"] == 150000.0 and luis["num_prestamos"] == 1
    assert luis["esperado"] == 350000.0

    # Y al admin, que lo aprobo, no le toca la caja.
    admin = _cuadre(s["admin"], d, d["admin_id"])["cuadre"]
    assert admin["prestado"] == 0.0


def test_un_prestamo_sin_quien_lo_entregue_no_descuadra_a_nadie(entorno):
    """Los prestamos de antes de esta funcion no tienen desembolso atribuido."""
    s, d, _ = entorno
    _anotar(s["admin"], d, d["luis_id"], "base", 500000)
    r = s["admin"].post("/prestamos/nuevo", data={
        "cliente_id": d["cliente_id"], "zona_id": d["zona_id"],
        "capital": "90000", "tasa_interes": "20", "num_cuotas": "4",
        "plazo_dias": "7", "fecha_inicio": d["hoy"].isoformat(),
    })
    assert r.status_code == 200, r.text
    for quien in ("luis_id", "marta_id", "admin_id"):
        assert _cuadre(s["admin"], d, d[quien])["cuadre"]["prestado"] == 0.0


def test_no_se_puede_desembolsar_a_nombre_de_otra_empresa(entorno):
    s, d, _ = entorno
    r = s["admin"].post("/prestamos/nuevo", data={
        "cliente_id": d["cliente_id"], "zona_id": d["zona_id"],
        "capital": "70000", "tasa_interes": "20", "num_cuotas": "4",
        "plazo_dias": "7", "fecha_inicio": d["hoy"].isoformat(),
        "desembolsado_por": d["ajeno_id"],
    })
    assert r.status_code == 404, f"devolvio {r.status_code}: {r.text[:200]}"


# ── El sobregiro se ve ────────────────────────────────────────────────────

def test_prestar_mas_de_lo_cobrado_avisa_en_el_momento(entorno):
    """La regla del negocio: se presta con lo que se recoge. Pasarse no se
    impide, pero el admin tiene que enterarse ahora y no al cuadrar."""
    s, d, _ = entorno
    _anotar(s["admin"], d, d["luis_id"], "base", 500000)
    s["luis"].post("/cobros/registrar", data={
        "cuota_id": d["cuotas"][0], "valor_cobrado": "40000",
        "metodo_pago": "Efectivo"})

    r = s["admin"].post("/prestamos/nuevo", data={
        "cliente_id": d["cliente_id"], "zona_id": d["zona_id"],
        "capital": "100000", "tasa_interes": "20", "num_cuotas": "4",
        "plazo_dias": "7", "fecha_inicio": d["hoy"].isoformat(),
        "desembolsado_por": d["luis_id"],
    })
    assert r.status_code == 200, r.text
    cuerpo = r.json()
    assert cuerpo.get("ok"), "el prestamo debe crearse igualmente"
    assert cuerpo.get("sobregiro") == 60000.0, cuerpo
    assert "sobregiro" in (cuerpo.get("aviso") or "").lower()

    c = _cuadre(s["admin"], d, d["luis_id"])["cuadre"]
    assert c["sobregiro"] is True and c["sobregiro_valor"] == 60000.0


def test_prestar_menos_de_lo_cobrado_no_avisa(entorno):
    s, d, _ = entorno
    _anotar(s["admin"], d, d["luis_id"], "base", 500000)
    s["luis"].post("/cobros/registrar", data={
        "cuota_id": d["cuotas"][0], "valor_cobrado": "60000",
        "metodo_pago": "Efectivo"})
    r = s["admin"].post("/prestamos/nuevo", data={
        "cliente_id": d["cliente_id"], "zona_id": d["zona_id"],
        "capital": "50000", "tasa_interes": "20", "num_cuotas": "4",
        "plazo_dias": "7", "fecha_inicio": d["hoy"].isoformat(),
        "desembolsado_por": d["luis_id"],
    })
    assert r.status_code == 200, r.text
    assert "aviso" not in r.json(), r.json()
    assert _cuadre(s["admin"], d, d["luis_id"])["cuadre"]["sobregiro"] is False


# ── Quien puede mirar y quien puede escribir ─────────────────────────────

def test_el_cobrador_ve_su_propia_caja(entorno):
    """Si solo la viera el admin, se enteraria cuando ya no puede reconstruir
    el dia."""
    s, d, _ = entorno
    _anotar(s["admin"], d, d["luis_id"], "base", 500000)
    cuerpo = _cuadre(s["luis"], d)
    assert cuerpo["cuadre"]["base"] == 500000.0
    assert cuerpo["cuadre"]["usuario_id"] == d["luis_id"]


def test_el_cobrador_no_ve_la_caja_de_otro(entorno):
    s, d, _ = entorno
    r = s["luis"].get("/caja/resumen", params={"usuario_id": d["marta_id"],
                                               "fecha": d["hoy"].isoformat()})
    assert r.status_code == 403, f"devolvio {r.status_code}"


def test_el_cobrador_no_ve_el_cuadre_de_toda_la_empresa(entorno):
    """Sin usuario_id el admin recibe a todos; el cobrador, solo el suyo."""
    s, d, _ = entorno
    cuerpo = _cuadre(s["luis"], d)
    assert "cuadres" not in cuerpo, "le devolvio el cuadre de toda la empresa"
    assert cuerpo["cuadre"]["usuario_id"] == d["luis_id"]


def test_el_cobrador_no_puede_anotar_su_propia_base(entorno):
    """Si puede escribirse la base, cualquier dia le cuadra.

    Los gastos son la excepcion deliberada, y tienen sus propias pruebas
    mas abajo: la base no lo es."""
    s, d, Sesion = entorno
    from app.database import MovimientoCaja
    r = _anotar(s["luis"], d, d["luis_id"], "base", 500000)
    assert r.status_code == 403, f"devolvio {r.status_code}"
    db = Sesion()
    try:
        assert db.query(MovimientoCaja).count() == 0, "lo anoto igualmente"
    finally:
        db.close()


def test_el_cobrador_no_puede_borrar_un_movimiento(entorno):
    s, d, Sesion = entorno
    from app.database import MovimientoCaja
    _anotar(s["admin"], d, d["luis_id"], "entrega", 100000)
    db = Sesion()
    try:
        mid = db.query(MovimientoCaja).order_by(MovimientoCaja.id.desc()).first().id
    finally:
        db.close()
    r = s["luis"].post(f"/caja/movimiento/{mid}/borrar")
    assert r.status_code == 403, f"devolvio {r.status_code}"
    db = Sesion()
    try:
        assert db.query(MovimientoCaja).filter(MovimientoCaja.id == mid).count() == 1
    finally:
        db.close()


def test_el_admin_ve_el_cuadre_de_todos_los_cobradores(entorno):
    """Incluidos los que no se movieron: lo que el admin necesita saber por la
    tarde es justamente quien no ha entregado."""
    s, d, _ = entorno
    _anotar(s["admin"], d, d["luis_id"], "base", 500000)
    cuerpo = _cuadre(s["admin"], d)
    assert "cuadres" in cuerpo
    nombres = {c["nombre"] for c in cuerpo["cuadres"]}
    assert {"Luis", "Marta"} <= nombres, nombres
    marta = next(c for c in cuerpo["cuadres"] if c["nombre"] == "Marta")
    assert marta["hubo_movimiento"] is False


def test_el_admin_no_ve_ni_escribe_la_caja_de_otra_empresa(entorno):
    s, d, Sesion = entorno
    from app.database import MovimientoCaja
    r = s["admin"].get("/caja/resumen", params={"usuario_id": d["ajeno_id"],
                                                "fecha": d["hoy"].isoformat()})
    assert r.status_code == 404, f"devolvio {r.status_code}"
    r = _anotar(s["admin"], d, d["ajeno_id"], "base", 500000)
    assert r.status_code == 404, f"devolvio {r.status_code}"
    db = Sesion()
    try:
        assert db.query(MovimientoCaja).filter(
            MovimientoCaja.usuario_id == d["ajeno_id"]).count() == 0
    finally:
        db.close()


def test_sin_sesion_no_hay_caja(entorno):
    from app.main import app
    with TestClient(app) as anon:
        r = anon.get("/caja/resumen", follow_redirects=False)
        assert r.status_code in (302, 401), f"devolvio {r.status_code}"


# ── Lo que no se acepta ──────────────────────────────────────────────────

@pytest.mark.parametrize("valor", ["0", "-5000", "abc", ""])
def test_un_valor_que_no_es_dinero_se_rechaza(entorno, valor):
    s, d, _ = entorno
    r = _anotar(s["admin"], d, d["luis_id"], "base", valor)
    assert r.status_code == 400, f"'{valor}' devolvio {r.status_code}"


def test_un_valor_desmesurado_se_rechaza(entorno):
    """Un cero de mas al teclear descuadra el mes entero."""
    s, d, _ = entorno
    r = _anotar(s["admin"], d, d["luis_id"], "base", 900000000)
    assert r.status_code == 400


def test_un_tipo_inventado_se_rechaza(entorno):
    s, d, _ = entorno
    r = _anotar(s["admin"], d, d["luis_id"], "regalo", 1000)
    assert r.status_code == 400


def test_no_se_puede_anotar_ni_cuadrar_en_el_futuro(entorno):
    s, d, _ = entorno
    manana = d["hoy"] + datetime.timedelta(days=1)
    assert _anotar(s["admin"], d, d["luis_id"], "base", 1000,
                   fecha=manana).status_code == 400
    r = s["admin"].get("/caja/resumen", params={"usuario_id": d["luis_id"],
                                                "fecha": manana.isoformat()})
    assert r.status_code == 400


def test_una_fecha_invalida_se_rechaza(entorno):
    s, d, _ = entorno
    r = s["admin"].get("/caja/resumen", params={"usuario_id": d["luis_id"],
                                                "fecha": "el-martes"})
    assert r.status_code == 400


def test_borrar_un_movimiento_lo_saca_del_cuadre(entorno):
    s, d, Sesion = entorno
    from app.database import MovimientoCaja
    _anotar(s["admin"], d, d["luis_id"], "base", 500000)
    _anotar(s["admin"], d, d["luis_id"], "base", 500000, concepto="repetida")
    db = Sesion()
    try:
        mid = db.query(MovimientoCaja).order_by(MovimientoCaja.id.desc()).first().id
    finally:
        db.close()
    assert _cuadre(s["admin"], d, d["luis_id"])["cuadre"]["base"] == 1000000.0
    r = s["admin"].post(f"/caja/movimiento/{mid}/borrar")
    assert r.status_code == 200, r.text
    assert r.json()["cuadre"]["base"] == 500000.0


# ── La tabla nueva no se queda fuera de nada ─────────────────────────────

def test_la_tabla_nueva_tiene_su_politica_de_aislamiento():
    import pathlib
    sql = (pathlib.Path(__file__).resolve().parent.parent
           / "rls_policies.sql").read_text(encoding="utf-8")
    assert "ALTER TABLE movimientos_caja ENABLE ROW LEVEL SECURITY" in sql
    assert "empresa_isolation_movimientos_caja" in sql


def test_la_tabla_nueva_entra_en_el_respaldo():
    from app.services.respaldo import _nombre_tablas
    assert "movimientos_caja" in _nombre_tablas()


def test_hay_migracion_para_la_caja():
    import pathlib
    ruta = pathlib.Path(__file__).resolve().parent.parent / "alembic" / "versions"
    textos = [p.read_text(encoding="utf-8") for p in ruta.glob("*.py")]
    assert any("movimientos_caja" in t and "create_table" in t for t in textos), \
        "ninguna migracion crea movimientos_caja"
    assert any("desembolsado_por_id" in t and "add_column" in t for t in textos), \
        "ninguna migracion anade prestamos.desembolsado_por_id"


# ── La migracion tiene que poder repetirse ───────────────────────────────

def test_la_migracion_de_la_caja_se_puede_repetir():
    """El proveedor arranca dos contenedores a la vez y cada uno ejecuta
    `alembic upgrade head`.

    Los dos entran al mismo tiempo: uno crea la tabla y el otro se estrella
    con "la relacion ya existe". El que se estrella tumba el despliegue, y
    como el trabajo a medias no se deshace, todos los arranques siguientes
    mueren en el mismo sitio -- un bucle del que no se sale solo. Paso en
    produccion con esta misma migracion.

    Lo que se exige aqui no es el estilo sino la propiedad: ejecutarla dos
    veces seguidas tiene que terminar bien las dos.
    """
    import importlib.util
    import pathlib
    import tempfile

    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    from sqlalchemy import create_engine, inspect

    from app.database import Base

    ruta = (pathlib.Path(__file__).resolve().parent.parent / "alembic" / "versions"
            / "20260926_0021_caja_del_cobrador.py")
    spec = importlib.util.spec_from_file_location("migracion_caja", ruta)
    migracion = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migracion)

    bd = pathlib.Path(tempfile.gettempdir()) / "creditospro_migracion_caja.db"
    bd.unlink(missing_ok=True)
    motor = create_engine(f"sqlite:///{bd}")
    try:
        # Estado de partida: el esquema completo ya creado, que es justo el
        # caso en que la migracion se encuentra el trabajo hecho.
        Base.metadata.create_all(motor)
        with motor.connect() as cx:
            for _ in range(2):
                ctx = MigrationContext.configure(cx)
                with Operations.context(ctx):
                    migracion.upgrade()
            cx.commit()
        columnas = {c["name"] for c in inspect(motor).get_columns("prestamos")}
        assert {"desembolsado_por_id", "fecha_desembolso"} <= columnas
    finally:
        motor.dispose()
        bd.unlink(missing_ok=True)


# ── Los gastos los anota el cobrador, y solo los suyos ───────────────────

def test_el_cobrador_anota_su_propio_gasto(entorno):
    """La excepcion deliberada a "el cobrador ve su caja, no la escribe".

    Quien tuvo el gasto es el unico que sabe cuanto fue y cuando; hacerle
    esperar a que alguien en la oficina lo escriba le deja la caja
    descuadrada hasta el dia siguiente. El control no es impedirselo: es que
    cada gasto salga con su valor y su concepto donde el admin los ve.
    """
    s, d, _ = entorno
    _anotar(s["admin"], d, d["luis_id"], "base", 500000)
    r = _anotar(s["luis"], d, d["luis_id"], "gasto", 18000, concepto="almuerzo y bus")
    assert r.status_code == 200, r.text

    c = _cuadre(s["luis"], d)["cuadre"]
    assert c["gastos"] == 18000.0
    assert c["esperado"] == 482000.0
    gasto = [m for m in c["movimientos"] if m["tipo"] == "gasto"][0]
    assert gasto["concepto"] == "almuerzo y bus"
    assert gasto["efecto"] == -1, "un gasto resta"


def test_el_admin_ve_los_gastos_que_anoto_el_cobrador(entorno):
    """Si no los viera, anotarlos uno mismo seria un agujero y no un control."""
    s, d, _ = entorno
    _anotar(s["luis"], d, d["luis_id"], "gasto", 9000, concepto="transporte")
    c = _cuadre(s["admin"], d, d["luis_id"])["cuadre"]
    assert c["gastos"] == 9000.0
    assert any(m["concepto"] == "transporte" for m in c["movimientos"])


def test_el_cobrador_no_anota_gastos_en_la_caja_de_otro(entorno):
    s, d, Sesion = entorno
    from app.database import MovimientoCaja
    r = _anotar(s["luis"], d, d["marta_id"], "gasto", 50000)
    assert r.status_code == 403, f"devolvio {r.status_code}"
    db = Sesion()
    try:
        assert db.query(MovimientoCaja).filter(
            MovimientoCaja.usuario_id == d["marta_id"]).count() == 0
    finally:
        db.close()


def test_el_cobrador_retira_un_gasto_suyo_pero_no_una_base(entorno):
    """Un gasto mal tecleado lo arregla quien lo escribio; la base no la
    escribio el, asi que tampoco la borra."""
    s, d, Sesion = entorno
    from app.database import MovimientoCaja

    _anotar(s["luis"], d, d["luis_id"], "gasto", 7000, concepto="mal tecleado")
    _anotar(s["admin"], d, d["luis_id"], "base", 500000)
    db = Sesion()
    try:
        gasto = db.query(MovimientoCaja).filter(
            MovimientoCaja.tipo == "gasto").order_by(MovimientoCaja.id.desc()).first()
        base = db.query(MovimientoCaja).filter(
            MovimientoCaja.tipo == "base").order_by(MovimientoCaja.id.desc()).first()
        gid, bid = gasto.id, base.id
    finally:
        db.close()

    assert s["luis"].post(f"/caja/movimiento/{gid}/borrar").status_code == 200
    assert s["luis"].post(f"/caja/movimiento/{bid}/borrar").status_code == 403

    db = Sesion()
    try:
        assert db.query(MovimientoCaja).filter(MovimientoCaja.id == gid).count() == 0
        assert db.query(MovimientoCaja).filter(MovimientoCaja.id == bid).count() == 1
    finally:
        db.close()


def test_el_almuerzo_ya_no_se_descuenta_solo():
    """La regla vieja restaba 15.000 fijos sin que nadie los escribiera."""
    from app.utils import caja
    assert not hasattr(caja, "VIATICO_DIARIO"), \
        "el viatico automatico sigue en el codigo"
    assert "gasto" in caja.TIPOS
    assert caja.EFECTO["gasto"] == -1
