"""El cobrador avisa por nota; el administrador corrige.

Es la contrapartida de haber cerrado la ficha del cliente. Quien esta en la
calle es el unico que se entera de que alguien se mudo o cambio de numero;
si no tiene donde apuntarlo, ese dato se pierde en un WhatsApp o no se dice
nunca. La nota no modifica nada: deja constancia y le llega al admin.

Por eso escribir una nota es la UNICA escritura que le queda al cobrador, y
eso hay que vigilarlo por los dos lados: que pueda escribirla (si se cierra
de mas, la restriccion se vuelve impracticable) y que la nota no se
convierta en una puerta para tocar datos ajenos.
"""
import datetime
import tempfile
from decimal import Decimal
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="module")
def entorno():
    """Dos empresas; en la primera, un admin y un cobrador."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    bd = Path(tempfile.gettempdir()) / "creditospro_notas_test.db"
    if bd.exists():
        bd.unlink()

    from app.database import (Base, Cliente, Empresa, Usuario, Zona,
                              get_db, get_db_system)
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

    from conftest import sustituir_sesion
    claves = sustituir_sesion(app, _sesion)

    datos = {}
    db = Sesion()
    try:
        for etiqueta, nombre in (("A", "NotasSA"), ("B", "OtraSA")):
            e = Empresa(nombre=nombre, activa=True)
            db.add(e); db.flush()
            clave = assign_company_key(db, e)
            z = Zona(empresa_id=e.id, codigo=f"Z{e.id}", nombre=f"Zona {nombre}")
            db.add(z); db.flush()
            c = Cliente(empresa_id=e.id, cedula=f"CC{e.id}", nombre=f"Cliente {nombre}",
                        telefono="3000000000", zona_id=z.id, activo=True)
            db.add(c); db.flush()
            datos[etiqueta] = dict(empresa_id=e.id, clave=clave,
                                   zona_id=z.id, cliente_id=c.id)

        za = db.query(Zona).filter(Zona.empresa_id == datos["A"]["empresa_id"]).first()
        for usuario, rol in (("jefa", "admin"), ("cobra", "cobrador")):
            u = Usuario(empresa_id=datos["A"]["empresa_id"], username=usuario,
                        nombre=usuario.title(), rol=rol, activo=True,
                        password_hash=get_password_hash("ClaveDePrueba123!"))
            db.add(u); db.flush()
            if rol == "cobrador":
                u.zonas_asignadas.append(za)
        db.commit()
    finally:
        db.close()

    def entrar(usuario):
        cli = TestClient(app)
        cli.__enter__()
        r = cli.post("/license/activate", data={"license_key": datos["A"]["clave"]})
        assert r.status_code == 200, r.text
        r = cli.post("/auth/login", data={"username": usuario,
                                          "password": "ClaveDePrueba123!"})
        assert r.status_code == 200, f"{usuario} no pudo entrar"
        cli.get("/cobros")
        cli.headers["x-csrf-token"] = cli.cookies.get("cp_csrf", "")
        return cli

    cobrador = entrar("cobra")
    admin = entrar("jefa")
    yield cobrador, admin, datos, Sesion

    for c in (cobrador, admin):
        c.__exit__(None, None, None)
    for clave in claves:
        app.dependency_overrides.pop(clave, None)
    motor.dispose()
    bd.unlink(missing_ok=True)


# ── El cobrador si puede avisar ────────────────────────────────────────────

def test_el_cobrador_puede_dejar_una_nota(entorno):
    """La unica escritura que le queda; sin ella la restriccion no es viable."""
    cobrador, _, d, Sesion = entorno
    from app.database import NotaCliente

    r = cobrador.post(f"/clientes/{d['A']['cliente_id']}/notas",
                      data={"texto": "Se mudó al barrio de al lado"})
    assert r.status_code == 200, r.text
    db = Sesion()
    try:
        n = db.query(NotaCliente).order_by(NotaCliente.id.desc()).first()
        assert n.texto == "Se mudó al barrio de al lado"
        assert n.escrita_por == "Cobra", "debe quedar quien la escribio"
        assert n.atendida is False, "nace pendiente"
    finally:
        db.close()


def test_la_nota_no_toca_la_ficha_del_cliente(entorno):
    """Es un aviso, no una edicion encubierta."""
    cobrador, _, d, Sesion = entorno
    from app.database import Cliente

    db = Sesion()
    try:
        antes = db.query(Cliente).filter(Cliente.id == d["A"]["cliente_id"]).first()
        nombre, telefono = antes.nombre, antes.telefono
    finally:
        db.close()

    cobrador.post(f"/clientes/{d['A']['cliente_id']}/notas",
                  data={"texto": "El número nuevo es 3001234567"})

    db = Sesion()
    try:
        despues = db.query(Cliente).filter(Cliente.id == d["A"]["cliente_id"]).first()
        assert despues.nombre == nombre and despues.telefono == telefono
    finally:
        db.close()


@pytest.mark.parametrize("texto", ["", "   ", "\n\t "])
def test_una_nota_vacia_se_rechaza(entorno, texto):
    """Una bandeja con filas en blanco deja de leerse."""
    cobrador, _, d, _ = entorno
    r = cobrador.post(f"/clientes/{d['A']['cliente_id']}/notas", data={"texto": texto})
    assert r.status_code == 400, f"devolvio {r.status_code}"


def test_una_nota_larguisima_se_rechaza(entorno):
    cobrador, _, d, _ = entorno
    r = cobrador.post(f"/clientes/{d['A']['cliente_id']}/notas",
                      data={"texto": "x" * 601})
    assert r.status_code == 400


# ── Pero no es una puerta trasera ──────────────────────────────────────────

def test_no_puede_dejar_notas_en_clientes_de_otra_empresa(entorno):
    """La nota respeta el aislamiento igual que cualquier otra escritura."""
    cobrador, _, d, Sesion = entorno
    from app.database import NotaCliente

    r = cobrador.post(f"/clientes/{d['B']['cliente_id']}/notas",
                      data={"texto": "colada"})
    assert r.status_code in (403, 404), f"devolvio {r.status_code}"
    db = Sesion()
    try:
        assert db.query(NotaCliente).filter(
            NotaCliente.cliente_id == d["B"]["cliente_id"]).count() == 0, \
            "escribio la nota igualmente"
    finally:
        db.close()


def test_el_cobrador_no_ve_la_bandeja_del_admin(entorno):
    """La bandeja es el listado completo de la empresa: no es cosa suya."""
    cobrador, _, _, _ = entorno
    r = cobrador.get("/clientes/notas/pendientes")
    assert r.status_code == 403, f"devolvio {r.status_code}"


def test_el_cobrador_no_puede_marcar_una_nota_como_atendida(entorno):
    """Quien la resuelve es quien corrige la ficha, y eso es del admin."""
    cobrador, admin, d, Sesion = entorno
    from app.database import NotaCliente

    cobrador.post(f"/clientes/{d['A']['cliente_id']}/notas",
                  data={"texto": "para intentar cerrarla yo mismo"})
    db = Sesion()
    try:
        nota_id = db.query(NotaCliente).order_by(NotaCliente.id.desc()).first().id
    finally:
        db.close()

    r = cobrador.post(f"/clientes/notas/{nota_id}/atender")
    assert r.status_code == 403, f"devolvio {r.status_code}"
    db = Sesion()
    try:
        assert db.query(NotaCliente).filter(NotaCliente.id == nota_id).first().atendida is False
    finally:
        db.close()


# ── El admin la recibe y la cierra ─────────────────────────────────────────

def test_el_admin_ve_las_pendientes_con_el_cliente(entorno):
    """Sin saber de quien es la nota, el aviso no sirve de nada."""
    cobrador, admin, d, _ = entorno
    cobrador.post(f"/clientes/{d['A']['cliente_id']}/notas",
                  data={"texto": "cambió de casa, avisar"})

    r = admin.get("/clientes/notas/pendientes")
    assert r.status_code == 200, r.text
    cuerpo = r.json()
    assert cuerpo["total"] >= 1
    nota = cuerpo["notas"][0]
    for campo in ("texto", "cliente", "cedula", "escrita_por", "creado", "cliente_id"):
        assert campo in nota, f"falta {campo} en la bandeja"


def test_atender_una_nota_la_saca_de_la_bandeja(entorno):
    cobrador, admin, d, Sesion = entorno
    from app.database import NotaCliente

    cobrador.post(f"/clientes/{d['A']['cliente_id']}/notas",
                  data={"texto": "para cerrarla"})
    db = Sesion()
    try:
        nota_id = db.query(NotaCliente).order_by(NotaCliente.id.desc()).first().id
    finally:
        db.close()

    antes = admin.get("/clientes/notas/pendientes").json()["total"]
    r = admin.post(f"/clientes/notas/{nota_id}/atender")
    assert r.status_code == 200, r.text
    despues = admin.get("/clientes/notas/pendientes").json()["total"]
    assert despues == antes - 1

    db = Sesion()
    try:
        n = db.query(NotaCliente).filter(NotaCliente.id == nota_id).first()
        assert n.atendida is True
        assert n.atendida_por == "Jefa", "debe quedar quien la resolvio"
        assert n.atendida_en is not None
    finally:
        db.close()


def test_atender_dos_veces_no_revienta(entorno):
    """Dos pulsaciones seguidas con mala señal no deben dar error."""
    cobrador, admin, d, Sesion = entorno
    from app.database import NotaCliente

    cobrador.post(f"/clientes/{d['A']['cliente_id']}/notas", data={"texto": "doble"})
    db = Sesion()
    try:
        nota_id = db.query(NotaCliente).order_by(NotaCliente.id.desc()).first().id
    finally:
        db.close()
    assert admin.post(f"/clientes/notas/{nota_id}/atender").status_code == 200
    assert admin.post(f"/clientes/notas/{nota_id}/atender").status_code == 200


def test_el_admin_no_atiende_notas_de_otra_empresa(entorno):
    admin = entorno[1]
    r = admin.post("/clientes/notas/999999/atender")
    assert r.status_code == 404


# ── La tabla nueva no se queda fuera de nada ───────────────────────────────

def test_la_tabla_nueva_tiene_su_politica_de_aislamiento():
    """Una tabla sin politica es una tabla que el rol restringido lee entera.

    Es el patron que ya se colo una vez: se crea la tabla, se olvida la
    politica, y el aislamiento solo existe en el codigo.
    """
    import pathlib
    sql = (pathlib.Path(__file__).resolve().parent.parent / "rls_policies.sql").read_text(encoding="utf-8")
    assert "ALTER TABLE notas_cliente ENABLE ROW LEVEL SECURITY" in sql
    assert "empresa_isolation_notas_cliente" in sql


def test_la_tabla_nueva_entra_en_el_respaldo():
    """El respaldo recorre los modelos, asi que deberia entrar sola."""
    from app.services.respaldo import _nombre_tablas
    assert "notas_cliente" in _nombre_tablas()
