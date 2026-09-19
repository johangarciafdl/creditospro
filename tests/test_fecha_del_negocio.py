"""La aplicacion decide "hoy" por el reloj del negocio, no por el del servidor.

El servidor corre en UTC y los usuarios trabajan en Colombia (UTC-5). Un
`date.today()` en codigo de negocio adelanta el cambio de dia a las 19:00
hora local: los cobros de la tarde salen del informe del dia, las cuotas se
marcan vencidas antes de tiempo y la ruta del dia cambia de zona en plena
jornada. El fallo es invisible en desarrollo porque solo aparece en la franja
horaria en la que nadie prueba, asi que se vigila por estructura.
"""
import datetime
import pathlib
import re

from app.database import hoy_local, inicio_dia_negocio

RAIZ = pathlib.Path(__file__).resolve().parent.parent / "app"

# hoy_local() e inicio_dia_negocio() tienen que poder caer de vuelta en la
# hora del servidor si falta la base de husos horarios: ahi si es legitimo.
EXENTOS = {"database.py"}


def test_ningun_modulo_decide_hoy_con_el_reloj_del_servidor():
    culpables = []
    for ruta in RAIZ.rglob("*.py"):
        if ruta.name in EXENTOS:
            continue
        for n, linea in enumerate(ruta.read_text(encoding="utf-8").splitlines(), 1):
            if re.search(r"date\.today\(\)", linea):
                culpables.append(f"{ruta.relative_to(RAIZ.parent)}:{n}: {linea.strip()}")
    assert not culpables, (
        "Usa hoy_local() en vez de date.today():\n  " + "\n  ".join(culpables)
    )


def test_hoy_local_devuelve_una_fecha_plausible():
    """No puede alejarse mas de un dia de la del servidor."""
    assert abs((hoy_local() - datetime.date.today()).days) <= 1


def test_inicio_dia_negocio_es_comparable_con_marcas_guardadas():
    """Las marcas se guardan con datetime.now(): el corte tiene que ser naive."""
    inicio = inicio_dia_negocio()
    assert inicio.tzinfo is None, "mezclar naive y aware revienta la comparacion"
    assert inicio <= datetime.datetime.now(), "el dia no puede empezar en el futuro"
    assert datetime.datetime.now() - inicio < datetime.timedelta(days=2)
