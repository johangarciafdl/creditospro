"""La vista simple trabaja sin señal.

En la calle la señal se va. Antes, sin señal la ruta no cargaba ("No hay
conexion") y el cobrador no sabia a quien visitar; el cobro si se guardaba en
el celular, pero el "no pagó" y el orden se perdian. Lo probado a mano en el
navegador (cargar, cortar la red, recargar, cobrar, "no pagó", mover, volver
la señal y ver que todo llega una sola vez) se vigila aqui por piezas.
"""
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent


def _leer(ruta):
    return (RAIZ / ruta).read_text(encoding="utf-8")


def test_la_pantalla_de_la_ruta_queda_guardada_en_el_celular():
    sw = _leer("static/sw.js")
    lista = sw.split("const STATIC = [")[1].split("];")[0]
    assert "'/ruta'" in lista and "'/caja'" in lista


def test_el_worker_no_sirve_datos_viejos_de_la_ruta_como_si_fueran_frescos():
    """Los datos los guarda la pantalla con su hora; si el worker los sirviera
    del cache, la pantalla no sabria que son viejos."""
    sw = _leer("static/sw.js")
    assert "url.pathname.startsWith('/ruta/')" in sw


def test_la_ruta_guarda_su_copia_y_la_usa_sin_senal():
    html = _leer("templates/app_cobrador.html")
    for pieza in ("_guardarCopia(d)", "_usarCopia(", "id=\"sin-senal\"",
                  "Sin señal · datos de las", "if (!navigator.onLine) { _usarCopia("):
        assert pieza in html, f"falta {pieza}"
    # La copia es de cada usuario.
    assert "'cp-ruta:' + _USUARIO" in html


def test_lo_registrado_sin_senal_se_refleja_en_la_copia():
    html = _leer("templates/app_cobrador.html")
    for gancho in ("window.alGuardarCobroSinSenal", "window.alNoPagoSinSenal",
                   "Sin enviar"):
        assert gancho in html, f"falta {gancho}"


def test_el_no_pago_y_el_orden_sin_senal_van_a_la_cola():
    modal = _leer("templates/_modal_cobro_js.html")
    assert "encolarSinSenal('/cobros/no-pago'" in modal
    assert "window.alGuardarCobroSinSenal" in modal
    for plantilla in ("templates/app_cobrador.html", "templates/cobros.html"):
        assert "encolarSinSenal('/ruta/orden'" in _leer(plantilla), plantilla


def test_la_cola_se_envia_al_volver_la_senal_y_no_reintenta_para_siempre():
    app = _leer("static/js/app.js")
    assert "window.addEventListener('online', () => setTimeout(vaciarColaSinSenal" in app
    bloque = app.split("async function vaciarColaSinSenal")[1][:1500]
    # Un 4xx definitivo se descarta; un 5xx se reintenta.
    assert "r.status >= 400 && r.status < 500" in bloque


def test_al_cerrar_sesion_se_borran_las_copias_y_se_avisa_de_lo_pendiente():
    app = _leer("static/js/app.js")
    salir = app.split("function cerrarSesion")[1][:1400]
    assert "pendientesSinSenal()" in salir
    assert "_borrarDatosSinSenal()" in salir
    assert "await vaciarColaSinSenal()" in salir


def test_el_no_pago_repetido_no_duplica(tmp_path):
    """Reintentar un "no pagó" de la cola es seguro: el servidor lo marca
    como duplicado en vez de crear otro."""
    cobros = _leer("app/routers/cobros.py")
    bloque = cobros.split('@router.post("/no-pago")')[1][:6000]
    assert "duplicado" in bloque
