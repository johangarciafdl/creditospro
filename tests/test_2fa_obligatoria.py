"""Los administradores tienen que activar la verificacion en dos pasos.

Hasta activarla, cualquier pantalla los lleva a /auth/2fa/configurar y las
peticiones de datos responden 403. El cobrador no se ve afectado.
"""
import os
import py_compile
import tempfile
from pathlib import Path

import pyotp
import pytest
from fastapi.testclient import TestClient

HTML = {"accept": "text/html"}
entorno_extra = {}


@pytest.fixture(scope="module")
def entorno():
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    bd = Path(tempfile.gettempdir()) / "creditospro_2fa_test.db"
    if bd.exists():
        bd.unlink()
    from app.database import Base, Empresa, Usuario, Zona
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
    db = Sesion()
    try:
        e = Empresa(nombre="DosPasosSA", activa=True)
        db.add(e); db.flush()
        clave = assign_company_key(db, e)
        z = Zona(empresa_id=e.id, codigo="DP", nombre="Centro")
        db.add(z); db.flush()
        for u, rol in (("dpjefa", "admin"), ("dpcobra", "cobrador")):
            usr = Usuario(empresa_id=e.id, username=u, nombre=u.title() + " Prueba", rol=rol,
                          activo=True, password_hash=get_password_hash("ClaveDePrueba123!"))
            db.add(usr); db.flush()
            if rol == "cobrador":
                usr.zonas_asignadas.append(z)
        db.commit()
    finally:
        db.close()

    anterior = os.environ.get("EXIGIR_2FA_ADMIN")
    os.environ["EXIGIR_2FA_ADMIN"] = "1"

    def entrar(usuario):
        vaciar_limitador()
        cli = TestClient(app)
        cli.__enter__()
        assert cli.post("/license/activate", data={"license_key": clave}).status_code == 200
        r = cli.post("/auth/login", data={"username": usuario, "password": "ClaveDePrueba123!"},
                     follow_redirects=False)
        assert r.status_code in (200, 302, 303), r.text
        cli.get("/auth/2fa/configurar")
        cli.headers["x-csrf-token"] = cli.cookies.get("cp_csrf", "")
        return cli

    jefa, cobra = entrar("dpjefa"), entrar("dpcobra")
    entorno_extra.update(clave=clave, app=app)
    yield jefa, cobra
    os.environ["EXIGIR_2FA_ADMIN"] = anterior or "0"
    for c in (jefa, cobra):
        c.__exit__(None, None, None)
    for k in claves:
        app.dependency_overrides.pop(k, None)
    motor.dispose()
    bd.unlink(missing_ok=True)


def test_el_admin_sin_2fa_va_a_configurarla(entorno):
    jefa, _ = entorno
    r = jefa.get("/dashboard", headers=HTML, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/auth/2fa/configurar"
    r = jefa.get("/finanzas/datos")
    assert r.status_code == 403 and r.json()["configurar_2fa"] is True
    assert jefa.get("/auth/2fa/configurar").status_code == 200


def test_el_cobrador_no_se_ve_afectado(entorno):
    _, cobra = entorno
    assert cobra.get("/ruta", headers=HTML, follow_redirects=False).status_code == 200


def test_activarla_con_la_contrasena_el_qr_y_un_codigo(entorno):
    jefa, _ = entorno
    assert jefa.post("/auth/2fa/setup", data={"password": "mala"}).status_code == 403
    r = jefa.post("/auth/2fa/setup", data={"password": "ClaveDePrueba123!"})
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["qr_svg"].lstrip().startswith("<svg") and d["secret"]
    pytest.secreto_2fa = d["secret"]
    assert jefa.post("/auth/2fa/setup/confirm", data={"code": "000000"}).status_code == 400
    r = jefa.post("/auth/2fa/setup/confirm", data={"code": pyotp.TOTP(d["secret"]).now()})
    assert r.status_code == 200 and len(r.json()["backup_codes"]) == 10
    # Activada: ya entra.
    assert jefa.get("/dashboard", headers=HTML, follow_redirects=False).status_code == 200
    assert jefa.get("/finanzas/datos").status_code == 200


def test_la_pantalla_y_el_script_de_recuperacion_existen():
    html = Path("templates/auth/2fa_configurar.html").read_text(encoding="utf-8")
    assert "paso1(" in html and "paso2(" in html and "backup_codes" in html
    py_compile.compile("scripts/resetear_2fa.py", doraise=True)
    assert "segno" in Path("requirements.txt").read_text(encoding="utf-8")


def test_la_cuenta_de_plataforma_no_queda_encerrada():
    """El superadmin entra por /plataforma/login, sin paso de codigo; si se le
    exigiera la 2FA, el candado de licencia (no activa empresa) lo dejaria
    sin poder ni configurarla."""
    from types import SimpleNamespace
    from app.routers.auth import exige_segundo_factor
    req = SimpleNamespace(url=SimpleNamespace(path="/plataforma"))
    os.environ["EXIGIR_2FA_ADMIN"] = "1"
    sa = SimpleNamespace(rol="superadmin", two_factor_enabled=False)
    admin = SimpleNamespace(rol="admin", two_factor_enabled=False)
    assert exige_segundo_factor(sa, req) is False
    assert exige_segundo_factor(admin, SimpleNamespace(url=SimpleNamespace(path="/dashboard"))) is True



def test_entrar_con_el_codigo_desde_el_formulario_del_navegador(entorno):
    """El error real: con la 2FA activa, el formulario del codigo (un <form>
    HTML, sin cabecera CSRF) se rechazaba siempre con "Solicitud bloqueada
    por CSRF", aunque el codigo fuera el correcto."""
    import re
    from conftest import vaciar_limitador
    secreto = getattr(pytest, "secreto_2fa", None)
    assert secreto, "esta prueba va despues de activar la 2FA"
    vaciar_limitador()
    with TestClient(entorno_extra["app"]) as nav:      # sin cabecera x-csrf-token
        assert nav.post("/license/activate",
                        data={"license_key": entorno_extra["clave"]}).status_code == 200
        r = nav.post("/auth/login", data={"username": "dpjefa", "password": "ClaveDePrueba123!"},
                     follow_redirects=False)
        assert r.status_code in (302, 303) and r.headers["location"] == "/auth/2fa", r.text
        pagina = nav.get("/auth/2fa").text
        token = re.search(r'name="csrf_token" value="([^"]+)"', pagina)
        assert token, "el formulario del codigo no lleva el token CSRF"
        # Un codigo malo: error del codigo, no de CSRF.
        r = nav.post("/auth/2fa", data={"code": "000000", "csrf_token": token.group(1)},
                     follow_redirects=False)
        assert r.status_code == 401 and "CSRF" not in r.text
        token = re.search(r'name="csrf_token" value="([^"]+)"', r.text).group(1)
        r = nav.post("/auth/2fa", data={"code": pyotp.TOTP(secreto).now(), "csrf_token": token},
                     follow_redirects=False)
        assert r.status_code == 303 and r.headers["location"] == "/dashboard", r.text
        assert nav.get("/dashboard", headers=HTML, follow_redirects=False).status_code == 200
