"""El interruptor de interfaz: la empresa elige que pantalla ve su cobrador.

Las restricciones de rol son las mismas en las dos interfaces (eso lo cubre
test_permisos_cobrador.py). Lo que se comprueba aqui es otra cosa: que el
interruptor exista, que lo mueva solo el admin, que solo afecte a su propia
empresa, y que mover el interruptor de una empresa no toque a la otra.

Las dos mitades que importan, y que es facil dejar a medias:

1. Que el cobrador acabe en la vista simple, y no solo que el menu deje de
   ofrecerle los modulos -- si el enlace desaparece pero la URL sigue
   abriendose, el interruptor no restringe nada, solo lo esconde.
2. Que al admin no le cambie NADA. Es la mitad que nadie prueba y la que
   dejaria a la empresa sin poder administrarse.
"""
import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="module")
def entorno():
    """Dos empresas con su admin y su cobrador en cada una."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    bd = Path(tempfile.gettempdir()) / "creditospro_interfaz_test.db"
    if bd.exists():
        bd.unlink()

    from app.database import Base, Cliente, Empresa, Usuario, Zona
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

    datos = {}
    db = Sesion()
    try:
        for etiqueta, nombre in (("A", "InterfazSA"), ("B", "OtraInterfazSA")):
            e = Empresa(nombre=nombre, activa=True)
            db.add(e); db.flush()
            clave = assign_company_key(db, e)
            z = Zona(empresa_id=e.id, codigo=f"IZ{e.id}", nombre=f"Zona {nombre}")
            db.add(z); db.flush()
            db.add(Cliente(empresa_id=e.id, cedula=f"IC{e.id}",
                           nombre=f"Cliente {nombre}", telefono="3000000000",
                           zona_id=z.id, activo=True))
            # En minusculas: el login normaliza el username a minusculas
            # antes de buscarlo, asi que "jefaA" nunca encontraria su fila.
            sufijo = etiqueta.lower()
            for usuario, rol in ((f"jefa{sufijo}", "admin"),
                                 (f"cobra{sufijo}", "cobrador")):
                u = Usuario(empresa_id=e.id, username=usuario,
                            nombre=usuario.title(), rol=rol, activo=True,
                            password_hash=get_password_hash("ClaveDePrueba123!"))
                db.add(u); db.flush()
                if rol == "cobrador":
                    u.zonas_asignadas.append(z)
            datos[etiqueta] = dict(empresa_id=e.id, clave=clave, zona_id=z.id)
        db.commit()
    finally:
        db.close()

    def entrar(etiqueta, usuario):
        # Cuatro sesiones seguidas en el mismo setup: sin vaciar el limitador,
        # la cuarta activacion se lleva un 429 del limite por IP.
        vaciar_limitador()
        cli = TestClient(app)
        cli.__enter__()
        r = cli.post("/license/activate",
                     data={"license_key": datos[etiqueta]["clave"]})
        assert r.status_code == 200, r.text
        r = cli.post("/auth/login", data={"username": usuario,
                                          "password": "ClaveDePrueba123!"})
        assert r.status_code == 200, f"{usuario} no pudo entrar"
        cli.get("/ruta")
        cli.headers["x-csrf-token"] = cli.cookies.get("cp_csrf", "")
        return cli

    sesiones = {
        "admin_a": entrar("A", "jefaa"),
        "cobra_a": entrar("A", "cobraa"),
        "admin_b": entrar("B", "jefab"),
        "cobra_b": entrar("B", "cobrab"),
    }
    yield sesiones, datos, Sesion

    for cli in sesiones.values():
        cli.__exit__(None, None, None)
    for clave in claves:
        app.dependency_overrides.pop(clave, None)
    motor.dispose()
    bd.unlink(missing_ok=True)


def _poner(Sesion, empresa_id, valor):
    """Escribe la columna directamente: el estado de partida de cada prueba."""
    from app.database import Empresa
    db = Sesion()
    try:
        db.query(Empresa).filter(Empresa.id == empresa_id).update(
            {"interfaz_cobrador": valor})
        db.commit()
    finally:
        db.close()


# ── El valor por defecto no cambia nada para quien ya operaba ──────────────

def test_una_empresa_nace_con_la_interfaz_completa(entorno):
    """El despliegue no debe mover a nadie de pantalla sin que se lo pidan."""
    _, d, Sesion = entorno
    from app.database import Empresa
    db = Sesion()
    try:
        for etiqueta in ("A", "B"):
            e = db.query(Empresa).filter(Empresa.id == d[etiqueta]["empresa_id"]).first()
            assert e.interfaz_cobrador == "completa"
    finally:
        db.close()


def test_un_valor_desconocido_se_lee_como_completa(entorno):
    """Una empresa nunca se queda sin pantalla por un dato raro en la columna."""
    s, d, Sesion = entorno
    _poner(Sesion, d["A"]["empresa_id"], "loquesea")
    try:
        r = s["cobra_a"].get("/dashboard", follow_redirects=False)
        assert r.status_code == 200, f"devolvio {r.status_code}"
    finally:
        _poner(Sesion, d["A"]["empresa_id"], "completa")


# ── Con "completa" todo sigue igual ────────────────────────────────────────

@pytest.mark.parametrize("ruta", ["/dashboard", "/clientes", "/cobros"])
def test_con_la_completa_el_cobrador_entra_a_los_modulos(entorno, ruta):
    s, d, Sesion = entorno
    _poner(Sesion, d["A"]["empresa_id"], "completa")
    r = s["cobra_a"].get(ruta, follow_redirects=False)
    assert r.status_code == 200, f"{ruta} devolvio {r.status_code}"


# ── Con "simple" el cobrador acaba en la vista unica ───────────────────────

@pytest.mark.parametrize("ruta", ["/dashboard", "/clientes", "/cobros"])
def test_con_la_simple_los_modulos_lo_mandan_a_su_ruta(entorno, ruta):
    """No basta esconder el enlace: la URL escrita a mano tambien redirige."""
    s, d, Sesion = entorno
    _poner(Sesion, d["A"]["empresa_id"], "simple")
    try:
        r = s["cobra_a"].get(ruta, follow_redirects=False)
        assert r.status_code == 302, f"{ruta} devolvio {r.status_code}"
        assert r.headers["location"] == "/ruta", r.headers["location"]
    finally:
        _poner(Sesion, d["A"]["empresa_id"], "completa")


def test_con_la_simple_el_menu_ofrece_solo_la_ruta(entorno):
    """Un enlace que al pulsarlo redirige es un enlace que no debe estar."""
    s, d, Sesion = entorno
    _poner(Sesion, d["A"]["empresa_id"], "simple")
    try:
        html = s["cobra_a"].get("/ruta").text
        assert 'href="/ruta"' in html, "el menu no ofrece la vista simple"
        for viejo in ('href="/dashboard"', 'href="/clientes"', 'href="/cobros"'):
            assert viejo not in html, f"el menu sigue ofreciendo {viejo}"
    finally:
        _poner(Sesion, d["A"]["empresa_id"], "completa")


def test_al_admin_no_le_cambia_nada(entorno):
    """La mitad que nadie prueba: encender la simple no puede dejar a la
    empresa sin poder administrarse."""
    s, d, Sesion = entorno
    _poner(Sesion, d["A"]["empresa_id"], "simple")
    try:
        for ruta in ("/dashboard", "/clientes", "/cobros", "/prestamos",
                     "/reportes", "/auth/usuarios"):
            r = s["admin_a"].get(ruta, follow_redirects=False)
            assert r.status_code == 200, f"{ruta} devolvio {r.status_code} al admin"
        html = s["admin_a"].get("/dashboard").text
        assert 'href="/clientes"' in html, "al admin le desaparecio el menu"
    finally:
        _poner(Sesion, d["A"]["empresa_id"], "completa")


# ── La vista unica ────────────────────────────────────────────────────────

def test_la_vista_simple_se_abre_para_el_cobrador(entorno):
    s, _, _ = entorno
    r = s["cobra_a"].get("/ruta")
    assert r.status_code == 200, r.text
    assert "Mi Ruta" in r.text


def test_la_vista_simple_no_carga_datos_al_entrar(entorno):
    """Arranca vacia: el cobrador elige la zona o pulsa "Ver todos"."""
    s, _, _ = entorno
    html = s["cobra_a"].get("/ruta").text
    assert 'id="sel-zona"' in html, "falta el selector de zona"
    assert "Elige la zona" in html, "no muestra el estado vacio"


def test_la_vista_simple_pide_sesion(entorno):
    """Sin sesion es una redireccion al login, no una pantalla vacia."""
    from app.main import app
    with TestClient(app) as anon:
        r = anon.get("/ruta", follow_redirects=False)
        assert r.status_code == 302
        assert "/license" in r.headers["location"] or "/auth/login" in r.headers["location"]


# ── Quien puede mover el interruptor ──────────────────────────────────────

def test_el_admin_cambia_la_interfaz(entorno):
    s, d, Sesion = entorno
    from app.database import Empresa
    try:
        r = s["admin_a"].post("/auth/interfaz-cobrador", data={"interfaz": "simple"})
        assert r.status_code == 200, r.text
        assert r.json()["interfaz"] == "simple"
        db = Sesion()
        try:
            e = db.query(Empresa).filter(Empresa.id == d["A"]["empresa_id"]).first()
            assert e.interfaz_cobrador == "simple"
        finally:
            db.close()
    finally:
        _poner(Sesion, d["A"]["empresa_id"], "completa")


def test_el_cobrador_no_puede_cambiar_la_interfaz(entorno):
    """Si el cobrador puede apagarla, la restriccion no existe."""
    s, d, Sesion = entorno
    from app.database import Empresa
    r = s["cobra_a"].post("/auth/interfaz-cobrador", data={"interfaz": "simple"})
    assert r.status_code == 403, f"devolvio {r.status_code}"
    db = Sesion()
    try:
        e = db.query(Empresa).filter(Empresa.id == d["A"]["empresa_id"]).first()
        assert e.interfaz_cobrador == "completa", "la cambio igualmente"
    finally:
        db.close()


@pytest.mark.parametrize("valor", ["", "  ", "mediana", "COMPLETA; DROP TABLE"])
def test_un_valor_invalido_se_rechaza(entorno, valor):
    s, d, Sesion = entorno
    from app.database import Empresa
    r = s["admin_a"].post("/auth/interfaz-cobrador", data={"interfaz": valor})
    assert r.status_code == 400, f"'{valor}' devolvio {r.status_code}"
    db = Sesion()
    try:
        e = db.query(Empresa).filter(Empresa.id == d["A"]["empresa_id"]).first()
        assert e.interfaz_cobrador == "completa"
    finally:
        db.close()


def test_cambiar_la_interfaz_no_toca_a_la_otra_empresa(entorno):
    """El endpoint no recibe empresa_id: la empresa es la del que pide."""
    s, d, Sesion = entorno
    from app.database import Empresa
    try:
        assert s["admin_a"].post("/auth/interfaz-cobrador",
                                 data={"interfaz": "simple"}).status_code == 200
        db = Sesion()
        try:
            otra = db.query(Empresa).filter(Empresa.id == d["B"]["empresa_id"]).first()
            assert otra.interfaz_cobrador == "completa", "le cambio la interfaz a la otra empresa"
        finally:
            db.close()
        # Y el cobrador de la otra empresa sigue con sus modulos.
        r = s["cobra_b"].get("/dashboard", follow_redirects=False)
        assert r.status_code == 200, f"al cobrador de B lo redirigio: {r.status_code}"
    finally:
        _poner(Sesion, d["A"]["empresa_id"], "completa")


# ── La columna nueva no se queda fuera de nada ────────────────────────────

def test_la_columna_nueva_entra_en_el_respaldo():
    """El respaldo recorre los modelos, asi que la columna entra sola."""
    from app.database import Empresa
    assert "interfaz_cobrador" in Empresa.__table__.columns


def test_hay_migracion_para_la_columna():
    """Sin migracion, el despliegue arranca contra una tabla sin la columna."""
    import pathlib
    ruta = pathlib.Path(__file__).resolve().parent.parent / "alembic" / "versions"
    textos = [p.read_text(encoding="utf-8") for p in ruta.glob("*.py")]
    assert any("interfaz_cobrador" in t and "add_column" in t for t in textos), \
        "ninguna migracion añade empresas.interfaz_cobrador"
