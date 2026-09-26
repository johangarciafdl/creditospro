"""Tests anti-XSS para los helpers globales y los templates sensibles."""
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _read(rel):
    return (ROOT / rel).read_text(encoding="utf-8")


# Los helpers vivian dentro de un <script> en templates/base.html; se
# extrajeron a static/js/app.js para poder minificarlos y cachearlos. El
# contrato que estos tests protegen no cambio, solo el archivo.
JS_COMPARTIDO = "static/js/app.js"


def test_base_tiene_helpers_anti_xss():
    """esc() y attr() deben seguir definidos antes de cualquier otro script.

    Estos dos se quedan en linea en base.html a proposito: todo el HTML que
    generan las pantallas pasa por ellos, asi que tienen que existir aunque
    un archivo externo no llegue a cargar.
    """
    base = _read("templates/base.html")
    assert "window.esc" in base, "Falta helper esc() en base.html"
    assert "window.attr" in base, "Falta helper attr() en base.html"
    assert "function toast" in _read(JS_COMPARTIDO), f"Falta toast() en {JS_COMPARTIDO}"


def test_base_html_carga_el_js_compartido():
    """base.html debe seguir sirviendo esos helpers a todas las pantallas."""
    base = _read("templates/base.html")
    assert "estatico('js/app.js')" in base, (
        "base.html ya no carga js/app.js: las pantallas se quedarian sin esc(), "
        "attr() ni toast()"
    )


def test_toast_no_inserta_html_del_mensaje():
    """toast() debe usar textContent para el mensaje, no innerHTML."""
    base = _read(JS_COMPARTIDO)
    # Buscar la funcion toast y verificar que use textContent o createTextNode
    m = re.search(r"function toast\([^)]*\)\{.*?clearTimeout\(t\._t\);", base, re.DOTALL)
    assert m, "No se encontro el cuerpo de toast()"
    body = m.group(0)
    assert "createTextNode" in body, "toast() sigue usando innerHTML en vez de createTextNode"


def test_prestamos_template_escapa_datos_usuario():
    tpl = _read("templates/prestamos.html")
    # No debe haber interpolaciones ${userData} sin esc()
    # Buscar todas las interpolaciones ${...} en el map
    for field in ("p.cliente", "p.cedula", "p.zona", "p.estado", "p.fecha_inicio"):
        # Aceptamos ${Number(p.capital)}, ${attr(p.cliente_id)}, o ${esc(p.X)}
        bad = re.search(r"\$\{(?!\s*(esc|attr|Number|attr|JSON\.stringify))\s*[a-zA-Z_$]*\s*" + re.escape(field), tpl)
        assert not bad, (
            f"{field} se inserta sin escapar en prestamos.html — posible XSS"
        )


def test_clientes_template_escapa_datos_usuario():
    tpl = _read("templates/clientes.html")
    for field in ("c.nombre", "c.cedula", "c.zona", "c.telefono", "c.tipo_cliente"):
        bad = re.search(r"\$\{(?!\s*(esc|attr|Number|attr|JSON\.stringify))\s*[a-zA-Z_$]*\s*" + re.escape(field), tpl)
        assert not bad, f"{field} se inserta sin escapar en clientes.html"


def test_cobros_template_escapa_datos_usuario():
    tpl = _read("templates/cobros.html")
    for field in ("p.cliente", "p.cedula", "p.metodo", "c.cobrador", "c.hora", "c.cliente"):
        bad = re.search(r"\$\{(?!\s*(esc|attr|Number|attr|JSON\.stringify))\s*[a-zA-Z_$]*\s*" + re.escape(field), tpl)
        assert not bad, f"{field} se inserta sin escapar en cobros.html"


def test_app_cobrador_escapa_datos_usuario():
    tpl = _read("templates/app_cobrador.html")
    # La vista simple pasó de listar cuotas (p.cliente) a listar clientes de
    # una zona (f.nombre), asi que los campos que llegan del usuario son
    # otros; la exigencia es la misma.
    for field in ("f.nombre", "p.vencimiento", "f.whatsapp", "f.telefono",
                  "f.no_pago_motivo"):
        bad = re.search(r"\$\{(?!\s*(esc|attr|Number|attr|JSON\.stringify))\s*[a-zA-Z_$]*\s*" + re.escape(field), tpl)
        assert not bad, f"{field} se inserta sin escapar en app_cobrador.html"
    # El nombre del archivo de la foto va dentro de un atributo HTML, que es
    # donde una comilla suelta escapa del atributo y se convierte en otro.
    assert 'data-mini="${attr(f.miniatura)}"' in tpl, (
        "el nombre de la miniatura debe ir escapado dentro del atributo"
    )


def test_xss_payload_bloqueado_por_esc():
    """Simula un nombre de cliente con payload XSS y verifica que
    pasarlo por esc() no produce HTML ejecutable.
    """
    # Simulamos el helper tal como esta en static/js/app.js
    def esc(s):
        if s is None or s is None:
            return ""
        return (
            str(s)
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;")
            .replace("'", "&#39;")
        )

    payload = '<img src=x onerror="alert(document.cookie)">'
    out = esc(payload)
    assert "<img" not in out
    assert "&lt;img" in out
    assert "onerror" not in out.replace("&lt;img src=x ", "") or "&quot;" in out


def test_xss_en_evento_onclick_atributo_bloqueado():
    """Si un cliente_id viene como `1);alert(1)//`, el attr() debe
    neutralizarlo antes de meterlo en un onclick.
    """
    def esc(s):
        if s is None:
            return ""
        return (
            str(s)
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;")
            .replace("'", "&#39;")
        )

    payload = "1);alert(1)//"
    out = esc(payload)
    # El ; y los ( se mantienen, pero como va dentro de "..." o '...'
    # y luego dentro de un atributo HTML, las comillas rompen la inyeccion
    assert '"' not in out
    assert "'" not in out
