"""Guarda y recupera las imagenes subidas.

Historia corta de donde han vivido y por que:

1. En `uploads/`, el disco del contenedor. El proveedor lo recrea en cada
   despliegue, asi que una foto tomada por un cobrador duraba hasta la
   siguiente publicacion: la fila del cliente seguia apuntando a un archivo
   que ya no existia y el perfil mostraba el icono de imagen rota.
2. En la propia base de datos, como bytes. Sobrevivia a los despliegues,
   pero hace crecer cada copia de seguridad con contenido que no es
   relacional y que nunca se consulta por SQL.
3. En Supabase Storage, que es su sitio: almacenamiento de objetos, en la
   misma region que la base de datos, con su propio limite de tamano y de
   tipos por bucket.

La tabla `archivos` se queda como indice: guarda de que empresa es cada
imagen, que es lo que permite negarsela a otra antes de ir a buscarla. La
columna `almacen` dice donde estan los bytes de esa fila en concreto, para
que las imagenes subidas antes del cambio se sigan leyendo y para que la
aplicacion funcione sin credenciales de Storage -- pruebas y desarrollo
local -- guardandolos en la base como hasta ahora.

Las imagenes llegan ya validadas y reducidas por `sanitizar_imagen_subida`
(lado mayor 1280 px), asi que ocupan unas decenas de kilobytes.
"""
from __future__ import annotations

import logging
import uuid

from sqlalchemy.orm import Session

from app.database import Archivo
from app.utils import supabase_storage

logger = logging.getLogger(__name__)

MIMES = {".jpg": "image/jpeg", ".png": "image/png", ".webp": "image/webp"}


def _ruta_en_bucket(empresa_id: int, tipo: str, nombre: str) -> str:
    """Un prefijo por empresa y por tipo: ordena el bucket y hace evidente
    de quien es cada objeto al mirarlo desde el panel de Supabase."""
    return f"empresa_{empresa_id}/{tipo}/{nombre}"


def guardar_imagen(db: Session, empresa_id: int, datos: bytes, ext: str,
                   tipo: str = "cliente", prefijo: str = "") -> str:
    """Guarda la imagen y devuelve el nombre con el que se servira."""
    partes = [str(empresa_id)]
    if prefijo:
        partes.append(str(prefijo))
    partes.append(uuid.uuid4().hex)
    nombre = "_".join(partes) + ext
    mime = MIMES.get(ext, "application/octet-stream")

    almacen, ruta, cuerpo = "bd", None, datos
    if supabase_storage.disponible():
        ruta = _ruta_en_bucket(empresa_id, tipo, nombre)
        try:
            supabase_storage.subir(ruta, datos, mime)
            almacen, cuerpo = "supabase", None
        except supabase_storage.ErrorStorage as e:
            # Perder la foto es peor que guardarla en el sitio menos elegante:
            # se queda en la base y la aplicacion sigue adelante.
            logger.error("Storage fallo al subir %s, se guarda en la base: %s", nombre, e)
            ruta = None

    db.add(Archivo(
        empresa_id=empresa_id,
        nombre=nombre,
        tipo=tipo,
        mime=mime,
        almacen=almacen,
        ruta=ruta,
        datos=cuerpo,
        tamano=len(datos),
    ))
    return nombre


def leer_imagen(db: Session, empresa_id: int, nombre: str) -> tuple[bytes, str] | None:
    """Devuelve (bytes, mime) de esta empresa, o None si no es suya o falta.

    El filtro por empresa_id no es decorativo: el nombre del objeto es
    adivinable para quien conozca el formato, y esta consulta es lo unico
    que hay entre una empresa y las fotos de otra.
    """
    fila = (
        db.query(Archivo)
        .filter(Archivo.nombre == nombre, Archivo.empresa_id == empresa_id)
        .first()
    )
    if not fila:
        return None
    if fila.almacen == "supabase" and fila.ruta:
        datos = supabase_storage.descargar(fila.ruta)
        if datos is None:
            logger.warning("La imagen %s consta en Storage pero no se pudo leer", nombre)
            return None
        return (datos, fila.mime)
    if fila.datos is None:
        return None
    return (bytes(fila.datos), fila.mime)


def borrar_imagen(db: Session, empresa_id: int, nombre: str) -> int:
    """Retira una imagen que ya no referencia nadie."""
    if not nombre:
        return 0
    fila = (
        db.query(Archivo)
        .filter(Archivo.nombre == nombre, Archivo.empresa_id == empresa_id)
        .first()
    )
    if not fila:
        return 0
    if fila.almacen == "supabase" and fila.ruta:
        # Si el borrado en Storage falla queda un objeto huerfano, molesto
        # pero inocuo; lo que no puede quedar es la fila apuntando a algo
        # que ya no se va a mostrar.
        supabase_storage.borrar(fila.ruta)
    db.delete(fila)
    return 1
