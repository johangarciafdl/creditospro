"""Reparte los mensajes entre stdout y stderr segun su gravedad.

Railway -- y cualquier recolector de registros de contenedores -- clasifica
por el canal de salida: lo que va a stdout es informacion y lo que va a
stderr es error. `logging.basicConfig()` sin argumentos escribe TODO en
stderr, y uvicorn hace lo mismo con sus mensajes de arranque.

El resultado era que el panel mostraba en rojo, como errores, cosas como
"Uvicorn running on...", "Application startup complete" o "Base de datos
conectada correctamente". En treinta minutos de registro, 84 de 185
entradas eran mensajes normales marcados como error. Con ese ruido, un
error de verdad no se distingue, y al mirar el panel parece que la
aplicacion esta fallando cuando esta perfectamente sana -- que es
exactamente la conclusion a la que se llego.

Aqui se separan: INFO y DEBUG por stdout, WARNING en adelante por stderr.
"""
from __future__ import annotations

import logging
import sys

FORMATO = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"

# Los de uvicorn hay que reconducirlos aparte: los crea el propio uvicorn con
# sus manejadores y con propagate=False, asi que no heredan nada del raiz.
# "uvicorn.error", pese al nombre, es el que lleva los mensajes de arranque.
LOGGERS_DE_UVICORN = ("uvicorn", "uvicorn.error", "uvicorn.access")


class _SoloHastaInfo(logging.Filter):
    """Deja pasar lo que no es un problema, para mandarlo por stdout."""

    def filter(self, record: logging.LogRecord) -> bool:
        return record.levelno < logging.WARNING


def _manejadores() -> list[logging.Handler]:
    formato = logging.Formatter(FORMATO)

    normal = logging.StreamHandler(sys.stdout)
    normal.setLevel(logging.DEBUG)
    normal.addFilter(_SoloHastaInfo())
    normal.setFormatter(formato)

    problemas = logging.StreamHandler(sys.stderr)
    problemas.setLevel(logging.WARNING)
    problemas.setFormatter(formato)

    return [normal, problemas]


def configurar(nivel: int = logging.INFO) -> None:
    """Configura el logger raiz. Se llama al importar la aplicacion."""
    raiz = logging.getLogger()
    for viejo in list(raiz.handlers):
        raiz.removeHandler(viejo)
    for h in _manejadores():
        raiz.addHandler(h)
    raiz.setLevel(nivel)


def adoptar_uvicorn() -> None:
    """Hace que uvicorn use el mismo reparto.

    Se llama despues de que uvicorn haya montado los suyos, es decir desde
    el arranque de la aplicacion; hacerlo antes no sirve de nada porque
    uvicorn los reemplaza al iniciarse.
    """
    for nombre in LOGGERS_DE_UVICORN:
        lg = logging.getLogger(nombre)
        for viejo in list(lg.handlers):
            lg.removeHandler(viejo)
        lg.propagate = True
