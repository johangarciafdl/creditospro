"""Cliente minimo de Supabase Storage para el bucket privado de imagenes.

Solo hacen falta tres operaciones -- subir, descargar y borrar -- asi que se
hablan directamente con la API REST en vez de anadir el SDK entero como
dependencia.

El bucket es privado y no tiene ninguna politica sobre storage.objects, de
modo que unicamente la clave de servicio (que salta RLS) puede tocarlo. Esa
clave vive en el servidor y nunca sale hacia el navegador: las imagenes se
sirven por un endpoint propio de la aplicacion, que antes comprueba la
empresa del usuario y su acceso a la zona, igual que cuando los bytes
estaban en la base de datos. Por eso no se usan URL publicas ni firmadas --
una URL firmada, una vez emitida, vale para cualquiera que la tenga y no
sabe nada de zonas ni de empresas.

Si SUPABASE_URL o SUPABASE_SERVICE_KEY no estan configuradas, `disponible()`
devuelve False y el almacen cae a la columna `datos` de la tabla archivos.
Eso mantiene funcionando las pruebas y el desarrollo local sin credenciales.
"""
from __future__ import annotations

import logging
import os

import httpx

logger = logging.getLogger(__name__)

SUPABASE_URL = (os.getenv("SUPABASE_URL") or "").rstrip("/")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY") or ""
BUCKET = os.getenv("SUPABASE_BUCKET_IMAGENES", "imagenes")

# Storage esta en la misma region que la base de datos; con la aplicacion ya
# desplegada al lado, estos tiempos son holgados.
TIMEOUT_SUBIDA = 30.0
TIMEOUT_LECTURA = 15.0


class ErrorStorage(RuntimeError):
    """Storage respondio algo que impide continuar con la operacion."""


def disponible() -> bool:
    return bool(SUPABASE_URL and SUPABASE_SERVICE_KEY)


def _cabeceras(extra: dict | None = None) -> dict:
    cab = {
        "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
        "apikey": SUPABASE_SERVICE_KEY,
    }
    if extra:
        cab.update(extra)
    return cab


def _url(ruta: str) -> str:
    return f"{SUPABASE_URL}/storage/v1/object/{BUCKET}/{ruta}"


def subir(ruta: str, datos: bytes, mime: str) -> None:
    """Sube los bytes al bucket. Lanza ErrorStorage si no se pudo."""
    if not disponible():
        raise ErrorStorage("Supabase Storage no esta configurado")
    try:
        r = httpx.post(
            _url(ruta),
            content=datos,
            headers=_cabeceras({
                "Content-Type": mime,
                # Sobrescribir si el nombre ya existiera: los nombres llevan
                # un uuid, asi que en la practica no ocurre, pero un
                # reintento tras un fallo de red no debe romperse por esto.
                "x-upsert": "true",
                "Cache-Control": "max-age=31536000",
            }),
            timeout=TIMEOUT_SUBIDA,
        )
    except httpx.HTTPError as e:
        raise ErrorStorage(f"No se pudo contactar con Storage: {e}") from e
    if r.status_code >= 400:
        raise ErrorStorage(f"Storage respondio {r.status_code}: {r.text[:200]}")


def descargar(ruta: str) -> bytes | None:
    """Devuelve los bytes, o None si no estan."""
    if not disponible():
        return None
    try:
        r = httpx.get(_url(ruta), headers=_cabeceras(), timeout=TIMEOUT_LECTURA)
    except httpx.HTTPError as e:
        logger.warning("Storage no respondio al pedir %s: %s", ruta, e)
        return None
    if r.status_code == 200:
        return r.content
    if r.status_code != 404:
        logger.warning("Storage devolvio %s al pedir %s", r.status_code, ruta)
    return None


def borrar(ruta: str) -> bool:
    """Retira el objeto. Un fallo aqui no debe tumbar la operacion que lo pidio."""
    if not disponible():
        return False
    try:
        r = httpx.delete(_url(ruta), headers=_cabeceras(), timeout=TIMEOUT_LECTURA)
    except httpx.HTTPError as e:
        logger.warning("Storage no respondio al borrar %s: %s", ruta, e)
        return False
    if r.status_code >= 400 and r.status_code != 404:
        logger.warning("Storage devolvio %s al borrar %s", r.status_code, ruta)
        return False
    return True
