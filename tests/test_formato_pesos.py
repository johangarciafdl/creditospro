"""Un solo formateador de pesos, y lo que se muestra es lo que se cobra.

Habia dos funciones llamadas cop: la de app/templates.py redondeaba al peso
entero y la de app/utils/money.py no. Las plantillas usaban una y los
mensajes de las respuestas la otra, asi que la misma cuota de 0,10 aparecia
como "$0" en la tabla de cuotas y como "$0,10" en el formulario de cobro. Un
cobrador que entrega un recibo por una cifra y registra otra descuadra el
arqueo del dia.
"""
import pathlib
import re
from decimal import Decimal

import pytest

from app.templates import templates
from app.utils.money import cop

RAIZ = pathlib.Path(__file__).resolve().parent.parent


def test_el_filtro_de_plantillas_es_el_mismo_formateador():
    assert templates.env.filters["cop"] is cop
    assert templates.env.globals["cop"] is cop


@pytest.mark.parametrize("valor,esperado", [
    (200_000, "$200.000"),
    (2_000_000, "$2.000.000"),
    (1500, "$1.500"),
    (0, "$0"),
    (None, "$0"),
    (Decimal("933.36"), "$933,36"),
    (Decimal("0.10"), "$0,10"),
    (Decimal("1777.76"), "$1.777,76"),
    (Decimal("13600.00"), "$13.600"),
])
def test_punto_para_miles_y_coma_para_centavos(valor, esperado):
    assert cop(valor) == esperado


def test_nunca_redondea_a_escondidas():
    """Si hay centavos se ven: lo mostrado no puede diferir de lo cobrado."""
    for centavos in range(1, 100):
        v = Decimal(f"10.{centavos:02d}")
        assert cop(v).endswith(f",{centavos:02d}"), f"{v} se mostro como {cop(v)}"


def test_no_reaparece_un_segundo_formateador():
    """Dos implementaciones del mismo formato acaban separandose."""
    definiciones = []
    for ruta in (RAIZ / "app").rglob("*.py"):
        if ruta.name == "money.py":
            continue
        for n, linea in enumerate(ruta.read_text(encoding="utf-8").splitlines(), 1):
            if re.match(r"\s*def cop\b", linea):
                definiciones.append(f"{ruta.relative_to(RAIZ)}:{n}")
    assert not definiciones, (
        "cop() solo se define en app/utils/money.py; tambien en: "
        + ", ".join(definiciones)
    )


def test_las_plantillas_no_formatean_pesos_a_mano():
    """El formato de EE.UU. escribe 2,000,000, que en Colombia se lee mal."""
    culpables = []
    for ruta in (RAIZ / "templates").rglob("*.html"):
        for n, linea in enumerate(ruta.read_text(encoding="utf-8").splitlines(), 1):
            if re.search(r"\{\{[^}]*\|\s*format\([\"']\$?\{?:?,", linea) or \
               re.search(r"\"\?\$\{?:,\.0f\}?\"", linea):
                culpables.append(f"{ruta.name}:{n}: {linea.strip()[:80]}")
    assert not culpables, "Usa el filtro cop:\n  " + "\n  ".join(culpables)


def test_el_navegador_tampoco_formatea_pesos_a_mano():
    """Un '$' pegado a toLocaleString es un cuarto formateador encubierto.

    Se encontraron tres a la vez: fmtCOP en base.html, fmt() en el panel y
    ocho llamadas sueltas repartidas por las plantillas. Cada una redondeaba
    distinto, asi que el mismo importe se leia de tres maneras segun la
    pantalla. La unica excepcion es la abreviatura del grafico ($1,2M), que
    no pretende ser la cifra exacta.
    """
    permitidos = {
        # La definicion del propio formateador y la abreviatura del grafico.
        ("base.html", "window.fmtCOP"),
        ("dashboard.html", "function fmt"),
    }
    culpables = []
    for ruta in (RAIZ / "templates").rglob("*.html"):
        lineas = ruta.read_text(encoding="utf-8").splitlines()
        for n, linea in enumerate(lineas, 1):
            if "toLocaleString('es-CO'" not in linea:
                continue
            # Un contador de clientes o de zonas tambien separa miles y es
            # correcto; lo que no puede es llevar un simbolo de peso delante.
            if not re.search(r"""(['"]\$['"]\s*\+|\$\$\{)""", linea):
                continue
            # Dentro de fmtCOP y de la abreviatura del grafico esta permitido.
            contexto = chr(10).join(lineas[max(0, n - 8):n])
            if any(ruta.name == f and marca in contexto for f, marca in permitidos):
                continue
            culpables.append(f"{ruta.name}:{n}: {linea.strip()[:80]}")
    assert not culpables, (
        "Usa cop() en vez de formatear pesos a mano:" + chr(10) + "  "
        + (chr(10) + "  ").join(culpables)
    )
