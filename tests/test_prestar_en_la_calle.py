"""El cobrador registra al cliente y le presta, en una sola peticion.

Los dos pasos van juntos a proposito. Si fueran dos peticiones, una senal que
se cae entre medias deja un cliente dado de alta sin el prestamo que
justificaba darlo de alta, y el cobrador -- en la calle, con el cliente
delante -- no sabe si repetir o no. Por eso lo primero que se comprueba aqui
es que un prestamo que falla no deje al cliente creado.

La otra mitad es la linea que el usuario trazo: **dar de alta si, corregir
no**. El cobrador puede registrar a alguien que no existia; sobre alguien que
ya existia, le presta y punto -- sus datos no se tocan aunque los mande.
"""
import datetime
import tempfile
from decimal import Decimal
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="module")
def entorno():
    """Un cobrador con una zona suya y otra que no lo es."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    bd = Path(tempfile.gettempdir()) / "creditospro_prestar_test.db"
    if bd.exists():
        bd.unlink()

    from app.database import Base, Cliente, Empresa, Usuario, Zona, hoy_local
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

    d = {"hoy": hoy_local()}
    db = Sesion()
    try:
        e = Empresa(nombre="CalleSA", activa=True)
        db.add(e); db.flush()
        d["empresa_id"] = e.id
        d["clave"] = assign_company_key(db, e)

        suya = Zona(empresa_id=e.id, codigo="CA1", nombre="Suya")
        ajena = Zona(empresa_id=e.id, codigo="CA2", nombre="Ajena")
        db.add_all([suya, ajena]); db.flush()
        d["zona"], d["zona_ajena"] = suya.id, ajena.id

        u = Usuario(empresa_id=e.id, username="calle", nombre="Calle Cobra",
                    rol="cobrador", activo=True,
                    password_hash=get_password_hash("ClaveDePrueba123!"))
        db.add(u); db.flush()
        u.zonas_asignadas.append(suya)        # la otra NO es suya
        d["usuario_id"] = u.id

        c = Cliente(empresa_id=e.id, cedula="7001", nombre="Cliente Viejo",
                    telefono="3001112233", direccion="Calle Vieja 1",
                    zona_id=suya.id, activo=True)
        db.add(c); db.flush()
        d["cliente_id"] = c.id

        fuera = Cliente(empresa_id=e.id, cedula="7002", nombre="Cliente Ajeno",
                        telefono="3004445566", zona_id=ajena.id, activo=True)
        db.add(fuera); db.flush()
        d["cliente_ajeno"] = fuera.id
        db.commit()
    finally:
        db.close()

    vaciar_limitador()
    cli = TestClient(app)
    cli.__enter__()
    assert cli.post("/license/activate",
                    data={"license_key": d["clave"]}).status_code == 200
    assert cli.post("/auth/login", data={"username": "calle",
                                         "password": "ClaveDePrueba123!"}
                    ).status_code == 200
    cli.get("/ruta")
    cli.headers["x-csrf-token"] = cli.cookies.get("cp_csrf", "")
    yield cli, d, Sesion

    cli.__exit__(None, None, None)
    for clave in claves:
        app.dependency_overrides.pop(clave, None)
    motor.dispose()
    bd.unlink(missing_ok=True)


def _prestar(cli, d, **extra):
    datos = {"zona_id": d["zona"], "capital": "300000", "tasa_interes": "20",
             "num_cuotas": "30", "plazo_dias": "1"}
    datos.update(extra)
    return cli.post("/ruta/prestar", data=datos)


# ── Un cliente nuevo ──────────────────────────────────────────────────────

def test_da_de_alta_al_cliente_y_le_presta_en_una(entorno):
    cli, d, Sesion = entorno
    from app.database import Cliente, Cuota, Prestamo

    r = _prestar(cli, d, cedula="8001", nombre="Persona Nueva",
                 telefono="3009998877", direccion="Carrera 5")
    assert r.status_code == 200, r.text
    cuerpo = r.json()
    assert cuerpo["ok"] and cuerpo["cliente_nuevo"] is True

    db = Sesion()
    try:
        c = db.query(Cliente).filter(Cliente.cedula == "8001").first()
        assert c is not None and c.zona_id == d["zona"]
        p = db.query(Prestamo).filter(Prestamo.cliente_id == c.id).first()
        assert p is not None
        assert p.desembolsado_por_id == d["usuario_id"], "no salio de su caja"
        assert p.fecha_desembolso == d["hoy"]
        assert db.query(Cuota).filter(Cuota.prestamo_id == p.id).count() == 30
    finally:
        db.close()


def test_un_prestamo_que_falla_no_deja_al_cliente_creado(entorno):
    """Es la razon de que los dos pasos vayan en una sola peticion."""
    cli, d, Sesion = entorno
    from app.database import Cliente

    # 0 cuotas: el prestamo no se puede calcular.
    r = _prestar(cli, d, cedula="8002", nombre="No Debe Quedar",
                 telefono="3001110000", num_cuotas="0")
    assert r.status_code == 400, r.text
    db = Sesion()
    try:
        assert db.query(Cliente).filter(Cliente.cedula == "8002").first() is None, \
            "el prestamo fallo y el cliente se quedo creado"
    finally:
        db.close()


def test_una_cedula_repetida_no_crea_un_duplicado(entorno):
    """Le dice quien es para que preste sobre ese, en vez de dejarle dos
    fichas del mismo señor que despues nadie sabe cual es."""
    cli, d, Sesion = entorno
    from app.database import Cliente

    r = _prestar(cli, d, cedula="7001", nombre="Otro Nombre",
                 telefono="3001112233")
    assert r.status_code == 409, r.text
    cuerpo = r.json()
    assert cuerpo["duplicado"] is True
    assert cuerpo["cliente_id"] == d["cliente_id"]
    db = Sesion()
    try:
        assert db.query(Cliente).filter(Cliente.cedula == "7001").count() == 1
    finally:
        db.close()


# La cedula admite letras y guiones a proposito (hay documentos que los
# llevan); lo que no admite es vacia, de dos caracteres, ni con simbolos.
@pytest.mark.parametrize("campo,valor", [
    ("cedula", ""), ("nombre", ""), ("telefono", ""),
    ("cedula", "ab"), ("cedula", "12/34 56!"),
])
def test_un_cliente_nuevo_sin_datos_validos_se_rechaza(entorno, campo, valor):
    cli, d, _ = entorno
    datos = {"cedula": "8100", "nombre": "Alguien", "telefono": "3001112222"}
    datos[campo] = valor
    r = _prestar(cli, d, **datos)
    assert r.status_code == 400, f"{campo}={valor!r} devolvio {r.status_code}"


# ── Un cliente que ya existia ────────────────────────────────────────────

def test_a_un_cliente_que_ya_existe_le_presta_sin_tocarle_los_datos(entorno):
    """La linea: dar de alta si, corregir no. Aunque mande datos nuevos."""
    cli, d, Sesion = entorno
    from app.database import Cliente, Prestamo

    r = _prestar(cli, d, cliente_id=d["cliente_id"],
                 nombre="NOMBRE CAMBIADO", telefono="3000000000",
                 direccion="OTRA DIRECCION")
    assert r.status_code == 200, r.text
    assert r.json()["cliente_nuevo"] is False

    db = Sesion()
    try:
        c = db.query(Cliente).filter(Cliente.id == d["cliente_id"]).first()
        assert c.nombre == "Cliente Viejo", "le cambio el nombre al prestarle"
        assert c.direccion == "Calle Vieja 1", "le cambio la direccion"
        assert c.telefono == "3001112233", "le cambio el telefono"
        p = db.query(Prestamo).filter(
            Prestamo.cliente_id == d["cliente_id"]).order_by(Prestamo.id.desc()).first()
        assert p is not None and p.desembolsado_por_id == d["usuario_id"]
    finally:
        db.close()


# ── La zona manda ────────────────────────────────────────────────────────

def test_no_puede_prestar_en_una_zona_que_no_es_suya(entorno):
    cli, d, Sesion = entorno
    from app.database import Cliente
    r = _prestar(cli, d, zona_id=d["zona_ajena"], cedula="8300",
                 nombre="En Zona Ajena", telefono="3001112222")
    assert r.status_code == 403, f"devolvio {r.status_code}"
    db = Sesion()
    try:
        assert db.query(Cliente).filter(Cliente.cedula == "8300").first() is None
    finally:
        db.close()


def test_no_puede_prestarle_a_un_cliente_de_otra_zona(entorno):
    cli, d, Sesion = entorno
    from app.database import Prestamo
    db = Sesion()
    try:
        antes = db.query(Prestamo).filter(
            Prestamo.cliente_id == d["cliente_ajeno"]).count()
    finally:
        db.close()
    r = _prestar(cli, d, cliente_id=d["cliente_ajeno"])
    assert r.status_code == 403, f"devolvio {r.status_code}"
    db = Sesion()
    try:
        assert db.query(Prestamo).filter(
            Prestamo.cliente_id == d["cliente_ajeno"]).count() == antes
    finally:
        db.close()


def test_el_buscador_no_ofrece_clientes_de_zonas_que_no_cobra(entorno):
    """Ensenarselos le invita a prestar donde no le toca."""
    cli, d, _ = entorno
    r = cli.get("/ruta/buscar-cliente", params={"q": "Cliente"})
    assert r.status_code == 200, r.text
    ids = {c["id"] for c in r.json()["clientes"]}
    assert d["cliente_id"] in ids
    assert d["cliente_ajeno"] not in ids, "le ofrecio un cliente de otra zona"


def test_el_buscador_no_responde_a_dos_letras(entorno):
    """Con dos letras devolveria media empresa en el celular."""
    cli, _, _ = entorno
    assert cli.get("/ruta/buscar-cliente", params={"q": "Cl"}).json()["clientes"] == []


# ── El dinero y el aviso ─────────────────────────────────────────────────

def test_prestar_descuenta_de_su_caja_y_avisa_del_sobregiro(entorno):
    """Presta con lo que recoge: pasarse no se impide, pero se ve."""
    cli, d, Sesion = entorno
    from app.utils.caja import cuadre

    r = _prestar(cli, d, cedula="8400", nombre="Del Sobregiro",
                 telefono="3001112222", capital="250000")
    assert r.status_code == 200, r.text
    cuerpo = r.json()
    assert cuerpo.get("sobregiro", 0) > 0, "presto sin cobrar nada y no aviso"
    assert "sobregiro" in (cuerpo.get("aviso") or "").lower()

    db = Sesion()
    try:
        c = cuadre(db, d["empresa_id"], d["usuario_id"], d["hoy"])
        assert c["prestado"] >= 250000.0
        assert c["esperado"] < 0, "presto mas de lo que tenia y la caja no lo refleja"
    finally:
        db.close()


def test_sin_sesion_no_se_presta(entorno):
    from app.main import app
    with TestClient(app) as anon:
        r = anon.post("/ruta/prestar", data={"zona_id": 1, "capital": "1000",
                                             "num_cuotas": "2"},
                      follow_redirects=False)
        assert r.status_code in (302, 401, 403), f"devolvio {r.status_code}"
