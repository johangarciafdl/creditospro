"""Una empresa no puede alcanzar los datos de otra cambiando un identificador.

Es el ataque que mas importa en esta aplicacion y el que ninguna herramienta
automatica encuentra: no hay entrada malformada ni inyeccion, todas las
peticiones son perfectamente validas y estan autenticadas. Lo unico que
cambia es el numero del recurso. Un escaner de vulnerabilidades ve dos
peticiones correctas; solo sabiendo quien deberia poder ver que se nota que
una de las dos no deberia responder.

Cada prueba hace de empresa A intentando tocar un recurso de la empresa B.
Se comprueban las dos mitades: que la respuesta niegue el acceso, y -- en
las que escriben -- que el dato de la victima siga intacto despues, porque
un endpoint puede responder un error y haber escrito igualmente.
"""
import datetime
import os
import tempfile
from decimal import Decimal
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="module")
def dos_empresas():
    """Levanta la app con dos inquilinos completos y devuelve (cliente_http, A, B).

    La sesion de base de datos se inyecta sustituyendo la dependencia `get_db`,
    sin recargar `app.database`. Recargarlo reasigna el motor global, pero los
    routers ya importaron `SessionLocal` por valor y se quedan apuntando al
    motor viejo: la siguiente fixture que recargue encuentra tablas que no
    existen. Sustituir la dependencia deja el resto del proceso intacto.
    """
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    bd = Path(tempfile.gettempdir()) / "creditospro_aislamiento_test.db"
    if bd.exists():
        bd.unlink()

    from app.database import (Base, Cliente, Cuota, Empresa, Prestamo,
                              Usuario, Zona, get_db, get_db_system)
    from app.main import app
    from app.utils.company_activation import assign_company_key
    from app.utils.security import get_password_hash

    motor = create_engine(f"sqlite:///{bd}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(motor)
    SessionLocal = sessionmaker(bind=motor, autoflush=False)

    def _sesion():
        db = SessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = _sesion
    app.dependency_overrides[get_db_system] = _sesion

    datos = {}
    db = SessionLocal()
    try:
        for etiqueta, nombre, usuario in [("A", "AtacanteSA", "atacante"),
                                          ("B", "VictimaSA", "victima")]:
            e = Empresa(nombre=nombre, activa=True)
            db.add(e); db.flush()
            clave = assign_company_key(db, e)
            z = Zona(empresa_id=e.id, codigo=f"Z{e.id}", nombre=f"Zona {nombre}")
            db.add(z); db.flush()
            db.add(Usuario(empresa_id=e.id, username=usuario, nombre=nombre,
                           rol="admin", activo=True,
                           password_hash=get_password_hash("ClaveDePrueba123!")))
            c = Cliente(empresa_id=e.id, cedula=f"CC{e.id}0001",
                        nombre=f"Cliente de {nombre}", telefono="3000000000",
                        zona_id=z.id, activo=True)
            db.add(c); db.flush()
            p = Prestamo(empresa_id=e.id, cliente_id=c.id, zona_id=z.id,
                         capital=Decimal("100000"), tasa_interes=Decimal("20"),
                         total_pagar=Decimal("120000"), num_cuotas=2,
                         valor_cuota=Decimal("60000"), estado="Activo",
                         fecha_inicio=datetime.date(2026, 9, 1),
                         fecha_fin=datetime.date(2026, 11, 1))
            db.add(p); db.flush()
            cuotas = []
            for i in (1, 2):
                cu = Cuota(empresa_id=e.id, prestamo_id=p.id, numero=i,
                           valor=Decimal("60000"), valor_pagado=Decimal("0"),
                           estado="Pendiente",
                           fecha_vencimiento=datetime.date(2026, 9, 1)
                           + datetime.timedelta(days=30 * i))
                db.add(cu); cuotas.append(cu)
            db.flush()
            datos[etiqueta] = dict(empresa_id=e.id, clave=clave, usuario=usuario,
                                   zona_id=z.id, cliente_id=c.id, nombre_cliente=c.nombre,
                                   prestamo_id=p.id, cuota_id=cuotas[0].id)
        db.commit()
    finally:
        db.close()

    with TestClient(app) as c:
        # Entrar como la empresa A, que sera la atacante.
        r = c.post("/license/activate", data={"license_key": datos["A"]["clave"]})
        assert r.status_code == 200, r.text
        r = c.post("/auth/login", data={"username": datos["A"]["usuario"],
                                        "password": "ClaveDePrueba123!"})
        assert r.status_code == 200, f"no se pudo entrar como atacante: {r.text[:200]}"
        c.get("/clientes")
        c.headers["x-csrf-token"] = c.cookies.get("cp_csrf", "")
        # Las comprobaciones leen la base directamente para ver si algo se
        # escribio pese a la negativa; comparten la misma sesion.
        yield c, datos["A"], datos["B"], SessionLocal

    app.dependency_overrides.pop(get_db, None)
    app.dependency_overrides.pop(get_db_system, None)
    motor.dispose()
    if bd.exists():
        bd.unlink(missing_ok=True)


def _niega(respuesta) -> bool:
    """404, 401 o 403 valen: lo que no vale es entregar el dato."""
    return respuesta.status_code in (401, 403, 404)


# ── Lectura ────────────────────────────────────────────────────────────────

def test_no_puede_leer_la_ficha_de_un_cliente_ajeno(dos_empresas):
    c, _, B, Sesion = dos_empresas
    r = c.get(f"/clientes/{B['cliente_id']}")
    assert _niega(r), f"devolvio {r.status_code}"
    assert B["nombre_cliente"] not in r.text


def test_no_puede_consultar_la_deuda_de_un_cliente_ajeno(dos_empresas):
    c, _, B, Sesion = dos_empresas
    r = c.get(f"/cobros/proxima-cuota/{B['cliente_id']}")
    assert _niega(r), f"devolvio {r.status_code}: {r.text[:120]}"


def test_no_puede_descargar_la_foto_de_otra_empresa(dos_empresas):
    """El nombre del archivo es adivinable para quien conozca el formato."""
    c, _, B, Sesion = dos_empresas
    r = c.get(f"/uploads/fotos/{B['empresa_id']}_1_loquesea.jpg")
    assert _niega(r), f"devolvio {r.status_code}"


def test_filtrar_por_una_zona_ajena_no_devuelve_nada(dos_empresas):
    """Aqui el aislamiento se ve como una lista vacia, no como un error."""
    c, _, B, Sesion = dos_empresas
    for ruta in (f"/clientes/buscar-ajax?q=&todos=1&zona_id={B['zona_id']}",
                 f"/cobros/pendientes-ajax?zona_id={B['zona_id']}"):
        r = c.get(ruta)
        assert r.status_code in (200, 401, 403, 404), f"{ruta} -> {r.status_code}"
        assert B["nombre_cliente"] not in r.text, f"{ruta} filtro datos ajenos"


def test_la_busqueda_general_nunca_saca_clientes_de_otra_empresa(dos_empresas):
    c, _, B, Sesion = dos_empresas
    r = c.get("/clientes/buscar-ajax?q=Cliente&todos=1&per_page=100")
    assert r.status_code == 200
    assert B["nombre_cliente"] not in r.text


# ── Escritura ──────────────────────────────────────────────────────────────

def _nombre_en_bd(Sesion, cliente_id: int) -> str:
    from app.database import Cliente
    db = Sesion()
    try:
        c = db.query(Cliente).filter(Cliente.id == cliente_id).first()
        return c.nombre if c else ""
    finally:
        db.close()


def test_no_puede_modificar_un_cliente_ajeno(dos_empresas):
    """Con el cuerpo completo y valido: nada en la peticion delata el ataque."""
    c, A, B, Sesion = dos_empresas
    r = c.post(f"/clientes/{B['cliente_id']}/editar",
               data={"nombre": "SECUESTRADO", "cedula": "9990001",
                     "telefono": "3001112222", "whatsapp": "3001112222",
                     "direccion": "x", "barrio": "x",
                     "zona_id": A["zona_id"], "tipo_cliente": "Regular"})
    assert _niega(r), f"devolvio {r.status_code}: {r.text[:150]}"
    assert _nombre_en_bd(Sesion, B["cliente_id"]) == B["nombre_cliente"], \
        "respondio un error pero escribio igualmente"


def test_no_puede_mover_la_ubicacion_de_un_cliente_ajeno(dos_empresas):
    c, _, B, Sesion = dos_empresas
    r = c.post(f"/clientes/{B['cliente_id']}/ubicacion",
               data={"lat": "6.25", "lng": "-75.56"})
    assert _niega(r), f"devolvio {r.status_code}"


def _saldo_en_bd(Sesion, cuota_id: int):
    from app.database import Cuota
    db = Sesion()
    try:
        cu = db.query(Cuota).filter(Cuota.id == cuota_id).first()
        return (cu.valor_pagado, cu.estado) if cu else (None, None)
    finally:
        db.close()


def test_no_puede_cobrar_una_cuota_ajena(dos_empresas):
    c, _, B, Sesion = dos_empresas
    antes = _saldo_en_bd(Sesion, B["cuota_id"])
    r = c.post("/cobros/registrar",
               data={"cuota_id": B["cuota_id"], "valor_cobrado": "1000",
                     "metodo_pago": "Efectivo"})
    assert _niega(r), f"devolvio {r.status_code}: {r.text[:150]}"
    assert _saldo_en_bd(Sesion, B["cuota_id"]) == antes, "el cobro se aplico pese al error"


def test_no_puede_usar_el_cobro_rapido_contra_un_cliente_ajeno(dos_empresas):
    c, _, B, Sesion = dos_empresas
    antes = _saldo_en_bd(Sesion, B["cuota_id"])
    r = c.post(f"/cobros/registrar-cliente/{B['cliente_id']}",
               data={"metodo_pago": "Efectivo"})
    assert _niega(r), f"devolvio {r.status_code}: {r.text[:150]}"
    assert _saldo_en_bd(Sesion, B["cuota_id"]) == antes


def _cuenta_no_pagos(Sesion, cuota_id: int) -> int:
    from app.database import NoPago
    db = Sesion()
    try:
        return db.query(NoPago).filter(NoPago.cuota_id == cuota_id).count()
    finally:
        db.close()


def test_no_puede_marcar_no_pago_en_una_cuota_ajena(dos_empresas):
    c, _, B, Sesion = dos_empresas
    r = c.post("/cobros/no-pago", data={"cuota_id": B["cuota_id"], "motivo": "x"})
    assert _niega(r), f"devolvio {r.status_code}: {r.text[:150]}"
    assert _cuenta_no_pagos(Sesion, B["cuota_id"]) == 0, "escribio la visita fallida igualmente"


def test_no_puede_deshacer_un_no_pago_ajeno(dos_empresas):
    c, _, B, Sesion = dos_empresas
    r = c.post("/cobros/no-pago/deshacer", data={"cuota_id": B["cuota_id"]})
    assert _niega(r), f"devolvio {r.status_code}"


def test_no_puede_renombrar_una_zona_ajena(dos_empresas):
    c, _, B, Sesion = dos_empresas
    r = c.post(f"/zonas/{B['zona_id']}/editar",
               data={"nombre": "ZONA SECUESTRADA", "codigo": "HACK"})
    assert _niega(r), f"devolvio {r.status_code}"
    from app.database import Zona
    db = Sesion()
    try:
        z = db.query(Zona).filter(Zona.id == B["zona_id"]).first()
        assert z.nombre != "ZONA SECUESTRADA", "respondio error pero renombro la zona"
    finally:
        db.close()


# ── Escalada de privilegios ────────────────────────────────────────────────

def test_un_admin_de_empresa_no_entra_al_panel_de_la_plataforma(dos_empresas):
    """Ser admin de la propia empresa no es ser dueno de la plataforma."""
    c, _, _, Sesion = dos_empresas
    for ruta in ("/plataforma/empresas", "/plataforma"):
        r = c.get(ruta, follow_redirects=False)
        assert r.status_code != 200 or "empresas" not in r.text.lower(), \
            f"{ruta} se abrio para un admin de empresa"


def test_no_puede_ver_la_ruta_semanal_de_un_usuario_ajeno(dos_empresas):
    c, _, B, Sesion = dos_empresas
    from app.database import Usuario
    db = Sesion()
    try:
        ajeno = db.query(Usuario).filter(Usuario.empresa_id == B["empresa_id"]).first()
        ajeno_id = ajeno.id
    finally:
        db.close()
    r = c.get(f"/auth/usuarios/{ajeno_id}/ruta", follow_redirects=False)
    assert r.status_code != 200 or "VictimaSA" not in r.text, f"devolvio {r.status_code}"
