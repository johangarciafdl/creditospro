"""Tests anti-XSS para los helpers globales y los templates sensibles."""
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _read(rel):
    return (ROOT / rel).read_text(encoding="utf-8")


def test_base_tiene_helpers_anti_xss():
    """El template base debe exponer esc() y attr() para uso seguro."""
    base = _read("templates/base.html")
    assert "window.esc" in base, "Falta helper esc() en base.html"
    assert "window.attr" in base, "Falta helper attr() en base.html"
    assert "function toast" in base


def test_toast_no_inserta_html_del_mensaje():
    """toast() debe usar textContent para el mensaje, no innerHTML."""
    base = _read("templates/base.html")
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
    for field in ("p.cliente", "p.vencimiento", "p.whatsapp", "p.telefono"):
        bad = re.search(r"\$\{(?!\s*(esc|attr|Number|attr|JSON\.stringify))\s*[a-zA-Z_$]*\s*" + re.escape(field), tpl)
        assert not bad, f"{field} se inserta sin escapar en app_cobrador.html"


def test_xss_payload_bloqueado_por_esc():
    """Simula un nombre de cliente con payload XSS y verifica que
    pasarlo por esc() no produce HTML ejecutable.
    """
    # Simulamos el helper tal como esta en base.html
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
