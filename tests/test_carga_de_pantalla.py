"""Nada de fuera puede retrasar el primer pixel.

Medido en produccion antes de este cambio: el servidor entregaba el HTML de
la ruta del cobrador en 206 ms y el usuario no veia nada hasta 1.266 ms. El
segundo entero que faltaba no era del servidor ni de la base: era el
navegador esperando a Google Fonts (una hoja de estilos que bloquea el
pintado, y que a su vez pide los archivos a fonts.gstatic.com) y a un
anime.js de cdnjs sin `defer`.

Eso es caro en el celular de un cobrador con mala señal, y ademas es una
dependencia: si esos dos servicios van lentos o estan bloqueados, la
aplicacion va lenta con ellos aunque el servidor propio este perfecto.

Estas pruebas no miden tiempos -- eso depende de la red de quien las corra --
sino la propiedad que los causaba: que la cabecera de cada pantalla no pida
nada a nadie mas. Es lo unico que, una vez arreglado, se puede volver a
romper sin que nadie lo note, porque anadir un `<link>` a un CDN es lo mas
natural del mundo al copiar un ejemplo de internet.
"""
import pathlib
import re

import pytest

RAIZ = pathlib.Path(__file__).resolve().parent.parent
PLANTILLAS = sorted((RAIZ / "templates").rglob("*.html"))

# Dominios de terceros que alguna vez estuvieron en la cabecera.
TERCEROS = re.compile(
    r"https?://(?:[a-z0-9-]+\.)*(?:googleapis\.com|gstatic\.com|cdnjs\.cloudflare\.com"
    r"|cdn\.jsdelivr\.net|unpkg\.com|code\.jquery\.com)",
    re.IGNORECASE,
)


def _sin_comentarios(html: str) -> str:
    """Los comentarios explican por que se quitaron: no son peticiones."""
    html = re.sub(r"<!--.*?-->", "", html, flags=re.DOTALL)
    return re.sub(r"\{#.*?#\}", "", html, flags=re.DOTALL)


@pytest.mark.parametrize("plantilla", PLANTILLAS, ids=lambda p: p.name)
def test_ninguna_pantalla_pide_nada_a_un_tercero(plantilla):
    html = _sin_comentarios(plantilla.read_text(encoding="utf-8"))
    encontrados = sorted(set(TERCEROS.findall(html)))
    assert not encontrados, (
        f"{plantilla.name} vuelve a pedir recursos a {encontrados}. "
        "Sirvelo desde /static/assets: un recurso de fuera en la cabecera "
        "retrasa el primer pixel y ademas deja la pantalla a merced de un "
        "servicio que no controlas."
    )


def test_los_scripts_de_la_cabecera_no_bloquean_el_pintado():
    """Un <script src> sin defer en el <head> para el parseo del HTML."""
    fallos = []
    for plantilla in PLANTILLAS:
        html = _sin_comentarios(plantilla.read_text(encoding="utf-8"))
        cabecera = html.split("</head>")[0] if "</head>" in html else ""
        for etiqueta in re.findall(r"<script\b[^>]*>", cabecera):
            if "src=" not in etiqueta:
                continue                      # inline: no descarga nada
            if "defer" in etiqueta or "async" in etiqueta:
                continue
            fallos.append(f"{plantilla.name}: {etiqueta[:90]}")
    assert not fallos, (
        "scripts que bloquean el pintado en la cabecera:\n  " + "\n  ".join(fallos)
    )


def test_las_tipografias_se_sirven_desde_el_propio_servidor():
    fuentes = RAIZ / "static" / "assets" / "fonts"
    assert (fuentes / "inter-latin.woff2").exists()
    assert (fuentes / "jetbrains-mono-latin.woff2").exists()
    # La licencia OFL exige acompañar los archivos con ella.
    licencia = (fuentes / "LICENSE.txt").read_text(encoding="utf-8")
    assert "Open Font License" in licencia
    assert "Inter" in licencia and "JetBrains Mono" in licencia


def test_el_css_declara_las_fuentes_locales():
    css = (RAIZ / "static" / "css" / "app.css").read_text(encoding="utf-8")
    assert "@font-face" in css
    assert "/static/assets/fonts/inter-latin.woff2" in css
    # swap: el texto se lee con la fuente del sistema mientras llega la real,
    # en vez de dejar huecos en blanco.
    assert "font-display:swap" in css.replace(" ", "")


def test_la_politica_de_seguridad_ya_no_admite_terceros():
    """Si la CSP sigue abierta a un CDN, volver a meterlo no falla en pruebas."""
    csp = (RAIZ / "app" / "utils" / "security_headers.py").read_text(encoding="utf-8")
    for dominio in ("cdnjs.cloudflare.com", "fonts.googleapis.com",
                    "fonts.gstatic.com", "cdn.jsdelivr.net"):
        assert dominio not in csp, f"la CSP sigue permitiendo {dominio}"


def test_las_librerias_locales_son_las_mismas_que_servia_el_cdn():
    """Descargar una libreria de un CDN y guardarla es cambiar de origen, no
    de contenido: si el archivo no es identico, se colo otra cosa."""
    import base64
    import hashlib

    ruta = RAIZ / "static" / "assets" / "vendor" / "anime-3.2.2.min.js"
    firma = "sha512-" + base64.b64encode(
        hashlib.sha512(ruta.read_bytes()).digest()).decode()
    # El mismo SRI que declaraba el <script> cuando venia de cdnjs.
    assert firma == ("sha512-aNMyYYxdIxIaot0Y1/PLuEu3eipGCmsEUBrUq+7aVyPGMFH8z0e"
                     "TP0tkqAvv34fzN6z+201d3T8HPb1svWSKHQ==")
