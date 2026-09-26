"""Normaliza la URL de la base de datos, nombrando el controlador.

Una URL que empieza por `postgresql://` no dice con que biblioteca
conectarse: deja que SQLAlchemy elija por defecto. Eso funciono durante
anos y luego dejo de funcionar sin que nadie tocara el codigo, porque
SQLAlchemy 2.1 cambio ese valor por defecto de psycopg2 a psycopg 3. El
proyecto declara psycopg2, asi que la compilacion nueva arranco pidiendo
un modulo que no estaba instalado y el contenedor no llego a levantar:

    ModuleNotFoundError: No module named 'psycopg'

Lo peor no fue la caida sino que las pruebas seguian en verde: el entorno
de desarrollo tenia SQLAlchemy 2.0, donde el valor por defecto era el
otro. "Probado" y "desplegado" eran dos programas distintos.

Escribir el controlador en la URL quita la decision de manos de un valor
por defecto que puede cambiar en cualquier version.
"""
from __future__ import annotations

# El que declara requirements.txt. Si algun dia se migra a psycopg 3, se
# cambia aqui y en requirements a la vez, que es justo lo que no ocurrio
# cuando la eleccion vivia en un valor por defecto.
CONTROLADOR_POSTGRES = "psycopg2"


def normalizar(url: str) -> str:
    """Devuelve la URL lista para create_engine.

    - `postgres://` es la forma antigua que aun usan algunos proveedores;
      SQLAlchemy no la reconoce.
    - `postgresql://` sin controlador se completa con el que el proyecto
      tiene instalado.
    - Una URL que ya nombra su controlador se deja como esta, para poder
      forzar otro sin tocar codigo.
    """
    if not url:
        return url
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)
    if url.startswith("postgresql://"):
        url = url.replace("postgresql://", f"postgresql+{CONTROLADOR_POSTGRES}://", 1)
    return url
