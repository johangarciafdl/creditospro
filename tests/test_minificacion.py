"""El minificador no puede alterar lo que el programa hace ni lo que muestra.

La tentacion es usar una libreria conocida como jsmin, pero jsmin es anterior
a los template literals de ES6 y colapsa los espacios DENTRO de ellos:
`hola ${x} y` queda `hola ${x}y`. Este proyecto construye casi todo su HTML
con template literals, asi que eso cambiaria textos que ve el cliente. De ahi
que el minificador propio solo quite comentarios y sangria.
"""
from pathlib import Path

from app.utils.minificar import minificar_css, minificar_js

RAIZ = Path(__file__).resolve().parents[1]


def test_no_toca_el_contenido_de_los_template_literals():
    codigo = 'const h = `hola ${nombre} y ${1 + 2} adios`;'
    assert "${nombre} y ${1 + 2}" in minificar_js(codigo)


def test_conserva_los_saltos_de_linea_dentro_de_un_template_literal():
    codigo = 'const h = `<div>\n  texto\n</div>`;'
    assert "<div>\n  texto\n</div>" in minificar_js(codigo)


def test_quita_comentarios_de_linea_y_de_bloque():
    salida = minificar_js("// fuera\nconst a = 1; /* fuera\ntambien */\nconst b = 2;")
    assert "fuera" not in salida
    assert "const a = 1;" in salida and "const b = 2;" in salida


def test_no_confunde_una_expresion_regular_con_una_division():
    codigo = 'const d = String(x).replace(/[^\d]/g, ""); const y = a / b;'
    salida = minificar_js(codigo)
    assert "/[^\d]/g" in salida
    assert "a / b" in salida or "a/b" in salida


def test_una_cadena_con_barras_no_abre_un_comentario():
    codigo = 'const u = "https://ejemplo.com/ruta"; const v = 1;'
    salida = minificar_js(codigo)
    assert "https://ejemplo.com/ruta" in salida
    assert "const v = 1;" in salida


def test_no_junta_lineas_distintas():
    """Unir lineas sin analizar la insercion automatica de puntoycoma
    puede cambiar el significado del programa."""
    salida = minificar_js("let a = 1\nlet b = 2\n")
    assert "\n" in salida


def test_los_estaticos_reales_siguen_siendo_javascript_valido():
    """Guardia de regresion sobre los archivos que se sirven de verdad."""
    import subprocess
    import tempfile

    for rel in ("static/js/app.js", "static/js/pwa.js", "static/sw.js"):
        origen = RAIZ / rel
        if not origen.exists():
            continue
        salida = minificar_js(origen.read_text(encoding="utf-8"))
        with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False, encoding="utf-8") as fh:
            fh.write(salida)
            ruta = fh.name
        try:
            r = subprocess.run(["node", "--check", ruta], capture_output=True, text=True)
        except FileNotFoundError:
            import pytest
            pytest.skip("node no esta disponible para validar la sintaxis")
        finally:
            Path(ruta).unlink(missing_ok=True)
        assert r.returncode == 0, f"{rel} minificado no es JavaScript valido:\n{r.stderr}"


def test_el_css_real_se_minifica_y_conserva_las_reglas_clave():
    css = (RAIZ / "static" / "css" / "app.css").read_text(encoding="utf-8")
    salida = minificar_css(css)
    assert len(salida) < len(css)
    assert ".nav-item{display:flex" in salida


def test_no_se_generan_source_maps():
    """Un source map publicaria el codigo original en produccion."""
    from app.utils.estaticos import construir

    manifiesto = construir(RAIZ)
    dist = RAIZ / "static" / "dist"
    assert not list(dist.rglob("*.map")), "se generaron source maps"
    for destino in manifiesto.values():
        contenido = (dist / destino).read_text(encoding="utf-8")
        assert "sourceMappingURL" not in contenido


def test_el_nombre_construido_cambia_con_el_contenido():
    from app.utils.estaticos import _hash_corto

    assert _hash_corto(b"a") != _hash_corto(b"b")
