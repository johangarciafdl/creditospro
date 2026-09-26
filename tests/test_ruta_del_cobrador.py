"""La vista unica: la ruta de una zona, con su semaforo y sus miniaturas.

La diferencia de fondo con el modulo de Cobros no es el diseño. Cobros lista
**cuotas** que vencen pronto; esta lista **clientes de una zona**, incluidos
los que estan al dia, porque el cobrador pasa por su puerta igual. Eso es lo
que se comprueba primero aqui: que no sea otra vez la lista de pendientes con
otra hoja de estilos.

Lo segundo es el semaforo, que se calcula en el servidor a proposito: si cada
pantalla lo dedujera por su cuenta, el mismo cliente podria salir amarillo en
una y verde en otra.

Y lo tercero son las miniaturas, que son lo que hace viable una lista de
ochenta clientes con foto en un celular: la foto guardada son 1280 px y
decenas de kilobytes, y ochenta de esas son varios megabytes por cada vez que
el cobrador abre su ruta.
"""
import datetime
import io
import tempfile
from decimal import Decimal
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image


def _jpeg(lado=900):
    b = io.BytesIO()
    Image.new("RGB", (lado, lado), (40, 110, 180)).save(b, "JPEG", quality=90)
    return b.getvalue()


@pytest.fixture(scope="module")
def entorno():
    """Una zona con un cliente de cada color, otra zona, y otra empresa."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    bd = Path(tempfile.gettempdir()) / "creditospro_ruta_test.db"
    if bd.exists():
        bd.unlink()

    from app.database import (Base, Cliente, Cuota, Empresa, Prestamo, Usuario,
                              Zona, hoy_local)
    from app.main import app
    from app.utils.almacen_imagenes import guardar_imagen
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
        e = Empresa(nombre="RutaSA", activa=True)
        db.add(e); db.flush()
        d["empresa_id"] = e.id
        d["clave"] = assign_company_key(db, e)

        za = Zona(empresa_id=e.id, codigo="RZ1", nombre="Centro")
        zb = Zona(empresa_id=e.id, codigo="RZ2", nombre="Norte")
        db.add_all([za, zb]); db.flush()
        d["zona_a"], d["zona_b"] = za.id, zb.id

        cobrador = Usuario(empresa_id=e.id, username="rutacobra", nombre="Ruta Cobra",
                           rol="cobrador", activo=True,
                           password_hash=get_password_hash("ClaveDePrueba123!"))
        db.add(cobrador); db.flush()
        cobrador.zonas_asignadas.append(za)      # zona B NO es suya
        d["usuario_id"] = cobrador.id

        def _cliente(nombre, cedula, zona_id, foto=False):
            c = Cliente(empresa_id=e.id, cedula=cedula, nombre=nombre,
                        telefono="3001112233", zona_id=zona_id, activo=True)
            db.add(c); db.flush()
            if foto:
                nombre_archivo = guardar_imagen(db, e.id, _jpeg(), ".jpg")
                c.foto_path = f"fotos/{nombre_archivo}"
                d["foto"] = nombre_archivo
            return c

        def _prestamo(cliente, zona_id, vence, valor="60000", pagado="0",
                      estado="Pendiente"):
            p = Prestamo(empresa_id=e.id, cliente_id=cliente.id, zona_id=zona_id,
                         capital=Decimal("100000"), tasa_interes=Decimal("20"),
                         total_pagar=Decimal("120000"), num_cuotas=2,
                         valor_cuota=Decimal(valor), estado="Activo",
                         fecha_inicio=hoy - datetime.timedelta(days=30),
                         fecha_fin=hoy + datetime.timedelta(days=30))
            db.add(p); db.flush()
            cu = Cuota(empresa_id=e.id, prestamo_id=p.id, numero=1,
                       valor=Decimal(valor), valor_pagado=Decimal(pagado),
                       estado=estado, fecha_vencimiento=vence)
            db.add(cu); db.flush()
            return p, cu

        # Un cliente de cada color, todos en la zona A.
        vencido = _cliente("Ana Vencida", "V1", za.id, foto=True)
        _, cu_v = _prestamo(vencido, za.id, hoy - datetime.timedelta(days=5))
        d["cliente_vencido"], d["cuota_vencida"] = vencido.id, cu_v.id

        hoy_c = _cliente("Beto Hoy", "H1", za.id)
        _, cu_h = _prestamo(hoy_c, za.id, hoy)
        d["cliente_hoy"], d["cuota_hoy"] = hoy_c.id, cu_h.id

        aldia = _cliente("Carla AlDia", "A1", za.id)
        _, cu_a = _prestamo(aldia, za.id, hoy + datetime.timedelta(days=7))
        d["cliente_aldia"], d["cuota_aldia"] = aldia.id, cu_a.id

        parcial = _cliente("Dora Parcial", "P1", za.id)
        _, cu_p = _prestamo(parcial, za.id, hoy, valor="50000", pagado="20000",
                            estado="Parcial")
        d["cliente_parcial"], d["cuota_parcial"] = parcial.id, cu_p.id

        sin_nada = _cliente("Elmer SinDeuda", "S1", za.id)
        d["cliente_sin_deuda"] = sin_nada.id

        # Otra zona de la misma empresa, que el cobrador no tiene asignada.
        otro_zona = _cliente("Fito DeNorte", "N1", zb.id)
        _prestamo(otro_zona, zb.id, hoy)
        d["cliente_zona_b"] = otro_zona.id

        # Y otra empresa entera, con su cliente y su foto.
        e2 = Empresa(nombre="OtraRutaSA", activa=True)
        db.add(e2); db.flush()
        d["empresa_b"] = e2.id
        d["clave_b"] = assign_company_key(db, e2)
        z2 = Zona(empresa_id=e2.id, codigo="RZ9", nombre="Ajena")
        db.add(z2); db.flush()
        cajeno = Cliente(empresa_id=e2.id, cedula="X9", nombre="Cliente Ajeno",
                         telefono="3009998877", zona_id=z2.id, activo=True)
        db.add(cajeno); db.flush()
        foto_ajena = guardar_imagen(db, e2.id, _jpeg(), ".jpg")
        cajeno.foto_path = f"fotos/{foto_ajena}"
        d["foto_ajena"] = foto_ajena
        d["zona_b_empresa"] = z2.id
        db.add(Usuario(empresa_id=e2.id, username="ajena", nombre="Ajena",
                       rol="admin", activo=True,
                       password_hash=get_password_hash("ClaveDePrueba123!")))
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
        cli.get("/ruta")
        cli.headers["x-csrf-token"] = cli.cookies.get("cp_csrf", "")
        return cli

    cobra = entrar(d["clave"], "rutacobra")
    ajena = entrar(d["clave_b"], "ajena")
    yield cobra, ajena, d, Sesion

    for c in (cobra, ajena):
        c.__exit__(None, None, None)
    for clave in claves:
        app.dependency_overrides.pop(clave, None)
    motor.dispose()
    bd.unlink(missing_ok=True)


def _zona(cli, d, **extra):
    params = {"zona_id": d["zona_a"]}
    params.update(extra)
    r = cli.get("/ruta/zona", params=params)
    assert r.status_code == 200, r.text
    return r.json()


def _por_id(cuerpo, cliente_id):
    for f in cuerpo["clientes"]:
        if f["cliente_id"] == cliente_id:
            return f
    return None


# ── Lista clientes de una zona, no cuotas ─────────────────────────────────

def test_trae_todos_los_clientes_de_la_zona_incluidos_los_que_estan_al_dia(entorno):
    """Es la diferencia con la lista de pendientes: el cobrador pasa por la
    puerta del que esta al dia igual que por la del que debe."""
    cobra, _, d, _ = entorno
    cuerpo = _zona(cobra, d)
    ids = {f["cliente_id"] for f in cuerpo["clientes"]}
    for clave in ("cliente_vencido", "cliente_hoy", "cliente_parcial",
                  "cliente_aldia", "cliente_sin_deuda"):
        assert d[clave] in ids, f"falta {clave} en la ruta"


def test_no_trae_clientes_de_otra_zona(entorno):
    cobra, _, d, _ = entorno
    cuerpo = _zona(cobra, d)
    ids = {f["cliente_id"] for f in cuerpo["clientes"]}
    assert d["cliente_zona_b"] not in ids


def test_la_zona_que_no_es_suya_devuelve_vacio(entorno):
    """Pedirla a mano no la abre: la zona B no esta entre sus asignadas."""
    cobra, _, d, _ = entorno
    r = cobra.get("/ruta/zona", params={"zona_id": d["zona_b"]})
    assert r.status_code == 200
    assert r.json()["clientes"] == []


def test_no_trae_clientes_de_otra_empresa(entorno):
    """El aislamiento no depende de que la zona pedida sea de la empresa."""
    cobra, _, d, _ = entorno
    r = cobra.get("/ruta/zona", params={"zona_id": d["zona_b_empresa"]})
    assert r.status_code == 200
    assert r.json()["clientes"] == []


def test_sin_sesion_no_devuelve_nada(entorno):
    from app.main import app
    with TestClient(app) as anon:
        r = anon.get("/ruta/zona", params={"zona_id": 1}, follow_redirects=False)
        assert r.status_code in (302, 401), f"devolvio {r.status_code}"


def test_el_buscador_filtra_por_nombre(entorno):
    cobra, _, d, _ = entorno
    cuerpo = _zona(cobra, d, q="Ana")
    assert len(cuerpo["clientes"]) == 1
    assert cuerpo["clientes"][0]["cliente_id"] == d["cliente_vencido"]


def test_una_fecha_invalida_se_rechaza(entorno):
    cobra, _, d, _ = entorno
    r = cobra.get("/ruta/zona", params={"zona_id": d["zona_a"], "fecha": "ayer"})
    assert r.status_code == 400


# ── El semaforo ───────────────────────────────────────────────────────────

@pytest.mark.parametrize("clave,esperado", [
    ("cliente_vencido", "rojo"),
    ("cliente_hoy", "amarillo"),
    ("cliente_aldia", "verde"),
    ("cliente_sin_deuda", "gris"),
])
def test_el_semaforo_lo_decide_el_servidor(entorno, clave, esperado):
    cobra, _, d, _ = entorno
    cuerpo = _zona(cobra, d)
    fila = _por_id(cuerpo, d[clave])
    assert fila is not None, f"{clave} no salio en la lista"
    assert fila["semaforo"] == esperado, \
        f"{clave} salio {fila['semaforo']} y deberia ser {esperado}"


def test_el_semaforo_sigue_a_la_fecha_elegida(entorno):
    """Un cobrador que cuadra la ruta por la noche mira otro dia, y lo que
    vencia hoy ya no vence hoy."""
    cobra, _, d, _ = entorno
    manana = (d["hoy"] + datetime.timedelta(days=1)).isoformat()
    cuerpo = _zona(cobra, d, fecha=manana)
    assert _por_id(cuerpo, d["cliente_hoy"])["semaforo"] == "rojo", \
        "vista desde mañana, la cuota de hoy esta vencida"
    assert _por_id(cuerpo, d["cliente_aldia"])["semaforo"] == "verde"


# ── El dinero ─────────────────────────────────────────────────────────────

def test_lo_que_falta_es_el_saldo_y_no_el_valor_de_la_cuota(entorno):
    """Pre-llenar el cobro con el valor completo de una cuota parcial hace que
    el servidor rechace el cobro con el cliente delante."""
    cobra, _, d, _ = entorno
    fila = _por_id(_zona(cobra, d), d["cliente_parcial"])
    assert fila["pendiente"]["valor"] == 50000.0
    assert fila["pendiente"]["valor_pagado"] == 20000.0
    assert fila["pendiente"]["falta"] == 30000.0


def test_el_resumen_suma_lo_que_hay_que_cobrar(entorno):
    cobra, _, d, _ = entorno
    cuerpo = _zona(cobra, d)
    r = cuerpo["resumen"]
    # Vencida (60000) + vence hoy (60000) + parcial (30000). El de al dia y el
    # que no debe nada no entran en lo de hoy.
    assert r["esperado"] == 150000.0, r
    assert r["por_cobrar"] == 3, r
    assert r["vencidos"] == 1, r
    assert r["clientes"] == 5, r


def test_un_cobro_del_dia_aparece_en_la_fila_y_en_el_resumen(entorno):
    cobra, _, d, _ = entorno
    r = cobra.post("/cobros/registrar",
                   data={"cuota_id": d["cuota_hoy"], "valor_cobrado": "25000",
                         "metodo_pago": "Efectivo"})
    assert r.status_code == 200, r.text
    cuerpo = _zona(cobra, d)
    fila = _por_id(cuerpo, d["cliente_hoy"])
    assert fila["cobrado_hoy"] == 25000.0
    assert cuerpo["resumen"]["cobrado"] == 25000.0
    assert cuerpo["resumen"]["cobrados"] == 1
    # Y sigue en "por cobrar": abono no es pago.
    assert fila["semaforo"] == "amarillo"
    assert fila["pendiente"]["falta"] == 35000.0


def test_una_visita_sin_cobro_queda_marcada(entorno):
    cobra, _, d, _ = entorno
    r = cobra.post("/cobros/no-pago",
                   data={"cuota_id": d["cuota_vencida"], "motivo": "no tenia"})
    assert r.status_code == 200, r.text
    fila = _por_id(_zona(cobra, d), d["cliente_vencido"])
    assert fila["no_pago_hoy"] is True
    assert "no tenia" in fila["no_pago_motivo"]


# ── Las miniaturas ────────────────────────────────────────────────────────

def test_la_lista_manda_el_nombre_de_la_foto_no_la_foto(entorno):
    """Si la lista trajera las fotos, serian megabytes en la primera peticion."""
    cobra, _, d, _ = entorno
    fila = _por_id(_zona(cobra, d), d["cliente_vencido"])
    assert fila["miniatura"] == d["foto"]
    assert _por_id(_zona(cobra, d), d["cliente_hoy"])["miniatura"] is None


def test_la_miniatura_pesa_mucho_menos_que_la_foto(entorno):
    cobra, _, d, _ = entorno
    foto = cobra.get(f"/uploads/fotos/{d['foto']}")
    mini = cobra.get(f"/uploads/miniaturas/{d['foto']}")
    assert foto.status_code == 200 and mini.status_code == 200, mini.text
    assert len(mini.content) < len(foto.content) / 3, \
        f"la miniatura pesa {len(mini.content)} y la foto {len(foto.content)}"
    with Image.open(io.BytesIO(mini.content)) as img:
        assert max(img.size) <= 160, f"la miniatura mide {img.size}"


def test_la_miniatura_se_genera_una_vez_y_se_reutiliza(entorno):
    """Reducir la imagen en cada visita es trabajo repetido por nada."""
    cobra, _, d, Sesion = entorno
    from app.database import Archivo
    from app.utils.almacen_imagenes import nombre_miniatura

    mini = nombre_miniatura(d["foto"])
    for _ in range(3):
        assert cobra.get(f"/uploads/miniaturas/{d['foto']}").status_code == 200
    db = Sesion()
    try:
        assert db.query(Archivo).filter(Archivo.nombre == mini).count() == 1, \
            "se guardo la miniatura mas de una vez"
    finally:
        db.close()


def test_una_empresa_no_puede_pedir_la_miniatura_de_otra(entorno):
    """Reducir una imagen no la hace menos privada."""
    cobra, _, d, _ = entorno
    r = cobra.get(f"/uploads/miniaturas/{d['foto_ajena']}")
    assert r.status_code == 404, f"devolvio {r.status_code}"


def test_sin_sesion_la_miniatura_no_se_sirve(entorno):
    from app.main import app
    _, _, d, _ = entorno
    with TestClient(app) as anon:
        r = anon.get(f"/uploads/miniaturas/{d['foto']}", follow_redirects=False)
        assert r.status_code in (302, 404), f"devolvio {r.status_code}"


def test_borrar_la_foto_se_lleva_la_miniatura(entorno):
    """Si no, queda un objeto en el bucket que nada va a pedir nunca mas."""
    cobra, _, d, Sesion = entorno
    from app.database import Archivo
    from app.utils.almacen_imagenes import (borrar_imagen, guardar_imagen,
                                            leer_miniatura, nombre_miniatura)

    db = Sesion()
    try:
        nombre = guardar_imagen(db, d["empresa_id"], _jpeg(), ".jpg")
        db.commit()
        assert leer_miniatura(db, d["empresa_id"], nombre) is not None
        mini = nombre_miniatura(nombre)
        assert db.query(Archivo).filter(Archivo.nombre == mini).count() == 1
        borrar_imagen(db, d["empresa_id"], nombre)
        db.commit()
        assert db.query(Archivo).filter(Archivo.nombre == mini).count() == 0, \
            "la miniatura sobrevivio a su foto"
        assert db.query(Archivo).filter(Archivo.nombre == nombre).count() == 0
    finally:
        db.close()


# ── Un 204 no lleva cuerpo ────────────────────────────────────────────────

def test_el_reporte_csp_devuelve_un_204_de_verdad():
    """Un 204 con cuerpo revienta la respuesta y ensucia el registro entero.

    El navegador manda un reporte por cada violacion de CSP, y cada pantalla
    de la aplicacion provoca varias, asi que la traza salia en produccion
    decenas de veces al dia tapando los errores que si importan.
    """
    from app.main import app
    from fastapi.testclient import TestClient

    with TestClient(app) as cli:
        r = cli.post("/csp-report", json={"csp-report": {
            "document-uri": "https://ejemplo/x", "violated-directive": "script-src",
        }})
        assert r.status_code == 204, r.text
        assert r.content == b"", f"un 204 no puede llevar cuerpo: {r.content!r}"

        # Y un cuerpo que no es JSON tampoco debe llevar contenido.
        r = cli.post("/csp-report", content=b"esto no es json",
                     headers={"content-type": "application/csp-report"})
        assert r.status_code == 204
        assert r.content == b""


# ── Cerrar sesion, arriba y una sola vez ──────────────────────────────────

def test_cerrar_sesion_esta_arriba_y_es_un_solo_boton(entorno):
    """Al fondo de la barra lateral lo tapaba la barra del sistema.

    En varios celulares la barra de navegacion o el recorte de la pantalla se
    comen lo que queda pegado al borde inferior, y el cobrador veia el boton a
    medias o no lo veia. Y uno solo: si el mismo control sale arriba y abajo,
    uno de los dos es el tapado y nadie sabe cual funciona.
    """
    cobra, _, _, _ = entorno
    html = cobra.get("/ruta").text
    assert html.count('href="/auth/logout"') == 1, \
        "debe haber exactamente un boton de cerrar sesion"
    cabecera = html.split('<header class="topbar"')[1].split("</header>")[0]
    assert 'href="/auth/logout"' in cabecera, \
        "cerrar sesion debe estar en la barra superior"
    assert "sidebar-footer" in html, "el pie de la barra lateral sigue existiendo"
    pie = html.split('<div class="sidebar-footer">')[1].split("</aside>")[0]
    assert "/auth/logout" not in pie, \
        "quedo un segundo boton de cerrar sesion pegado al borde inferior"


# ── La ruta semanal manda sobre la vista del dia ──────────────────────────

def test_la_vista_solo_ofrece_las_zonas_que_le_tocan_hoy(entorno):
    """El enlace entre las dos mitades de la automatizacion.

    El administrador configura, desde Usuarios, que zonas cobra cada dia de la
    semana. Esta prueba es la que comprueba que eso llega hasta la pantalla
    del cobrador: con una ruta configurada, el selector deja de ofrecerle sus
    zonas asignadas y le ofrece solo las de hoy. Sin ella, el administrador
    podria configurar la semana entera y el cobrador seguir viendolo todo.
    """
    cobra, _, d, Sesion = entorno
    from app.database import RutaCobro, dia_semana_local

    hoy = dia_semana_local()
    manana = (hoy + 1) % 7
    db = Sesion()
    try:
        db.query(RutaCobro).delete()
        # Hoy no le toca la zona A; le toca manana.
        db.add(RutaCobro(empresa_id=d["empresa_id"], usuario_id=d["usuario_id"],
                         dia_semana=manana, zona_id=d["zona_a"]))
        db.commit()
    finally:
        db.close()

    try:
        html = cobra.get("/ruta").text
        assert "no tienes ninguna zona asignada" in html.lower(), \
            "hoy no le toca ninguna zona y aun asi le ofrece alguna"

        # Y pedir a mano la zona que hoy no le toca tampoco la abre.
        r = cobra.get("/ruta/zona", params={"zona_id": d["zona_a"],
                                            "fecha": d["hoy"].isoformat()})
        assert r.status_code == 200
        assert r.json()["clientes"] == [], "le dio los clientes de una zona que hoy no cobra"

        # Ahora si le toca: la zona vuelve a aparecer.
        db = Sesion()
        try:
            db.query(RutaCobro).delete()
            db.add(RutaCobro(empresa_id=d["empresa_id"], usuario_id=d["usuario_id"],
                             dia_semana=hoy, zona_id=d["zona_a"]))
            db.commit()
        finally:
            db.close()
        html = cobra.get("/ruta").text
        assert 'id="sel-zona"' in html and "Centro" in html, \
            "le toca la zona hoy y no se la ofrece"
    finally:
        db = Sesion()
        try:
            db.query(RutaCobro).delete()
            db.commit()
        finally:
            db.close()
