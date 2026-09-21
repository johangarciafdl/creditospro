"""Toda pantalla que incluya el modal de cobro debe refrescarse despues.

El modal compartido no sabe que hay alrededor, asi que al terminar llama a
window.alRegistrarCobro y cada pantalla decide como recargarse. Cobros era
la unica que no la definia: el cobro se registraba bien, pero la lista se
quedaba igual. El cliente al que se acababa de cobrar seguia ahi y, al
pulsar Cobrar otra vez, el servidor respondia "la cuota ya esta pagada" --
un cobrador con prisa lo lee como que el cobro no entro.

Es un fallo mudo: no hay error en consola ni en el servidor, solo una lista
que no cambia. Por eso se vigila por estructura.
"""
import pathlib
import re

PLANTILLAS = pathlib.Path(__file__).resolve().parent.parent / "templates"


def _incluyen_el_modal():
    for ruta in PLANTILLAS.glob("*.html"):
        if ruta.name.startswith("_"):
            continue
        texto = ruta.read_text(encoding="utf-8")
        if "_modal_cobro_js.html" in texto:
            yield ruta, texto


def test_el_modal_compartido_lo_incluye_mas_de_una_pantalla():
    """Si nadie lo incluye, la prueba de abajo pasaria sin comprobar nada."""
    assert len(list(_incluyen_el_modal())) >= 2


def test_cada_pantalla_con_modal_de_cobro_define_como_refrescarse():
    culpables = [
        ruta.name for ruta, texto in _incluyen_el_modal()
        if not re.search(r"window\.alRegistrarCobro\s*=", texto)
    ]
    assert not culpables, (
        "Estas pantallas registran el cobro pero no se actualizan despues: "
        + ", ".join(culpables)
        + ". Define window.alRegistrarCobro para recargar la lista."
    )
