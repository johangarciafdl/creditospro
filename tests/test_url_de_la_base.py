"""La URL de la base de datos nombra siempre su controlador.

Una URL que empieza por `postgresql://` no dice con que biblioteca
conectarse: delega en el valor por defecto de SQLAlchemy. Funciono durante
anos y luego el despliegue dejo de arrancar sin que nadie tocara el codigo,
porque SQLAlchemy 2.1 cambio ese valor por defecto de psycopg2 a psycopg 3
y el proyecto solo instala psycopg2:

    ModuleNotFoundError: No module named 'psycopg'

Lo grave no fue la caida, que Railway contuvo conservando el despliegue
anterior. Lo grave es que las pruebas seguian en verde: el entorno de
desarrollo tenia SQLAlchemy 2.0, donde el valor por defecto era el otro.
"Probado" y "desplegado" no eran el mismo programa, y ninguna prueba podia
notarlo porque ninguna miraba la version.

Estas pruebas cubren las dos mitades del arreglo: que la URL nombre el
controlador, y que el rango de versiones no vuelva a dejar entrar sola una
version que cambia esa decision.
"""
import pathlib
import re

import pytest

from app.utils.url_bd import CONTROLADOR_POSTGRES, normalizar

RAIZ = pathlib.Path(__file__).resolve().parent.parent


@pytest.mark.parametrize("entrada", [
    "postgresql://usuario:clave@host:5432/base",
    "postgres://usuario:clave@host:5432/base",      # forma antigua de algunos proveedores
])
def test_una_url_de_postgres_siempre_nombra_su_controlador(entrada):
    salida = normalizar(entrada)
    assert salida.startswith(f"postgresql+{CONTROLADOR_POSTGRES}://"), salida
    assert "@host:5432/base" in salida, "no debe perder el resto de la URL"


def test_una_url_que_ya_elige_controlador_se_respeta():
    """Para poder forzar otro sin tocar codigo."""
    entrada = "postgresql+psycopg://usuario:clave@host/base"
    assert normalizar(entrada) == entrada


def test_sqlite_no_se_toca():
    for u in ("sqlite:///./local.db", "sqlite:///:memory:"):
        assert normalizar(u) == u


def test_una_url_vacia_no_revienta():
    assert normalizar("") == ""
    assert normalizar(None) is None


def test_el_controlador_declarado_es_el_que_se_instala():
    """Si se cambia uno sin el otro, el contenedor no arranca."""
    requisitos = (RAIZ / "requirements.txt").read_text(encoding="utf-8")
    if CONTROLADOR_POSTGRES == "psycopg2":
        assert re.search(r"^psycopg2-binary", requisitos, re.M), \
            "url_bd pide psycopg2 pero requirements.txt no lo instala"
    elif CONTROLADOR_POSTGRES == "psycopg":
        assert re.search(r"^psycopg\b", requisitos, re.M), \
            "url_bd pide psycopg 3 pero requirements.txt no lo instala"


def test_sqlalchemy_esta_acotado_por_debajo_de_la_version_que_cambio_el_defecto():
    """2.1 cambio el controlador por defecto de postgresql://.

    La URL ya nombra el controlador, asi que ese cambio concreto ya no
    puede tumbar nada. El tope sigue puesto por lo demas: subir de version
    mayor es una decision que se prueba, no algo que la siguiente
    compilacion decida sola mientras las pruebas corren con otra.
    """
    requisitos = (RAIZ / "requirements.txt").read_text(encoding="utf-8")
    linea = next(l for l in requisitos.splitlines()
                 if l.strip().lower().startswith("sqlalchemy"))
    assert "<2.1" in linea.replace(" ", ""), \
        f"SQLAlchemy sin tope por debajo de 2.1: {linea.strip()}"


def test_la_version_instalada_cae_dentro_del_rango_declarado():
    """Lo que prueba esta suite tiene que ser lo que se despliega."""
    import sqlalchemy
    mayor, menor = (int(x) for x in sqlalchemy.__version__.split(".")[:2])
    assert (mayor, menor) < (2, 1), (
        f"Las pruebas corren con SQLAlchemy {sqlalchemy.__version__}, por encima "
        "del tope de requirements.txt: estarias probando otro programa."
    )


def test_nadie_construye_un_motor_con_una_url_sin_normalizar():
    """create_engine debe recibir siempre una URL que paso por el ayudante."""
    culpables = []
    for ruta in list((RAIZ / "app").rglob("*.py")) + [RAIZ / "alembic" / "env.py"]:
        # El unico sitio donde ese literal debe aparecer es el que lo traduce.
        if ruta.name == "url_bd.py":
            continue
        for n, linea in enumerate(ruta.read_text(encoding="utf-8").splitlines(), 1):
            if linea.strip().startswith("#"):
                continue
            # Una URL de postgres escrita a mano, sin controlador
            if re.search(r'["\']postgres(ql)?://', linea):
                culpables.append(f"{ruta.relative_to(RAIZ)}:{n}: {linea.strip()[:80]}")
    assert not culpables, (
        "URL de postgres sin controlador en el codigo; usa url_bd.normalizar():"
        + chr(10) + chr(10).join(culpables)
    )
