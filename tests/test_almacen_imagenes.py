"""Las fotos tienen que sobrevivir a un despliegue.

Se guardaban con write_bytes() dentro de uploads/, en el sistema de archivos
del contenedor. El proveedor lo recrea en cada publicacion, asi que la foto
que un cobrador tomaba el lunes desaparecia el martes: la fila del cliente
seguia apuntando a un archivo inexistente y el perfil mostraba el icono de
imagen rota. Estas pruebas fijan que las imagenes viven en la base de datos
y que ningun camino de subida vuelve a escribir en disco.
"""
import pathlib
import re
from io import BytesIO

import pytest
from PIL import Image
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Archivo, Base
from app.utils.almacen_imagenes import borrar_imagen, guardar_imagen, leer_imagen
from app.utils.validators import LADO_MAXIMO_IMAGEN, sanitizar_imagen_subida

RAIZ = pathlib.Path(__file__).resolve().parent.parent


@pytest.fixture()
def db():
    motor = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(motor)
    s = sessionmaker(bind=motor)()
    yield s
    s.close()


def _jpeg(ancho=800, alto=600) -> bytes:
    b = BytesIO()
    Image.new("RGB", (ancho, alto), (10, 120, 200)).save(b, "JPEG", quality=95)
    return b.getvalue()


def test_la_imagen_se_recupera_tal_cual_se_guardo(db):
    ext, datos = sanitizar_imagen_subida("foto.jpg", _jpeg())
    nombre = guardar_imagen(db, 1, datos, ext, "cliente", 42)
    db.commit()

    guardada = leer_imagen(db, 1, nombre)
    assert guardada is not None
    assert guardada.datos == datos
    assert guardada.mime == "image/jpeg"
    assert guardada.tamano == len(datos)


def test_una_empresa_no_puede_leer_la_foto_de_otra(db):
    ext, datos = sanitizar_imagen_subida("foto.jpg", _jpeg())
    nombre = guardar_imagen(db, 1, datos, ext)
    db.commit()

    assert leer_imagen(db, 2, nombre) is None, "el nombre es adivinable; filtra por empresa"
    assert leer_imagen(db, 1, nombre) is not None


def test_sustituir_la_foto_retira_la_anterior(db):
    ext, datos = sanitizar_imagen_subida("foto.jpg", _jpeg())
    vieja = guardar_imagen(db, 1, datos, ext)
    db.commit()
    nueva = guardar_imagen(db, 1, datos, ext)
    assert borrar_imagen(db, 1, vieja) == 1
    db.commit()

    assert leer_imagen(db, 1, vieja) is None
    assert leer_imagen(db, 1, nueva) is not None
    assert db.query(Archivo).count() == 1


def test_borrar_no_alcanza_a_otra_empresa(db):
    ext, datos = sanitizar_imagen_subida("foto.jpg", _jpeg())
    nombre = guardar_imagen(db, 1, datos, ext)
    db.commit()
    assert borrar_imagen(db, 2, nombre) == 0
    assert leer_imagen(db, 1, nombre) is not None


def test_una_foto_de_movil_se_reduce_antes_de_guardarse():
    """12 megapixeles por cliente harian inmanejable la copia de seguridad."""
    ext, datos = sanitizar_imagen_subida("foto.jpg", _jpeg(4000, 3000))
    with Image.open(BytesIO(datos)) as img:
        assert max(img.size) == LADO_MAXIMO_IMAGEN
        assert img.size == (1280, 960), "debe conservar la proporcion"
    assert len(datos) < 500 * 1024


def test_una_imagen_pequena_no_se_agranda():
    ext, datos = sanitizar_imagen_subida("foto.jpg", _jpeg(300, 200))
    with Image.open(BytesIO(datos)) as img:
        assert img.size == (300, 200)


def test_ninguna_subida_escribe_en_el_disco_del_contenedor():
    """write_bytes sobre uploads/ es exactamente lo que se perdia."""
    culpables = []
    for ruta in (RAIZ / "app").rglob("*.py"):
        for n, linea in enumerate(ruta.read_text(encoding="utf-8").splitlines(), 1):
            if re.search(r"(UPLOAD_DIR|FOTO_DIR|LOGO_DIR)\s*/[^/]*\)?\s*\.write_bytes", linea) \
               or re.search(r"\.write_bytes\(contenido\)", linea):
                culpables.append(f"{ruta.relative_to(RAIZ)}:{n}: {linea.strip()[:80]}")
    assert not culpables, (
        "Guarda la imagen con guardar_imagen(); el disco se borra en cada despliegue:"
        + chr(10) + "  " + (chr(10) + "  ").join(culpables)
    )
