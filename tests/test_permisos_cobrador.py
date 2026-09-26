"""Que puede y que no puede hacer un cobrador.

La linea no esta entre "leer" y "escribir": esta entre **dar de alta algo
nuevo** y **corregir algo que ya existe**. Un cobrador encuentra a alguien en
la calle, lo registra y le presta en el momento -- eso es su trabajo. Lo que
no puede es volver sobre una ficha que ya estaba y cambiarla: una ficha de
cliente es el expediente de una deuda, y corregirla con prisa y sin
supervision es como se pierde la direccion de alguien que debe dinero. Si ve
un dato mal, deja una nota y el admin corrige.

Cada prueba de lo negado comprueba las dos mitades, igual que las de
aislamiento entre empresas: que la respuesta niegue la accion, y que el dato
siga intacto despues. Un endpoint puede responder 403 y haber escrito
igualmente.

El matiz que no hay que romper: la foto y el GPS que se guardan CON EL COBRO
son del cobro, no del cliente, y ahi si los aporta el cobrador porque son la
evidencia de donde se recibio el dinero.
"""
import datetime
import io
import tempfile
from decimal import Decimal
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image


@pytest.fixture(scope="module")
def entorno():
    """App con un cobrador de una empresa, y datos suyos que intentara tocar."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    bd = Path(tempfile.gettempdir()) / "creditospro_permisos_test.db"
    if bd.exists():
        bd.unlink()

    from app.database import (Base, Cliente, Cuota, Empresa, Prestamo,
                              Usuario, Zona, get_db, get_db_system)
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

    # Sustituye la dependencia en todas las rutas, sea el objeto que sea:
    # los routers importaron la suya al cargarse y otra prueba recarga
    # app.database, asi que las identidades no coinciden.
    from conftest import sustituir_sesion
    claves = sustituir_sesion(app, _sesion)

    db = Sesion()
    try:
        e = Empresa(nombre="PermisosSA", activa=True)
        db.add(e); db.flush()
        clave = assign_company_key(db, e)
        z = Zona(empresa_id=e.id, codigo="Z1", nombre="Centro")
        db.add(z); db.flush()
        for usuario, rol in (("jefa", "admin"), ("cobra", "cobrador")):
            db.add(Usuario(empresa_id=e.id, username=usuario, nombre=usuario.title(),
                           rol=rol, activo=True,
                           password_hash=get_password_hash("ClaveDePrueba123!")))
        db.flush()
        cobrador = db.query(Usuario).filter(Usuario.username == "cobra").first()
        cobrador.zonas_asignadas.append(z)          # la zona si es suya
        c = Cliente(empresa_id=e.id, cedula="111", nombre="Cliente Original",
                    telefono="3000000000", direccion="Calle Original 1",
                    zona_id=z.id, activo=True)
        db.add(c); db.flush()
        p = Prestamo(empresa_id=e.id, cliente_id=c.id, zona_id=z.id,
                     capital=Decimal("100000"), tasa_interes=Decimal("20"),
                     total_pagar=Decimal("120000"), num_cuotas=2,
                     valor_cuota=Decimal("60000"), estado="Activo",
                     fecha_inicio=datetime.date(2026, 9, 1),
                     fecha_fin=datetime.date(2026, 11, 1))
        db.add(p); db.flush()
        cu = Cuota(empresa_id=e.id, prestamo_id=p.id, numero=1,
                   valor=Decimal("60000"), valor_pagado=Decimal("0"),
                   estado="Pendiente", fecha_vencimiento=datetime.date(2026, 9, 15))
        db.add(cu); db.flush()
        datos = dict(empresa_id=e.id, clave=clave, zona_id=z.id,
                     cliente_id=c.id, prestamo_id=p.id, cuota_id=cu.id)
        db.commit()
    finally:
        db.close()

    with TestClient(app) as cli:
        r = cli.post("/license/activate", data={"license_key": datos["clave"]})
        assert r.status_code == 200, r.text
        r = cli.post("/auth/login", data={"username": "cobra",
                                          "password": "ClaveDePrueba123!"})
        assert r.status_code == 200, "el cobrador no pudo entrar"
        cli.get("/cobros")
        cli.headers["x-csrf-token"] = cli.cookies.get("cp_csrf", "")
        yield cli, datos, Sesion

    for clave in claves:
        app.dependency_overrides.pop(clave, None)
    motor.dispose()
    bd.unlink(missing_ok=True)


def _niega(r) -> bool:
    """403 es lo propio; 302 vale en las paginas que redirigen al login."""
    return r.status_code in (302, 401, 403)


def _jpeg() -> bytes:
    b = io.BytesIO()
    Image.new("RGB", (200, 200), (30, 90, 160)).save(b, "JPEG")
    return b.getvalue()


# ── Lo que NO puede hacer ──────────────────────────────────────────────────

def test_si_puede_dar_de_alta_un_cliente_nuevo(entorno):
    """Lo encuentra en la calle y lo registra: eso es su trabajo."""
    cli, d, Sesion = entorno
    from app.database import Cliente
    r = cli.post("/clientes/nuevo",
                 data={"cedula": "999", "nombre": "Cliente Nuevo",
                       "telefono": "3001112222", "zona_id": d["zona_id"],
                       "direccion": "x", "barrio": "x", "tipo_cliente": "Regular"})
    assert r.status_code == 200, f"no pudo registrarlo: {r.text[:200]}"
    db = Sesion()
    try:
        creado = db.query(Cliente).filter(Cliente.cedula == "999").first()
        assert creado is not None, "respondio bien pero no lo creo"
        assert creado.zona_id == d["zona_id"]
    finally:
        db.close()


def test_no_puede_cambiar_los_datos_de_un_cliente(entorno):
    cli, d, Sesion = entorno
    from app.database import Cliente
    r = cli.post(f"/clientes/{d['cliente_id']}/editar",
                 data={"nombre": "CAMBIADO", "cedula": "111",
                       "telefono": "3009998888", "whatsapp": "3009998888",
                       "direccion": "OTRA DIRECCION", "barrio": "otro",
                       "zona_id": d["zona_id"], "tipo_cliente": "Regular"})
    assert _niega(r), f"devolvio {r.status_code}"
    db = Sesion()
    try:
        c = db.query(Cliente).filter(Cliente.id == d["cliente_id"]).first()
        assert c.nombre == "Cliente Original", "le cambio el nombre"
        assert c.direccion == "Calle Original 1", "le cambio la direccion"
    finally:
        db.close()


def test_no_puede_cambiar_la_foto_del_cliente(entorno):
    cli, d, Sesion = entorno
    from app.database import Cliente
    r = cli.post(f"/clientes/{d['cliente_id']}/foto",
                 files={"foto": ("x.jpg", _jpeg(), "image/jpeg")})
    assert _niega(r), f"devolvio {r.status_code}"
    db = Sesion()
    try:
        c = db.query(Cliente).filter(Cliente.id == d["cliente_id"]).first()
        assert not c.foto_path, "le puso una foto"
    finally:
        db.close()


def test_no_puede_mover_la_ubicacion_del_cliente(entorno):
    cli, d, Sesion = entorno
    from app.database import Cliente
    r = cli.post(f"/clientes/{d['cliente_id']}/ubicacion",
                 data={"lat": "6.25", "lng": "-75.56"})
    assert _niega(r), f"devolvio {r.status_code}"
    db = Sesion()
    try:
        c = db.query(Cliente).filter(Cliente.id == d["cliente_id"]).first()
        assert c.lat is None and c.lng is None, "le movio la ubicacion"
    finally:
        db.close()


def test_si_puede_prestar_y_sale_de_su_propia_caja(entorno):
    """Presta en la calle y el dinero sale de su bolsillo, asi que el
    desembolso se le atribuye a el."""
    cli, d, Sesion = entorno
    from app.database import Prestamo, Usuario, hoy_local
    r = cli.post("/prestamos/nuevo",
                 data={"cliente_id": d["cliente_id"], "zona_id": d["zona_id"],
                       "capital": "500000", "tasa_interes": "20",
                       "num_cuotas": "4", "plazo_dias": "7",
                       "fecha_inicio": hoy_local().isoformat()})
    assert r.status_code == 200 and r.json().get("ok"), \
        f"no pudo prestar: {r.text[:200]}"
    db = Sesion()
    try:
        p = db.query(Prestamo).order_by(Prestamo.id.desc()).first()
        yo = db.query(Usuario).filter(Usuario.username == "cobra").first()
        assert p.desembolsado_por_id == yo.id, "el desembolso no se le atribuyo"
        assert p.fecha_desembolso == hoy_local()
    finally:
        db.close()


def test_no_puede_apuntarle_el_desembolso_a_otro(entorno):
    """Si pudiera, prestaria sin que su caja lo notara."""
    cli, d, Sesion = entorno
    from app.database import Prestamo, Usuario, hoy_local
    db = Sesion()
    try:
        jefa_id = db.query(Usuario).filter(Usuario.username == "jefa").first().id
        yo_id = db.query(Usuario).filter(Usuario.username == "cobra").first().id
    finally:
        db.close()
    r = cli.post("/prestamos/nuevo",
                 data={"cliente_id": d["cliente_id"], "zona_id": d["zona_id"],
                       "capital": "70000", "tasa_interes": "20",
                       "num_cuotas": "4", "plazo_dias": "7",
                       "fecha_inicio": hoy_local().isoformat(),
                       "desembolsado_por": jefa_id})
    assert r.status_code == 200, r.text
    db = Sesion()
    try:
        p = db.query(Prestamo).order_by(Prestamo.id.desc()).first()
        assert p.desembolsado_por_id == yo_id, "le apunto el desembolso a otro"
    finally:
        db.close()


@pytest.mark.parametrize("ruta", ["/reportes", "/reportes/cartera",
                                  "/reportes/cobros-diarios",
                                  "/reportes/resumen-zonas"])
def test_no_puede_entrar_a_los_informes(entorno, ruta):
    cli, _, _ = entorno
    r = cli.get(ruta, follow_redirects=False)
    assert _niega(r), f"{ruta} devolvio {r.status_code}"


@pytest.mark.parametrize("ruta", ["/zonas", "/whatsapp", "/auth/usuarios", "/plataforma"])
def test_no_puede_entrar_a_la_administracion(entorno, ruta):
    cli, _, _ = entorno
    r = cli.get(ruta, follow_redirects=False)
    assert r.status_code != 200 or "no autoriz" in r.text.lower(), \
        f"{ruta} se abrio para un cobrador"


def test_el_menu_no_le_ofrece_lo_que_no_puede_usar(entorno):
    """Un enlace que responde 403 al pulsarlo es un enlace que no debe estar."""
    cli, _, _ = entorno
    html = cli.get("/cobros").text
    for ruta in ('href="/zonas"', 'href="/whatsapp"', 'href="/reportes"'):
        assert ruta not in html, f"el menu sigue ofreciendo {ruta}"


# ── Lo que SI puede hacer ──────────────────────────────────────────────────

def test_si_puede_registrar_un_cobro(entorno):
    cli, d, Sesion = entorno
    from app.database import Cuota
    r = cli.post("/cobros/registrar",
                 data={"cuota_id": d["cuota_id"], "valor_cobrado": "10000",
                       "metodo_pago": "Efectivo"})
    assert r.status_code == 200, f"no pudo cobrar: {r.text[:200]}"
    db = Sesion()
    try:
        cu = db.query(Cuota).filter(Cuota.id == d["cuota_id"]).first()
        assert cu.valor_pagado == Decimal("10000.00")
    finally:
        db.close()


def test_si_puede_adjuntar_la_evidencia_del_cobro(entorno):
    """La foto y el GPS del pago son del cobro, no del cliente: esos si son suyos."""
    cli, d, Sesion = entorno
    from app.database import Cobro
    r = cli.post("/cobros/registrar",
                 data={"cuota_id": d["cuota_id"], "valor_cobrado": "5000",
                       "metodo_pago": "Efectivo", "lat": "6.25", "lng": "-75.56"},
                 files={"foto": ("evidencia.jpg", _jpeg(), "image/jpeg")})
    assert r.status_code == 200, f"no pudo adjuntar la evidencia: {r.text[:200]}"
    db = Sesion()
    try:
        co = db.query(Cobro).order_by(Cobro.id.desc()).first()
        assert co.foto_path, "el cobro quedo sin su evidencia"
        assert co.lat_cobro is not None, "el cobro quedo sin ubicacion"
    finally:
        db.close()


def test_si_puede_marcar_que_no_pago(entorno):
    cli, d, _ = entorno
    r = cli.post("/cobros/no-pago",
                 data={"cuota_id": d["cuota_id"], "motivo": "no tenia"})
    assert r.status_code == 200, f"no pudo marcar el no pago: {r.text[:200]}"


def test_si_puede_consultar_sus_clientes(entorno):
    cli, d, _ = entorno
    assert cli.get("/cobros").status_code == 200
    assert cli.get("/clientes").status_code == 200
    assert cli.get(f"/clientes/{d['cliente_id']}").status_code == 200


# ── Cerrar la accion no basta: hay que cerrar la pantalla que la ofrece ───

def test_la_pagina_de_prestamos_va_con_la_accion(entorno):
    """La pantalla y la accion tienen que decir lo mismo.

    Cuando el cobrador no podia prestar, la comprobacion estaba solo en POST
    /prestamos/nuevo y la pagina se quedo abierta: escribiendo la direccion a
    mano entraba y se encontraba delante el formulario que el servidor le iba
    a negar. Ahora si puede prestar, asi que la pagina se abre. Lo que se
    vigila aqui no es el valor concreto: es que las dos vayan juntas.
    """
    cli, _, _ = entorno
    r = cli.get("/prestamos", follow_redirects=False)
    assert r.status_code == 200, \
        f"puede prestar pero no puede ver la pantalla: {r.status_code}"


def test_la_ficha_le_ofrece_prestar_pero_no_editar(entorno):
    """La ficha tiene que trazar la misma linea que el servidor.

    Un boton que responde 403 al pulsarlo es un boton que no debe estar: quien
    lo pulsa no sabe si fallo el sistema o si no le correspondia. Y al reves,
    quitarle el de prestar le esconderia algo que si puede hacer.
    """
    cli, d, _ = entorno
    html = cli.get(f"/clientes/{d['cliente_id']}").text
    assert 'onclick="abrirModalPrestamo()"' in html, "no le ofrece prestar y si puede"
    assert 'id="modal-prestamo"' in html, "el formulario de prestamo no llego"
    assert 'onclick="abrirEditar()"' not in html, "le ofrece editar la ficha"
    assert 'id="modal-editar-cliente"' not in html, \
        "el formulario de edicion sigue en la pagina"
    assert "guardarNota" in html, "le quito el recuadro de notas"
