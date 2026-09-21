"""Lo normal por stdout, los problemas por stderr.

Railway clasifica los registros por el canal de salida: stdout es
informacion, stderr es error. logging.basicConfig() sin argumentos manda
todo a stderr, y uvicorn hace lo mismo con sus mensajes de arranque, asi
que el panel mostraba en rojo cosas como "Application startup complete" o
"Base de datos conectada correctamente". De 185 entradas de media hora, 84
eran mensajes normales marcados como error.

El coste no es estetico: con ese ruido un error de verdad no se distingue,
y al abrir el panel parece que la aplicacion esta fallando cuando esta
sana. Eso fue exactamente lo que se concluyo al reportar una caida que no
existia.
"""
import logging
import subprocess
import sys

CODIGO = """
import logging, sys
sys.path.insert(0, %r)
from app.utils import registro_logs
registro_logs.configurar(logging.INFO)
lg = logging.getLogger("prueba")
lg.debug("mensaje-debug")
lg.info("mensaje-info")
lg.warning("mensaje-warning")
lg.error("mensaje-error")
"""


def _ejecutar(raiz):
    return subprocess.run([sys.executable, "-c", CODIGO % str(raiz)],
                          capture_output=True, text=True, timeout=120)


def test_lo_informativo_sale_por_stdout(tmp_path):
    import pathlib
    raiz = pathlib.Path(__file__).resolve().parent.parent
    r = _ejecutar(raiz)
    assert "mensaje-info" in r.stdout, "INFO debe ir a stdout"
    assert "mensaje-info" not in r.stderr, "INFO en stderr se marca como error"


def test_los_problemas_salen_por_stderr(tmp_path):
    import pathlib
    raiz = pathlib.Path(__file__).resolve().parent.parent
    r = _ejecutar(raiz)
    for nivel in ("mensaje-warning", "mensaje-error"):
        assert nivel in r.stderr, f"{nivel} debe ir a stderr"
        assert nivel not in r.stdout, f"{nivel} no debe ensuciar stdout"


def test_ningun_mensaje_sale_por_los_dos_canales():
    """Duplicarlos haria que cada aviso apareciera dos veces en el panel."""
    import pathlib
    raiz = pathlib.Path(__file__).resolve().parent.parent
    r = _ejecutar(raiz)
    for m in ("mensaje-info", "mensaje-warning", "mensaje-error"):
        assert not (m in r.stdout and m in r.stderr), f"{m} sale duplicado"


def test_adoptar_uvicorn_les_quita_sus_propios_manejadores():
    from app.utils import registro_logs
    lg = logging.getLogger("uvicorn.error")
    lg.handlers = [logging.StreamHandler(sys.stderr)]
    lg.propagate = False

    registro_logs.adoptar_uvicorn()

    assert lg.handlers == [], "debe quedarse sin manejadores propios"
    assert lg.propagate is True, "para que herede el reparto del raiz"


def test_la_aplicacion_no_vuelve_a_usar_basicConfig():
    """basicConfig() sin stream escribe en stderr: es el origen del problema."""
    import pathlib
    import re
    raiz = pathlib.Path(__file__).resolve().parent.parent
    culpables = []
    for ruta in (raiz / "app").rglob("*.py"):
        # El propio modulo lo nombra en su docstring para explicar el problema.
        if ruta.name == "registro_logs.py":
            continue
        for n, linea in enumerate(ruta.read_text(encoding="utf-8").splitlines(), 1):
            if re.search(r"logging\.basicConfig\(", linea):
                culpables.append(f"{ruta.relative_to(raiz)}:{n}")
    assert not culpables, (
        "Usa registro_logs.configurar(); basicConfig manda todo a stderr: "
        + ", ".join(culpables)
    )
