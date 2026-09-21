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
# Las copias de seguridad van a su propio bucket: distinta vida util,
# distinto tamano y conviene poder borrarlas sin rozar las fotos.
BUCKET_RESPALDOS = os.getenv("SUPABASE_BUCKET_RESPALDOS", "respaldos")

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


def _url(ruta: str, bucket: str | None = None) -> str:
    return f"{SUPABASE_URL}/storage/v1/object/{bucket or BUCKET}/{ruta}"


def subir(ruta: str, datos: bytes, mime: str, bucket: str | None = None) -> None:
    """Sube los bytes al bucket. Lanza ErrorStorage si no se pudo."""
    if not disponible():
        raise ErrorStorage("Supabase Storage no esta configurado")
    try:
        r = httpx.post(
            _url(ruta, bucket),
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


def _es_no_encontrado(r: httpx.Response) -> bool:
    """Storage responde 400 -- no 404 -- cuando el objeto no existe.

    El codigo real viaja en el cuerpo: {"statusCode":"404","code":"NoSuchKey"}.
    Sin mirarlo, cada imagen que falta se registraba como incidencia y el
    registro se llenaba de avisos que no lo eran, escondiendo los de verdad.
    """
    if r.status_code == 404:
        return True
    if r.status_code != 400:
        return False
    try:
        cuerpo = r.json()
    except ValueError:
        return False
    return str(cuerpo.get("statusCode")) == "404"


def descargar(ruta: str, bucket: str | None = None) -> bytes | None:
    """Devuelve los bytes, o None si no estan."""
    if not disponible():
        return None
    try:
        r = httpx.get(_url(ruta, bucket), headers=_cabeceras(), timeout=TIMEOUT_LECTURA)
    except httpx.HTTPError as e:
        logger.warning("Storage no respondio al pedir %s: %s", ruta, e)
        return None
    if r.status_code == 200:
        return r.content
    if not _es_no_encontrado(r):
        logger.warning("Storage devolvio %s al pedir %s: %s",
                       r.status_code, ruta, r.text[:200])
    return None


def borrar(ruta: str, bucket: str | None = None) -> bool:
    """Retira el objeto. Un fallo aqui no debe tumbar la operacion que lo pidio."""
    if not disponible():
        return False
    try:
        r = httpx.delete(_url(ruta, bucket), headers=_cabeceras(), timeout=TIMEOUT_LECTURA)
    except httpx.HTTPError as e:
        logger.warning("Storage no respondio al borrar %s: %s", ruta, e)
        return False
    if r.status_code >= 400 and not _es_no_encontrado(r):
        logger.warning("Storage devolvio %s al borrar %s: %s",
                       r.status_code, ruta, r.text[:200])
        return False
    return True


def listar(carpeta: str = "", bucket: str | None = None, limite: int = 200) -> list[dict]:
    """Objetos del bucket, del mas reciente al mas antiguo.

    Ojo con `carpeta`: el parametro `prefix` de Supabase filtra por ruta de
    carpeta, no por principio del nombre del archivo. Pasarle "respaldo-"
    devuelve una lista vacia porque busca una carpeta que se llame asi. Para
    quedarse con unos nombres concretos hay que filtrar despues.
    """
    if not disponible():
        return []
    destino = bucket or BUCKET
    try:
        r = httpx.post(
            f"{SUPABASE_URL}/storage/v1/object/list/{destino}",
            headers=_cabeceras({"Content-Type": "application/json"}),
            json={"prefix": carpeta, "limit": limite,
                  "sortBy": {"column": "created_at", "order": "desc"}},
            timeout=TIMEOUT_LECTURA,
        )
    except httpx.HTTPError as e:
        logger.warning("Storage no respondio al listar %s: %s", destino, e)
        return []
    if r.status_code >= 400:
        logger.warning("Storage devolvio %s al listar %s: %s",
                       r.status_code, destino, r.text[:200])
        return []
    try:
        return [o for o in r.json() if o.get("name")]
    except ValueError:
        return []
