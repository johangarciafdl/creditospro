"""Guarda y recupera las imagenes subidas, en la base de datos.

Antes se escribian con `ruta.write_bytes(...)` dentro de `uploads/`, que vive
en el sistema de archivos del contenedor. El proveedor lo recrea en cada
despliegue, asi que una foto tomada por un cobrador duraba hasta la siguiente
publicacion: la fila del cliente seguia apuntando a un archivo que ya no
existia y el perfil mostraba el icono de imagen rota. Guardarlas en la base
de datos las hace sobrevivir a los despliegues y las incluye en las copias de
seguridad, que es donde el negocio espera encontrarlas.

Las imagenes llegan ya validadas y reducidas por `sanitizar_imagen_subida`
(lado mayor 1280 px), asi que ocupan unas decenas de kilobytes cada una.
"""
from __future__ import annotations

import uuid

from sqlalchemy.orm import Session

from app.database import Archivo

MIMES = {".jpg": "image/jpeg", ".png": "image/png", ".webp": "image/webp"}


def guardar_imagen(db: Session, empresa_id: int, datos: bytes, ext: str,
                   tipo: str = "cliente", prefijo: str = "") -> str:
    """Guarda la imagen y devuelve el nombre con el que se servira."""
    partes = [str(empresa_id)]
    if prefijo:
        partes.append(str(prefijo))
    partes.append(uuid.uuid4().hex)
    nombre = "_".join(partes) + ext
    db.add(Archivo(
        empresa_id=empresa_id,
        nombre=nombre,
        tipo=tipo,
        mime=MIMES.get(ext, "application/octet-stream"),
        datos=datos,
        tamano=len(datos),
    ))
    return nombre


def leer_imagen(db: Session, empresa_id: int, nombre: str) -> Archivo | None:
    """Devuelve la imagen de esta empresa, o None si no es suya o no existe."""
    return (
        db.query(Archivo)
        .filter(Archivo.nombre == nombre, Archivo.empresa_id == empresa_id)
        .first()
    )


def borrar_imagen(db: Session, empresa_id: int, nombre: str) -> int:
    """Retira una imagen que ya no referencia nadie."""
    if not nombre:
        return 0
    return (
        db.query(Archivo)
        .filter(Archivo.nombre == nombre, Archivo.empresa_id == empresa_id)
        .delete(synchronize_session=False)
    )
