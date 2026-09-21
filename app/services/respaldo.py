"""Copia de seguridad diaria de toda la base, sin intervencion de nadie.

Habia un script de respaldo, pero habia que acordarse de ejecutarlo. Un
respaldo que depende de la memoria de una persona no es un respaldo: es una
intencion. Para un negocio de prestamos, perder la base es perder el
negocio, asi que esto corre solo.

Que se guarda: todas las tablas del modelo, en JSON comprimido con gzip. La
base entera ocupa unos 9 MB y comprime muy por debajo de eso, asi que cabe
de sobra en memoria y en el bucket.

Las tablas NO se escriben a mano. El script anterior llevaba una lista fija
y se habia quedado sin cinco de las tablas nuevas -- rutas_cobro, no_pagos,
archivos y las dos de estado compartido -- sin que nada lo avisara. Aqui se
recorren los modelos, de modo que una tabla nueva entra en el respaldo el
dia que se crea.

Limite honesto: la copia vive en el mismo proyecto de Supabase que la base.
Eso protege de lo que de verdad pasa a diario -- un borrado por error, un
cambio de datos mal hecho, un fallo que arrasa filas -- pero NO de perder la
cuenta entera de Supabase. Para eso hay que bajarse copias de vez en cuando,
y por eso existe el endpoint de descarga en el panel del dueno.
"""
from __future__ import annotations

import datetime
import gzip
import io
import json
import logging
from decimal import Decimal

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.database import Base, hoy_local
from app.utils import supabase_storage

logger = logging.getLogger(__name__)

# Cuantos dias de copias se conservan. Con ~1 MB por copia, dos semanas
# ocupan nada y cubren de sobra el tiempo que se tarda en notar un error.
DIAS_A_CONSERVAR = 14

PREFIJO = "respaldo-"


def _serializable(valor):
    """Los tipos que JSON no sabe escribir por si solo."""
    if isinstance(valor, (datetime.datetime, datetime.date, datetime.time)):
        return valor.isoformat()
    if isinstance(valor, Decimal):
        # Como texto y no como float: un float pierde centavos.
        return str(valor)
    if isinstance(valor, (bytes, bytearray, memoryview)):
        # Las imagenes ya viven en Storage; si quedara algun blob antiguo se
        # anota su tamano en vez de inflar el respaldo con el contenido.
        return f"<{len(bytes(valor))} bytes omitidos>"
    return str(valor)


def _nombre_tablas() -> list[str]:
    """Todas las tablas del modelo, en orden de dependencia."""
    return [t.name for t in Base.metadata.sorted_tables]


def volcar(db: Session) -> dict:
    """Lee todas las tablas y devuelve el contenido del respaldo."""
    contenido: dict = {
        "generado": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "fecha_negocio": hoy_local().isoformat(),
        "tablas": {},
    }
    for tabla in _nombre_tablas():
        try:
            filas = db.execute(text(f'SELECT * FROM "{tabla}"')).mappings().all()
        except Exception as e:
            # Una tabla que aun no existe en esta base no debe abortar la
            # copia de las demas.
            logger.warning("Respaldo: no se pudo leer %s (%s)", tabla, e)
            contenido["tablas"][tabla] = {"error": str(e)[:200], "filas": []}
            continue
        contenido["tablas"][tabla] = {
            "filas": [dict(f) for f in filas],
            "total": len(filas),
        }
    return contenido


def comprimir(contenido: dict) -> bytes:
    crudo = json.dumps(contenido, default=_serializable, ensure_ascii=False).encode("utf-8")
    buffer = io.BytesIO()
    with gzip.GzipFile(fileobj=buffer, mode="wb", compresslevel=6) as gz:
        gz.write(crudo)
    return buffer.getvalue()


def nombre_del_dia(momento: datetime.datetime | None = None) -> str:
    m = momento or datetime.datetime.now(datetime.timezone.utc)
    return f"{PREFIJO}{m.strftime('%Y-%m-%d_%H%M')}.json.gz"


def _objetos(limite: int = 200) -> list[dict]:
    """Los respaldos del bucket.

    Se listan todos y se filtran por nombre aqui: el `prefix` de Supabase
    filtra por carpeta, no por principio del nombre, y pasarle "respaldo-"
    devolvia siempre una lista vacia -- con lo que la purga nunca borraba
    nada y las copias se habrian acumulado sin limite.
    """
    return [o for o in supabase_storage.listar(
        bucket=supabase_storage.BUCKET_RESPALDOS, limite=limite)
        if str(o.get("name", "")).startswith(PREFIJO)]


def purgar_antiguos(dias: int = DIAS_A_CONSERVAR) -> int:
    """Retira las copias mas viejas que el periodo de conservacion."""
    limite = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=dias)
    borradas = 0
    for objeto in _objetos(limite=500):
        creado = objeto.get("created_at") or ""
        try:
            cuando = datetime.datetime.fromisoformat(creado.replace("Z", "+00:00"))
        except ValueError:
            continue
        if cuando < limite:
            if supabase_storage.borrar(objeto["name"], bucket=supabase_storage.BUCKET_RESPALDOS):
                borradas += 1
    return borradas


def crear_respaldo(db: Session) -> dict:
    """Genera la copia, la sube y retira las viejas. Devuelve un resumen."""
    if not supabase_storage.disponible():
        raise RuntimeError(
            "No hay donde guardar el respaldo: faltan SUPABASE_URL y "
            "SUPABASE_SERVICE_KEY. Sin eso la copia se perderia con el "
            "contenedor, que es lo mismo que no tenerla."
        )

    contenido = volcar(db)
    datos = comprimir(contenido)
    nombre = nombre_del_dia()
    supabase_storage.subir(nombre, datos, "application/gzip",
                           bucket=supabase_storage.BUCKET_RESPALDOS)

    total_filas = sum(t.get("total", 0) for t in contenido["tablas"].values())
    borradas = purgar_antiguos()
    resumen = {
        "nombre": nombre,
        "tablas": len(contenido["tablas"]),
        "filas": total_filas,
        "bytes": len(datos),
        "antiguas_borradas": borradas,
    }
    logger.info("Respaldo %s: %d tablas, %d filas, %d KB (%d antiguas borradas)",
                nombre, resumen["tablas"], total_filas, len(datos) // 1024, borradas)
    return resumen


def listar_respaldos(limite: int = 30) -> list[dict]:
    """Las copias disponibles, de la mas reciente a la mas antigua."""
    objetos = _objetos(limite=limite)
    salida = []
    for o in objetos:
        meta = o.get("metadata") or {}
        salida.append({
            "nombre": o["name"],
            "creado": o.get("created_at"),
            "bytes": meta.get("size"),
        })
    return salida


def descargar_respaldo(nombre: str) -> bytes | None:
    """Baja una copia concreta. El nombre se valida para no salir del bucket."""
    if not nombre.startswith(PREFIJO) or "/" in nombre or ".." in nombre:
        return None
    return supabase_storage.descargar(nombre, bucket=supabase_storage.BUCKET_RESPALDOS)
