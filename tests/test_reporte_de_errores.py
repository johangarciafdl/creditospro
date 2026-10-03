"""Los cuatro errores del reporte de pruebas, y los mismos fallos en otras pantallas.

1. Campos de contraseña sin boton de ojo (Usuarios, y tambien registro,
   plataforma, activacion, WhatsApp y zonas).
2. "En que" del gasto aceptaba basura (".,.,.,mtdfgdg44´+´+"); lo mismo pasaba
   en el concepto de la caja, las observaciones del prestamo y las notas.
3. confirm()/prompt() del navegador (Mi caja, y tambien Usuarios, Plataforma,
   Cobros, la vista simple y el cierre de sesion).
4. Cliente nuevo con nombre inventado ("resdads"), y un formulario incompleto
   que mostraba "[object Object],[object Object]" (pasaba en TODOS los
   formularios: era la respuesta 422 de FastAPI).
"""
import datetime
import re
import tempfile
from pathlib import Path

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.utils.validators import (validar_cedula_persona, validar_descripcion,
                                  validar_nombre_persona)

RAIZ = Path(__file__).resolve().parent.parent


def _rechaza(funcion, *args):
    with pytest.raises(HTTPException) as e:
        funcion(*args)
    assert e.value.status_code == 400
    return e.value.detail


# ── 2. Texto con forma de texto ───────────────────────────────────────────

@pytest.mark.parametrize("texto", [
    ".,.,.,mtdfgdg44´+´+",      # el del reporte
    "almuerzo23",               # el del reporte: numero pegado a la palabra
    "mtdfgdg",                  # sin vocales / cinco consonantes seguidas
    "aaaaaa",                   # el mismo caracter repetido
    "???!!!",                   # solo signos
    "xz",                       # sin palabras
    "+*=_|~",                   # simbolos fuera de la lista
    "<script>alert(1)</script>",
])
def test_una_descripcion_basura_se_rechaza(texto):
    _rechaza(validar_descripcion, texto, "Concepto")


@pytest.mark.parametrize("texto,guardado", [
    ("almuerzo", "Almuerzo"),
    ("almuerzo 23", "Almuerzo 23"),
    ("Taxi 15000", "Taxi 15000"),
    ("gasolina 20mil", "Gasolina 20mil"),
    ("Pago 50.000 el 12/09", "Pago 50.000 el 12/09"),
    ("Arreglo moto: llanta trasera", "Arreglo moto: llanta trasera"),
    ("Transporte (bus) ida y vuelta", "Transporte (bus) ida y vuelta"),
    ("Café   con  leche", "Café con leche"),
    ("Cra 45 #12-30", "Cra 45 #12-30"),
])
def test_una_descripcion_normal_pasa_y_se_ordena(texto, guardado):
    assert validar_descripcion(texto, "Concepto") == guardado


def test_vacia_solo_se_rechaza_si_es_obligatoria():
    assert validar_descripcion("   ", "Concepto") == ""
    assert "escribe" in _rechaza(validar_descripcion, "", "En que", 300, True).lower()


# ── 4. Nombre y cedula del cliente ────────────────────────────────────────

@pytest.mark.parametrize("nombre", [
    "resdads",            # el del reporte: un solo nombre, inventado
    "Sammy",              # un solo nombre
    "Juan123 Perez",      # con numeros
    "Mtdfg Perez",        # palabra sin forma de nombre
    "Juan <b>Perez</b>",
    "",
])
def test_un_nombre_de_cliente_invalido_se_rechaza(nombre):
    _rechaza(validar_nombre_persona, nombre)


@pytest.mark.parametrize("nombre", [
    "Juan Perez", "JOHAN ROJAS", "María José De la Cruz", "O'Neil Smith",
    "Ana-María Gómez",
])
def test_un_nombre_de_cliente_real_pasa(nombre):
    assert validar_nombre_persona(nombre) == nombre


def test_la_cedula_necesita_numeros():
    _rechaza(validar_cedula_persona, "abcde")
    _rechaza(validar_cedula_persona, "123")
    assert validar_cedula_persona("1036789456") == "1036789456"
    assert validar_cedula_persona("V-12.345.678") == "V-12345678"
    assert validar_cedula_persona("PA1234567") == "PA1234567"


# ── Contra la aplicacion ──────────────────────────────────────────────────

@pytest.fixture(scope="module")
def entorno():
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    bd = Path(tempfile.gettempdir()) / "creditospro_reporte_errores_test.db"
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

    d = {}
    db = Sesion()
    try:
        e = Empresa(nombre="ReporteSA", activa=True)
        db.add(e); db.flush()
        d["clave"] = assign_company_key(db, e)
        z = Zona(empresa_id=e.id, codigo="RE1", nombre="Centro")
        db.add(z); db.flush()
        d["zona"] = z.id
        cob = Usuario(empresa_id=e.id, username="repcobra", nombre="Rep Cobra",
                      rol="cobrador", activo=True,
                      password_hash=get_password_hash("ClaveDePrueba123!"))
        db.add(cob); db.flush()
        cob.zonas_asignadas.append(z)
        d["cobrador_id"] = cob.id
        c = Cliente(empresa_id=e.id, cedula="1000555", nombre="Cliente Viejo",
                    telefono="3001112233", zona_id=z.id, activo=True)
        db.add(c); db.flush()
        d["cliente"] = c.id
        db.commit()
    finally:
        db.close()

    vaciar_limitador()
    cli = TestClient(app)
    cli.__enter__()
    assert cli.post("/license/activate", data={"license_key": d["clave"]}).status_code == 200
    assert cli.post("/auth/login", data={"username": "repcobra",
                                         "password": "ClaveDePrueba123!"}).status_code == 200
    cli.get("/ruta")
    cli.headers["x-csrf-token"] = cli.cookies.get("cp_csrf", "")
    yield cli, d

    cli.__exit__(None, None, None)
    for clave in claves:
        app.dependency_overrides.pop(clave, None)
    motor.dispose()
    bd.unlink(missing_ok=True)


def test_un_formulario_incompleto_explica_que_falta(entorno):
    """El "[object Object],[object Object]" del reporte: la lista de errores
    de FastAPI mostrada tal cual. Ahora es una frase que nombra los campos."""
    cli, d = entorno
    r = cli.post("/clientes/nuevo", data={"zona_id": str(d["zona"])})
    assert r.status_code == 422
    cuerpo = r.json()
    assert "detail" not in cuerpo
    assert isinstance(cuerpo["error"], str)
    for campo in ("Cédula", "Nombre", "Teléfono"):
        assert campo in cuerpo["error"], cuerpo["error"]
    assert "object" not in cuerpo["error"].lower()


def test_lo_mismo_en_cualquier_otro_formulario(entorno):
    cli, _ = entorno
    r = cli.post("/cobros/no-pago", data={})
    assert r.status_code == 422
    assert r.json()["error"].startswith("Completa:")
    r = cli.post("/ruta/prestar", data={"zona_id": "no-es-numero"})
    assert r.status_code == 422
    assert "Revisa: Zona" in r.json()["error"]


@pytest.mark.parametrize("nombre", ["resdads", "Juan123 Perez"])
def test_alta_de_cliente_con_nombre_inventado_se_rechaza(entorno, nombre):
    cli, d = entorno
    r = cli.post("/clientes/nuevo", data={
        "cedula": "1000777", "nombre": nombre, "telefono": "3005550000",
        "zona_id": str(d["zona"])})
    assert r.status_code == 400, r.text
    assert r.json()["error"]


def test_alta_de_cliente_valido_sigue_funcionando(entorno):
    cli, d = entorno
    r = cli.post("/clientes/nuevo", data={
        "cedula": "1000778", "nombre": "Rosa Elena Mejia", "telefono": "3005550001",
        "zona_id": str(d["zona"])})
    assert r.status_code == 200 and r.json().get("ok"), r.text


def test_el_gasto_del_cobrador_ya_no_llega_al_servidor(entorno):
    """La caja del cobrador es una guia: su gasto se queda en el celular. La
    validacion del "En que" sigue en validar_descripcion (pruebas de arriba)
    y la usa el admin en el cuadre semanal y la caja."""
    cli, d = entorno
    r = cli.post("/caja/movimiento", data={
        "usuario_id": d["cobrador_id"], "tipo": "gasto", "valor": "5000",
        "fecha": datetime.date.today().isoformat(), "concepto": "almuerzo"})
    assert r.status_code == 403





def test_una_nota_con_html_se_rechaza(entorno):
    """Las notas ni siquiera rechazaban '<' y '>'."""
    cli, d = entorno
    r = cli.post(f"/clientes/{d['cliente']}/notas", data={"texto": "<img src=x onerror=alert(1)>"})
    assert r.status_code == 400, r.text


# ── 3. Nada de confirm()/prompt()/alert() del navegador ───────────────────

def _codigo_sin_comentarios(texto: str) -> str:
    texto = re.sub(r"/\*.*?\*/", "", texto, flags=re.S)
    return "\n".join(l.split("//")[0] if "//" in l and "http" not in l else l
                     for l in texto.splitlines())


def test_no_queda_ningun_dialogo_nativo_del_navegador():
    archivos = list((RAIZ / "templates").rglob("*.html")) + \
        [p for p in (RAIZ / "static" / "js").glob("*.js")]
    encontrados = []
    for archivo in archivos:
        codigo = _codigo_sin_comentarios(archivo.read_text(encoding="utf-8"))
        for m in re.finditer(r"(?<![\w.])(confirm|prompt|alert)\(", codigo):
            encontrados.append(f"{archivo.name}: {m.group(0)}")
    assert not encontrados, encontrados


def test_las_ventanas_propias_existen_y_se_usan():
    app_js = (RAIZ / "static" / "js" / "app.js").read_text(encoding="utf-8")
    assert "function confirmar(" in app_js and "function pedirTexto(" in app_js
    caja = (RAIZ / "templates" / "caja.html").read_text(encoding="utf-8")
    assert caja.count("await confirmar(") >= 2   # retirar gasto, retirar movimiento (y cerrar caja)
    base = (RAIZ / "templates" / "base.html").read_text(encoding="utf-8")
    assert "cerrarSesion(event)" in base


def test_leer_respuesta_nunca_devuelve_una_lista_como_error():
    app_js = (RAIZ / "static" / "js" / "app.js").read_text(encoding="utf-8")
    bloque = app_js.split("async function leerRespuesta")[1][:900]
    assert "Array.isArray(datos.detail)" in bloque


# ── 1. Ojo en las contraseñas ─────────────────────────────────────────────

@pytest.mark.parametrize("plantilla", [
    "base.html", "registro.html", "plataforma_login.html", "activacion.html",
])
def test_las_paginas_con_contrasena_cargan_el_ojo(plantilla):
    html = (RAIZ / "templates" / plantilla).read_text(encoding="utf-8")
    assert "js/ojo_clave.js" in html


def test_el_login_conserva_su_propio_ojo_y_no_se_duplica():
    html = (RAIZ / "templates" / "auth" / "login.html").read_text(encoding="utf-8")
    assert "data-sin-ojo" in html and "togglePass" in html


def test_el_boton_del_ojo_no_envia_el_formulario():
    js = (RAIZ / "static" / "js" / "ojo_clave.js").read_text(encoding="utf-8")
    assert "boton.type = 'button'" in js
    assert 'input[type="password"]' in js
