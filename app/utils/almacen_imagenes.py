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
from io import BytesIO

from PIL import Image, UnidentifiedImageError
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import Archivo
from app.utils import supabase_storage

logger = logging.getLogger(__name__)

MIMES = {".jpg": "image/jpeg", ".png": "image/png", ".webp": "image/webp"}

# Lado mayor de la miniatura. La foto guardada son 1280 px y unas decenas de
# kilobytes; una lista de ochenta clientes serian varios megabytes por cada
# vez que el cobrador abre su ruta, justo donde peor va la señal. A 160 px la
# misma imagen baja a dos o tres kilobytes y sigue nitida en el circulito de
# la lista incluso en una pantalla de alta densidad.
LADO_MINIATURA = 160


def _ruta_en_bucket(empresa_id: int, tipo: str, nombre: str) -> str:
    """Un prefijo por empresa y por tipo: ordena el bucket y hace evidente
    de quien es cada objeto al mirarlo desde el panel de Supabase."""
    return f"empresa_{empresa_id}/{tipo}/{nombre}"


def guardar_imagen(db: Session, empresa_id: int, datos: bytes, ext: str,
                   tipo: str = "cliente", prefijo: str = "",
                   nombre: str = "") -> str:
    """Guarda la imagen y devuelve el nombre con el que se servira.

    `nombre` solo lo usa la miniatura, que necesita un nombre deducible del
    de la foto original para poder buscarla sin guardar una referencia
    aparte. Lo demas sigue recibiendo un nombre irrepetible.
    """
    if not nombre:
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


def nombre_miniatura(nombre: str) -> str:
    """El nombre de la miniatura de esta foto, deducible del original.

    Deducible y no guardado en ninguna columna a proposito: asi las fotos que
    ya estaban subidas -- miles -- tienen miniatura sin necesidad de un script
    que recorra la tabla y sin añadir una columna que habria que mantener en
    sincronia con la foto.
    """
    if not nombre:
        return ""
    raiz = nombre.rsplit(".", 1)[0]
    return f"mini_{raiz}.jpg"


def leer_miniatura(db: Session, empresa_id: int, nombre: str) -> tuple[bytes, str] | None:
    """La miniatura de esa foto; la genera la primera vez que se pide.

    Generar al vuelo en vez de al subir cubre con un solo camino las fotos
    nuevas y las que ya estaban. Se guarda el resultado, asi que el trabajo
    se hace una vez por foto y no una vez por visita.
    """
    mini = nombre_miniatura(nombre)
    if not mini:
        return None

    ya = leer_imagen(db, empresa_id, mini)
    if ya:
        return ya

    original = leer_imagen(db, empresa_id, nombre)
    if not original:
        return None

    try:
        with Image.open(BytesIO(original[0])) as img:
            img.thumbnail((LADO_MINIATURA, LADO_MINIATURA), Image.LANCZOS)
            if img.mode not in ("RGB", "L"):
                img = img.convert("RGB")
            salida = BytesIO()
            img.save(salida, format="JPEG", quality=72, optimize=True)
    except (UnidentifiedImageError, OSError, ValueError) as e:
        # La foto esta pero no se puede reducir. Devolverla entera es mejor
        # que dejar el hueco vacio en la lista.
        logger.warning("No se pudo generar la miniatura de %s: %s", nombre, e)
        return original

    datos = salida.getvalue()

    # El guardado va en un punto de retorno propio: si dos peticiones piden la
    # misma miniatura a la vez, la segunda choca con el nombre unico, y eso no
    # puede tumbar una peticion cuyo trabajo -- la imagen -- ya esta hecho.
    try:
        with db.begin_nested():
            guardar_imagen(db, empresa_id, datos, ".jpg",
                           tipo="miniatura", nombre=mini)
        db.commit()
    except IntegrityError:
        logger.info("La miniatura %s ya la genero otra peticion", mini)
    except Exception as e:
        logger.warning("No se pudo guardar la miniatura %s: %s", mini, e)

    return (datos, "image/jpeg")


def borrar_imagen(db: Session, empresa_id: int, nombre: str) -> int:
    """Retira una imagen que ya no referencia nadie, y su miniatura.

    La miniatura se borra aqui porque su nombre sale del de la foto: si la
    foto se reemplaza, la nueva tiene otro nombre y la miniatura vieja se
    quedaria en el bucket sin que nada la pida nunca mas.
    """
    if not nombre:
        return 0
    if not nombre.startswith("mini_"):
        _borrar_fila(db, empresa_id, nombre_miniatura(nombre))
    return _borrar_fila(db, empresa_id, nombre)


def _borrar_fila(db: Session, empresa_id: int, nombre: str) -> int:
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
