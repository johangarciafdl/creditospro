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

        # El admin de la MISMA empresa: hay cifras que solo el ve.
        jefa = Usuario(empresa_id=e.id, username="rutajefa", nombre="Ruta Jefa",
                       rol="admin", activo=True,
                       password_hash=get_password_hash("ClaveDePrueba123!"))
        db.add(jefa); db.flush()
        d["admin_id"] = jefa.id

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
                      estado="Pendiente", numero=1):
            p = Prestamo(empresa_id=e.id, cliente_id=cliente.id, zona_id=zona_id,
                         capital=Decimal("100000"), tasa_interes=Decimal("20"),
                         total_pagar=Decimal("120000"), num_cuotas=2,
                         valor_cuota=Decimal(valor), estado="Activo",
                         fecha_inicio=hoy - datetime.timedelta(days=30),
                         fecha_fin=hoy + datetime.timedelta(days=30))
            db.add(p); db.flush()
            cu = Cuota(empresa_id=e.id, prestamo_id=p.id, numero=numero,
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
        # Ya va por la 2a cuota (si fuera la 1a sin pagar seria "nuevo": gris).
        _, cu_a = _prestamo(aldia, za.id, hoy + datetime.timedelta(days=7), numero=2)
        d["cliente_aldia"], d["cuota_aldia"] = aldia.id, cu_a.id

        parcial = _cliente("Dora Parcial", "P1", za.id)
        _, cu_p = _prestamo(parcial, za.id, hoy, valor="50000", pagado="20000",
                            estado="Parcial")
        d["cliente_parcial"], d["cuota_parcial"] = parcial.id, cu_p.id

        sin_nada = _cliente("Elmer SinDeuda", "S1", za.id)
        d["cliente_sin_deuda"] = sin_nada.id

        # Cuatro cuotas atrasadas: el unico rojo.
        muy = _cliente("Gabo Atrasado", "G1", za.id)
        pm = Prestamo(empresa_id=e.id, cliente_id=muy.id, zona_id=za.id,
                      capital=Decimal("100000"), tasa_interes=Decimal("20"),
                      total_pagar=Decimal("120000"), num_cuotas=6,
                      valor_cuota=Decimal("20000"), estado="Activo",
                      fecha_inicio=hoy - datetime.timedelta(days=30),
                      fecha_fin=hoy + datetime.timedelta(days=30))
        db.add(pm); db.flush()
        for k in range(6):
            db.add(Cuota(empresa_id=e.id, prestamo_id=pm.id, numero=k + 1,
                         valor=Decimal("20000"), valor_pagado=Decimal("0"),
                         estado="Pendiente",
                         fecha_vencimiento=hoy + datetime.timedelta(days=k - 4)))
        d["cliente_muy_atrasado"] = muy.id

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
    jefa_cli = entrar(d["clave"], "rutajefa")
    ajena = entrar(d["clave_b"], "ajena")
    d["sesion_admin"] = jefa_cli
    yield cobra, ajena, d, Sesion

    for c in (cobra, jefa_cli, ajena):
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
    ("cliente_muy_atrasado", "rojo"),      # 4 cuotas atrasadas
    ("cliente_vencido", "verde"),          # 1 cuota atrasada: verde, y dice cuantas debe
    ("cliente_hoy", "verde"),              # le toca hoy, pero aun no debe nada
    ("cliente_aldia", "verde"),
    ("cliente_sin_deuda", "gris"),         # esta, pero no hay nada que cobrarle
])
def test_el_semaforo_lo_decide_el_servidor(entorno, clave, esperado):
    """Gris sin cobros; rojo desde 4 cuotas atrasadas; verde todos los demas. Lo decide el servidor para que no cambie de una pantalla
    a otra."""
    cobra, _, d, _ = entorno
    tarjeta = _por_id(_zona(cobra, d), d[clave])
    assert tarjeta is not None, f"{clave} no salio en la lista"
    assert tarjeta["estado"] == esperado, \
        f"{clave} salio {tarjeta['estado']} y deberia ser {esperado}"


def test_cuenta_las_cuotas_atrasadas_y_marca_la_de_hoy(entorno):
    cobra, _, d, _ = entorno
    cuerpo = _zona(cobra, d)
    assert _por_id(cuerpo, d["cliente_muy_atrasado"])["atrasadas"] == 4
    assert _por_id(cuerpo, d["cliente_vencido"])["atrasadas"] == 1
    hoy = _por_id(cuerpo, d["cliente_hoy"])
    assert hoy["atrasadas"] == 0 and hoy["cobrar_hoy"] is True
    assert _por_id(cuerpo, d["cliente_aldia"])["cobrar_hoy"] is False


def test_el_limite_del_rojo_es_cuatro():
    from app.routers.ruta import _estado
    assert [_estado(n, True) for n in range(6)] == \
        ["verde", "verde", "verde", "verde", "rojo", "rojo"]
    assert _estado(0, False) == "gris"
    # Nuevo: su prestamo aun no llega a la primera cuota.
    assert _estado(0, True, sin_empezar=True) == "gris"
    assert _estado(4, True, sin_empezar=True) == "rojo"


def test_el_semaforo_sigue_a_la_fecha_elegida(entorno):
    """El administrador revisa otros dias, y lo que vencia hoy ya no vence
    hoy vista desde mañana. (Al cobrador se le fija el dia de hoy: ver
    test_la_ruta_del_cobrador_es_la_de_hoy.)"""
    _, _, d, _ = entorno
    manana = (d["hoy"] + datetime.timedelta(days=1)).isoformat()
    cuerpo = _zona(d["sesion_admin"], d, fecha=manana)
    tarjeta = _por_id(cuerpo, d["cliente_hoy"])
    assert tarjeta["atrasadas"] == 1 and tarjeta["estado"] == "verde",         "vista desde mañana, la cuota de hoy esta atrasada"
    assert _por_id(cuerpo, d["cliente_aldia"])["estado"] == "verde"


# ── El dinero ─────────────────────────────────────────────────────────────

def test_lo_que_falta_es_el_saldo_y_no_el_valor_de_la_cuota(entorno):
    """Pre-llenar el cobro con el valor completo de una cuota parcial hace que
    el servidor rechace el cobro con el cliente delante."""
    cobra, _, d, _ = entorno
    pr = _por_id(_zona(cobra, d), d["cliente_parcial"])["prestamos"][0]
    assert pr["pendiente"]["cuota"] == 50000.0
    assert pr["pendiente"]["falta"] == 30000.0


def test_el_resumen_suma_lo_que_hay_que_cobrar(entorno):
    """La suma se sigue calculando; lo que cambia es a quien se le manda.

    Se pide con la sesion del administrador porque al cobrador el total por
    cobrar ya no le llega (ver mas abajo). Lo que se vigila aqui es la
    aritmetica, no el permiso.
    """
    _, _, d, _ = entorno
    cuerpo = _zona(d["sesion_admin"], d)
    r = cuerpo["resumen"]
    # Vencida (60000) + vence hoy (60000) + parcial (30000) + la siguiente del
    # muy atrasado (20000). El de al dia y el que no debe nada no entran.
    assert r["esperado"] == 170000.0, r
    assert r["por_cobrar"] == 4, r
    assert r["vencidos"] == 2, r
    assert r["clientes"] == 6, r


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
    # Abono no es pago: le sigue tocando hoy.
    assert fila["estado"] == "verde" and fila["cobrar_hoy"] is True
    assert fila["prestamos"][0]["pendiente"]["falta"] == 35000.0


def test_una_visita_sin_cobro_queda_marcada(entorno):
    cobra, _, d, _ = entorno
    r = cobra.post("/cobros/no-pago",
                   data={"cuota_id": d["cuota_vencida"], "motivo": "no tenia"})
    assert r.status_code == 200, r.text
    fila = _por_id(_zona(cobra, d), d["cliente_vencido"])
    assert fila["no_pago_hoy"] is True


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
    from app.database import RutaCobro
    from app.utils import zone_permissions as zp

    # Un miercoles: el fin de semana ve todas sus zonas y aqui no habria
    # nada que probar (y la prueba fallaria segun el dia en que se corra).
    hoy, manana = 2, 3
    original = zp.dia_semana_local
    zp.dia_semana_local = lambda: hoy
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

        # Y el fin de semana ve todas sus zonas aunque la ruta no se lo diga.
        zp.dia_semana_local = lambda: 6
        r = cobra.get("/ruta/zona", params={"zona_id": d["zona_a"],
                                            "fecha": d["hoy"].isoformat()})
        assert r.json()["clientes"], "el domingo no le abrio su zona"
    finally:
        zp.dia_semana_local = original
        db = Sesion()
        try:
            db.query(RutaCobro).delete()
            db.commit()
        finally:
            db.close()


# ── El total por cobrar es del admin ─────────────────────────────────────

def test_al_cobrador_no_se_le_manda_el_total_por_cobrar(entorno):
    """Es una cifra de negocio, no una herramienta de trabajo.

    Lo que el cobrador necesita -- cuanto le debe el cliente que tiene
    delante -- sigue en cada fila. Lo que se le quita es el total de lo que
    la empresa tiene por recoger, que no le hace falta para trabajar y si es
    algo que puede acabar fuera.

    No basta con esconder la tarjeta: si el numero viaja al navegador, esta
    a un clic de distancia en cualquier celular.
    """
    cobra, _, d, _ = entorno
    r = _zona(cobra, d)["resumen"]
    assert r["esperado"] is None, "le mando el total por cobrar"
    # Lo que si le toca ver.
    assert r["cobrado"] is not None
    assert r["vencidos"] is not None
    assert r["clientes"] > 0


def test_cada_cliente_sigue_trayendo_lo_que_debe(entorno):
    """Quitarle esto le impediria cobrar."""
    cobra, _, d, _ = entorno
    pr = _por_id(_zona(cobra, d), d["cliente_vencido"])["prestamos"][0]
    assert pr["pendiente"]["falta"] > 0, "no sabe cuanto cobrarle"
    assert pr["prestado"] > 0, "no sabe cuanto se le presto"
    assert pr["restante"] > 0, "no sabe cuanto le falta del prestamo"


def test_la_pantalla_esconde_la_tarjeta_si_no_llega_el_total():
    """La plantilla tiene que seguir al servidor, no al reves."""
    import pathlib
    html = (pathlib.Path(__file__).resolve().parent.parent / "templates"
            / "app_cobrador.html").read_text(encoding="utf-8")
    assert 'id="tarjeta-por-cobrar"' in html
    assert "r.esperado === null" in html, \
        "la tarjeta no comprueba si el servidor mando el total"


# ── Dar de alta un cliente sin prestarle ─────────────────────────────────

def test_la_vista_simple_ofrece_registrar_un_cliente(entorno):
    """A veces lo registra hoy y le presta la semana que viene; obligarle a
    inventarse un prestamo para poder anotarlo seria peor."""
    cobra, _, _, _ = entorno
    html = cobra.get("/ruta").text
    assert "abrirCliente()" in html, "no le ofrece registrar un cliente"
    assert 'id="modal-cliente"' in html, "el formulario no llego a la pagina"
    assert 'id="c-cedula"' in html and 'id="c-nombre"' in html


def test_registrar_un_cliente_desde_la_vista_simple(entorno):
    cobra, _, d, Sesion = entorno
    from app.database import Cliente
    r = cobra.post("/clientes/nuevo", data={
        "cedula": "1000001", "nombre": "Alta Sin Prestamo",
        "telefono": "3007778899", "zona_id": d["zona_a"],
        "direccion": "Calle 1", "barrio": "Centro", "tipo_cliente": "Regular"})
    assert r.status_code == 200, r.text
    db = Sesion()
    try:
        c = db.query(Cliente).filter(Cliente.cedula == "1000001").first()
        assert c is not None and c.zona_id == d["zona_a"]
    finally:
        db.close()


# ── La lista simplificada ────────────────────────────────────────────────

def test_cada_fila_trae_las_cuatro_cifras(entorno):
    """Lo que el cobrador canta en la puerta: cuanto se le presto, cuanto le
    falta, en que cuota va y cuanto es esa cuota."""
    cobra, _, d, _ = entorno
    pr = _por_id(_zona(cobra, d), d["cliente_vencido"])["prestamos"][0]
    assert pr["prestado"] == 100000.0
    assert pr["restante"] > 0
    assert pr["pendiente"]["cuota_num"] == 1
    assert pr["pendiente"]["total_cuotas"] == 2
    assert pr["pendiente"]["cuota"] == 60000.0


def test_lo_que_falta_baja_con_cada_pago(entorno):
    """El "le falta" es del prestamo entero y tiene que bajar al cobrar."""
    cobra, _, d, _ = entorno
    antes = _por_id(_zona(cobra, d), d["cliente_parcial"])["prestamos"][0]["restante"]
    r = cobra.post("/cobros/registrar", data={
        "cuota_id": d["cuota_parcial"], "valor_cobrado": "10000",
        "metodo_pago": "Efectivo"})
    assert r.status_code == 200, r.text
    despues = _por_id(_zona(cobra, d), d["cliente_parcial"])["prestamos"][0]["restante"]
    assert despues == antes - 10000.0, f"antes {antes}, despues {despues}"


def test_la_fila_no_manda_datos_que_no_se_pintan(entorno):
    """La lista de una zona grande pesaba decenas de kilobytes; lo que no se
    pinta no viaja."""
    cobra, _, d, _ = entorno
    fila = _por_id(_zona(cobra, d), d["cliente_vencido"])
    for campo in ("cedula", "direccion", "telefono", "deuda", "no_pago_motivo"):
        assert campo not in fila, f"la fila sigue mandando {campo}"


def test_la_pantalla_no_tiene_pestanas_y_solo_el_boton_de_whatsapp():
    import pathlib
    html = (pathlib.Path(__file__).resolve().parent.parent / "templates"
            / "app_cobrador.html").read_text(encoding="utf-8")
    for resto in ("verPestana", 'id="tab-cobrar"', 'id="tab-todos"', 'id="tab-cobrados"'):
        assert resto not in html, f"quedan pestañas: {resto}"
    tarjetas = html.split("const LUCES")[1].split("// ── HISTORIAL")[0]
    assert "wa.me" in tarjetas, "falta el boton de WhatsApp"
    for quitado in ("marcarNoPago", "tel:", "/clientes/${", "💰 Cobrar"):
        assert quitado not in tarjetas, f"la tarjeta sigue ofreciendo {quitado}"
    # Cobrar sigue siendo posible: cada prestamo de la tarjeta lo abre.
    assert "abrirCobro(" in tarjetas, "ya no hay forma de cobrar desde la lista"


def test_la_ruta_del_cobrador_es_la_de_hoy(entorno):
    """Un semaforo calculado para otro dia le pintaria de rojo a quien hoy
    esta al corriente. El admin si puede revisar otros dias."""
    cobra, _, d, _ = entorno
    manana_iso = (d["hoy"] + datetime.timedelta(days=1)).isoformat()
    # Pedir otro dia no cambia nada: se le calcula el de hoy.
    hoy = _por_id(_zona(cobra, d), d["cliente_hoy"])["estado"]
    otro = _por_id(_zona(cobra, d, fecha=manana_iso), d["cliente_hoy"])["estado"]
    assert otro == hoy, "al cobrador se le calculo el semaforo de otro dia"
    html = cobra.get("/ruta").text
    assert 'id="sel-fecha"' not in html, "le ofrece elegir dia"
    assert 'id="sel-fecha"' in d["sesion_admin"].get("/ruta").text, \
        "al admin le quito el selector de dia"


def test_sin_orden_propio_la_zona_sale_alfabetica(entorno):
    """La primera vez (el cobrador aun no ha movido a nadie) la zona sale por
    nombre. Ya no por urgencia: el orden lo pone el cobrador, y cobrar o
    cambiar de color no mueve a nadie."""
    cobra, _, d, Sesion = entorno
    _envejecer(Sesion, d)
    _borrar_orden(Sesion, d)
    nombres = [f["nombre"].lower() for f in _zona(cobra, d)["clientes"]]
    assert nombres == sorted(nombres), nombres
    ids = {f["cliente_id"] for f in _zona(cobra, d)["clientes"]}
    for clave in ("cliente_vencido", "cliente_hoy", "cliente_parcial",
                  "cliente_aldia", "cliente_sin_deuda"):
        assert d[clave] in ids, f"el orden escondio a {clave}"


# ── Lo recien dado de alta, arriba ────────────────────────────────────────

def _borrar_orden(Sesion, d):
    from app.database import OrdenRuta
    db = Sesion()
    try:
        db.query(OrdenRuta).filter(OrdenRuta.empresa_id == d["empresa_id"]).delete()
        db.commit()
    finally:
        db.close()


def _envejecer(Sesion, d, dias=30):
    """Todo lo sembrado pasa a ser de hace un mes: sin esto, todo es nuevo."""
    from app.database import Cliente, Prestamo, ahora_utc
    viejo = ahora_utc() - datetime.timedelta(days=dias)
    db = Sesion()
    try:
        db.query(Cliente).filter(Cliente.empresa_id == d["empresa_id"]).update(
            {Cliente.creado: viejo}, synchronize_session=False)
        db.query(Prestamo).filter(Prestamo.empresa_id == d["empresa_id"]).update(
            {Prestamo.creado: viejo}, synchronize_session=False)
        db.commit()
    finally:
        db.close()


def test_el_cliente_recien_creado_sale_primero(entorno):
    cobra, _, d, Sesion = entorno
    _envejecer(Sesion, d)
    _borrar_orden(Sesion, d)
    r = cobra.post("/ruta/prestar", data={
        "zona_id": d["zona_a"], "capital": "100000", "tasa_interes": "20",
        "num_cuotas": "20", "plazo_dias": "1",
        "cedula": "1000002", "nombre": "Zulema Recien", "telefono": "3005550001"})
    assert r.status_code == 200 and r.json().get("ok"), r.text
    filas = _zona(cobra, d)["clientes"]
    assert filas[0]["nombre"] == "Zulema Recien", [f["nombre"] for f in filas[:3]]
    # Nuevo: su primera cuota aun no vence, asi que va en gris (con su
    # prestamo dentro de la tarjeta, listo para cobrar cuando toque).
    assert filas[0]["nuevo"] and filas[0]["estado"] == "gris"
    assert filas[0]["prestamos"][0]["sin_empezar"]
    assert filas[0]["prestamos"][0]["nuevo"]
    # Lo demas, alfabetico y sin marca.
    resto = [f["nombre"].lower() for f in filas[1:]]
    assert resto == sorted(resto) and not any(f["nuevo"] for f in filas[1:])


def test_un_prestamo_nuevo_a_un_cliente_de_siempre_no_lo_mueve(entorno):
    """Se queda donde el cobrador lo tenia; el prestamo sale marcado dentro
    de su tarjeta."""
    cobra, _, d, Sesion = entorno
    _envejecer(Sesion, d)
    antes = [f["cliente_id"] for f in _zona(cobra, d)["clientes"]]
    r = cobra.post("/ruta/prestar", data={
        "zona_id": d["zona_a"], "capital": "50000", "tasa_interes": "20",
        "num_cuotas": "10", "plazo_dias": "1",
        "cliente_id": str(d["cliente_aldia"])})
    assert r.status_code == 200 and r.json().get("ok"), r.text
    cuerpo = _zona(cobra, d)
    assert [f["cliente_id"] for f in cuerpo["clientes"]] == antes
    tarjeta = _por_id(cuerpo, d["cliente_aldia"])
    assert len(tarjeta["prestamos"]) == 2, "una tarjeta por cliente, con sus prestamos"
    assert [p["nuevo"] for p in tarjeta["prestamos"]].count(True) == 1


def test_lo_de_hace_mas_de_tres_dias_ya_no_es_nuevo(entorno):
    cobra, _, d, Sesion = entorno
    _envejecer(Sesion, d, dias=4)
    assert not any(f["nuevo"] for f in _zona(cobra, d)["clientes"])


def test_la_vista_marca_lo_nuevo():
    html = Path("templates/app_cobrador.html").read_text(encoding="utf-8")
    assert "c.nuevo" in html and "fila-nuevo" in html


# ── El orden lo pone el cobrador ─────────────────────────────────────────

def _orden(cli, d, ids, **extra):
    datos = {"zona_id": d["zona_a"], "cliente_ids": ",".join(str(i) for i in ids)}
    datos.update(extra)
    return cli.post("/ruta/orden", data=datos)


def test_el_cobrador_ordena_y_el_orden_se_queda(entorno):
    cobra, _, d, Sesion = entorno
    _envejecer(Sesion, d)
    _borrar_orden(Sesion, d)
    ids = [f["cliente_id"] for f in _zona(cobra, d)["clientes"]]
    nuevo = list(reversed(ids))
    r = _orden(cobra, d, nuevo)
    assert r.status_code == 200 and r.json()["ok"], r.text
    assert [f["cliente_id"] for f in _zona(cobra, d)["clientes"]] == nuevo


def test_cobrar_no_mueve_a_nadie(entorno):
    cobra, _, d, Sesion = entorno
    antes = [f["cliente_id"] for f in _zona(cobra, d)["clientes"]]
    r = cobra.post("/cobros/registrar", data={
        "cuota_id": d["cuota_vencida"], "valor_cobrado": "60000", "metodo_pago": "Efectivo"})
    assert r.status_code == 200, r.text
    assert [f["cliente_id"] for f in _zona(cobra, d)["clientes"]] == antes


def test_ordenar_una_parte_no_desordena_el_resto(entorno):
    """La clasica (Pendientes) y el buscador mandan solo lo que se ve: los
    demas conservan su lugar."""
    cobra, _, d, _ = entorno
    ids = [f["cliente_id"] for f in _zona(cobra, d)["clientes"]]
    a, b = ids[1], ids[3]
    r = _orden(cobra, d, [b, a])           # intercambia dos
    assert r.status_code == 200, r.text
    esperado = list(ids)
    esperado[1], esperado[3] = b, a
    assert [f["cliente_id"] for f in _zona(cobra, d)["clientes"]] == esperado


def test_un_cliente_nuevo_entra_arriba_del_orden_guardado_y_se_queda(entorno):
    cobra, _, d, Sesion = entorno
    _envejecer(Sesion, d)
    ids = [f["cliente_id"] for f in _zona(cobra, d)["clientes"]]
    _orden(cobra, d, ids)
    r = cobra.post("/clientes/nuevo", data={
        "cedula": "1000003", "nombre": "Yolanda Llegando", "telefono": "3005550003",
        "zona_id": str(d["zona_a"])})
    assert r.status_code == 200, r.text
    assert _zona(cobra, d)["clientes"][0]["nombre"] == "Yolanda Llegando"
    # Pasados los dias de "nuevo", no salta a ninguna parte.
    _envejecer(Sesion, d)
    filas = _zona(cobra, d)["clientes"]
    assert filas[0]["nombre"] == "Yolanda Llegando" and not filas[0]["nuevo"]
    assert [f["cliente_id"] for f in filas[1:]] == ids


def test_el_orden_es_de_cada_cobrador_y_el_admin_lo_ve_y_lo_cambia(entorno):
    cobra, _, d, _ = entorno
    admin = d["sesion_admin"]
    propio = [f["cliente_id"] for f in _zona(cobra, d)["clientes"]]
    # Sin elegir cobrador: alfabetico y sin poder mover.
    cuerpo = _zona(admin, d)
    assert cuerpo["ordenable"] is False
    assert _orden(admin, d, propio).status_code == 400
    # Eligiendo al cobrador: su orden, y lo puede cambiar.
    cuerpo = _zona(admin, d, cobrador_id=d["usuario_id"])
    assert cuerpo["ordenable"] is True
    assert [f["cliente_id"] for f in cuerpo["clientes"]] == propio
    otro = propio[1:] + propio[:1]
    r = _orden(admin, d, otro, cobrador_id=str(d["usuario_id"]))
    assert r.status_code == 200, r.text
    assert [f["cliente_id"] for f in _zona(cobra, d)["clientes"]] == otro


def test_el_admin_mueve_la_ruta_del_cobrador_desde_cobros(entorno):
    """En Cobros el admin elige "Orden de <cobrador>": ve la lista en el orden
    de ese cobrador, la mueve, y el cobrador la ve igual en su celular."""
    cobra, _, d, _ = entorno
    admin = d["sesion_admin"]
    params = {"zona_id": d["zona_a"], "fecha": d["hoy"].isoformat()}
    assert admin.get("/cobros/pendientes-ajax", params=params).json()["ordenable"] is False
    lista = admin.get("/cobros/pendientes-ajax",
                      params=dict(params, cobrador_id=d["usuario_id"])).json()
    assert lista["ordenable"] is True
    clientes = list(dict.fromkeys(p["cliente_id"] for p in lista["pendientes"]))
    assert len(clientes) >= 2
    nuevo = clientes[::-1]
    assert _orden(admin, d, nuevo, cobrador_id=str(d["usuario_id"])).status_code == 200
    ruta = [f["cliente_id"] for f in _zona(cobra, d)["clientes"] if f["cliente_id"] in nuevo]
    assert ruta == nuevo
    pagina = admin.get("/cobros").text
    assert 'id="sel-orden"' in pagina


def test_el_cobrador_no_ordena_una_zona_que_no_es_suya(entorno):
    cobra, _, d, _ = entorno
    r = cobra.post("/ruta/orden", data={"zona_id": d["zona_b"],
                                        "cliente_ids": str(d["cliente_zona_b"])})
    assert r.status_code == 403
    # Ni el de otro cobrador, aunque mande cobrador_id: siempre es el suyo.
    r = cobra.post("/ruta/orden", data={"zona_id": d["zona_a"], "cobrador_id": "999999",
                                        "cliente_ids": str(d["cliente_hoy"])})
    assert r.status_code == 200


def test_ids_de_otra_zona_o_empresa_se_ignoran_al_ordenar(entorno):
    cobra, _, d, _ = entorno
    antes = [f["cliente_id"] for f in _zona(cobra, d)["clientes"]]
    r = _orden(cobra, d, [d["cliente_zona_b"], 987654])
    assert r.status_code == 200, r.text
    assert [f["cliente_id"] for f in _zona(cobra, d)["clientes"]] == antes


# ── Tarjeta compacta: historial y prestar ────────────────────────────────

def test_quien_no_debe_nada_viene_sin_cifras(entorno):
    cobra, _, d, _ = entorno
    t = _por_id(_zona(cobra, d), d["cliente_sin_deuda"])
    assert t["estado"] == "gris" and t["prestamos"] == []


def test_el_historial_trae_los_prestamos_y_sus_pagos(entorno):
    cobra, _, d, _ = entorno
    r = cobra.get(f"/ruta/cliente/{d['cliente_vencido']}/historial")
    assert r.status_code == 200, r.text
    h = r.json()
    assert h["prestamos"], "sin prestamos"
    pagos = [x for p in h["prestamos"] for x in p["pagos"]]
    assert pagos and all(x["valor"] > 0 for x in pagos)


def test_el_historial_de_otra_zona_o_empresa_no_se_ve(entorno):
    cobra, ajena, d, _ = entorno
    assert cobra.get(f"/ruta/cliente/{d['cliente_zona_b']}/historial").status_code == 404
    assert ajena.get(f"/ruta/cliente/{d['cliente_vencido']}/historial").status_code == 404


def test_la_vista_ya_no_tiene_la_ruta_por_cercania():
    html = Path("templates/app_cobrador.html").read_text(encoding="utf-8")
    for quitado in ("alternarCercania", "ordenarPorCercania", "google.com/maps",
                    "ubicados", "btn-cercania"):
        assert quitado not in html, f"queda {quitado}"
    for puesto in ("sortable-1.15.7.min.js", "manija", "verHistorial(", "prestarA(",
                   "guardarOrden(", "sel-cobrador"):
        assert puesto in html, f"falta {puesto}"


# ── La clasica: Cobros -> Pendientes en el mismo orden ───────────────────

def test_pendientes_de_la_clasica_sigue_el_orden_del_cobrador(entorno):
    cobra, _, d, _ = entorno
    orden_simple = [f["cliente_id"] for f in _zona(cobra, d)["clientes"]]
    r = cobra.get("/cobros/pendientes-ajax", params={"zona_id": d["zona_a"]})
    assert r.status_code == 200, r.text
    cuerpo = r.json()
    assert cuerpo["ordenable"] is True
    vistos = []
    for p in cuerpo["pendientes"]:
        if p["cliente_id"] not in vistos:
            vistos.append(p["cliente_id"])
    assert vistos == [c for c in orden_simple if c in vistos]
    # Las cuotas de un mismo cliente van juntas.
    corridas = [p["cliente_id"] for p in cuerpo["pendientes"]]
    for cid in set(corridas):
        idx = [i for i, c in enumerate(corridas) if c == cid]
        assert idx == list(range(idx[0], idx[0] + len(idx)))


def test_el_admin_ve_pendientes_por_vencimiento_sin_mover(entorno):
    _, _, d, _ = entorno
    r = d["sesion_admin"].get("/cobros/pendientes-ajax", params={"zona_id": d["zona_a"]})
    assert r.status_code == 200 and r.json()["ordenable"] is False


def test_la_clasica_trae_la_manija_y_no_aparta_a_quien_no_pago():
    html = Path("templates/cobros.html").read_text(encoding="utf-8")
    assert "sortable-1.15.7.min.js" in html and "guardarOrdenPend" in html
    assert "draggable:'.grupo-cliente'" in html


def test_abrir_una_ventana_no_mueve_el_scroll_de_la_lista():
    """Al cobrar, la lista subia y volvia a bajar a la tarjeta cobrada: el
    bloqueo del fondo usaba position:fixed, que pone el scroll a 0 mientras la
    ventana esta abierta y lo devuelve de un salto al cerrarla. Ahora se
    bloquea con overflow:hidden y la posicion no se toca."""
    css = Path("static/css/app.css").read_text(encoding="utf-8")
    base = Path("templates/base.html").read_text(encoding="utf-8")
    regla = [l for l in css.splitlines() if "modal-abierto" in l and "{" in l]
    assert regla and all("position:fixed" not in l for l in regla), regla
    assert "overflow:hidden" in regla[0]
    assert "body.style.top" not in base, "vuelve el truco que movia el scroll"
    # Y tras cobrar, la lista se refresca en su sitio.
    html = Path("templates/app_cobrador.html").read_text(encoding="utf-8")
    assert "window.alRegistrarCobro = () => recargarQuieto();" in html
