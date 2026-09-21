"""tojson no escapa la comilla doble: rompe el atributo que lo contiene.

El filtro tojson de Jinja escapa <, >, & y la comilla simple, pero deja la
doble tal cual, porque esta pensado para ir dentro de un bloque <script> o
de un atributo delimitado por comillas simples. Puesto en uno delimitado por
comillas dobles, el primer caracter del texto cierra el atributo:

    onclick="abrirCobro(8457, {{ cliente.nombre|tojson }}, ...)"
    -> onclick="abrirCobro(8457, "

El navegador no da ningun error al cargar: el boton simplemente queda con un
onclick truncado y no hace nada al pulsarlo. Es un fallo mudo, y por eso se
vigila por estructura.
"""
import pathlib
import re

from app.templates import templates

RAIZ = pathlib.Path(__file__).resolve().parent.parent


def test_tojson_escapa_la_comilla_simple_pero_no_la_doble():
    """La premisa de la regla, comprobada y no supuesta."""
    render = templates.env.from_string("{{ n|tojson }}").render
    assert r"\u0027" in render(n="O'Brien"), "la comilla simple si se escapa"
    salida = render(n='di "hola"')
    assert salida.count('"') > 2, "la comilla doble sale literal y rompe el atributo"


def test_ningun_atributo_con_comillas_dobles_contiene_tojson():
    culpables = []
    # Atributo HTML abierto con comilla doble que contiene un {{ ... tojson }}
    patron = re.compile(r'\b[\w:-]+="[^"]*\|\s*tojson[^"]*"')
    for ruta in (RAIZ / "templates").rglob("*.html"):
        for n, linea in enumerate(ruta.read_text(encoding="utf-8").splitlines(), 1):
            if patron.search(linea):
                culpables.append(f"{ruta.name}:{n}: {linea.strip()[:100]}")
    assert not culpables, (
        "Usa comillas simples en el atributo, o pasa el valor por una "
        "constante de JS:" + chr(10) + "  " + (chr(10) + "  ").join(culpables)
    )
