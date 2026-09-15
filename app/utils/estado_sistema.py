"""Estado real del sistema: base de datos, version desplegada y capacidad.

Esto es lo que permite responder "¿va lenta la aplicacion o es mi
internet?" y "¿que version esta corriendo?" sin entrar a los logs del
proveedor.

La informacion se separa en dos niveles a proposito:

- `salud()` es lo minimo, publico, para el chequeo automatico del
  proveedor: dice si la aplicacion responde y si la base de datos contesta.
  No expone nada mas, porque esa ruta la puede llamar cualquiera.
- `detalle()` es lo que ve el dueño de la plataforma: conexiones en uso
  contra el maximo, tamaño de las tablas, migracion aplicada. Va detras de
  la autenticacion de superadmin.
"""
from __future__ import annotations

import logging
import os
import subprocess
import time
from functools import lru_cache

from sqlalchemy import text

logger = logging.getLogger(__name__)

VERSION = "2.1.0"


@lru_cache(maxsize=1)
def commit_desplegado() -> str:
    """Identifica el codigo que esta corriendo ahora mismo.

    Railway expone RAILWAY_GIT_COMMIT_SHA; en local se pregunta a git. Sin
    esto, ante un fallo en produccion no hay forma de saber si la version
    desplegada incluye o no un arreglo concreto.
    """
    for var in ("RAILWAY_GIT_COMMIT_SHA", "GIT_COMMIT", "SOURCE_VERSION"):
        valor = os.getenv(var, "").strip()
        if valor:
            return valor[:12]
    try:
        salida = subprocess.run(
            ["git", "rev-parse", "--short=12", "HEAD"],
            capture_output=True, text=True, timeout=3,
        )
        if salida.returncode == 0:
            return salida.stdout.strip()
    except Exception:
        pass
    return "desconocido"


def _revision_migracion(db) -> str:
    try:
        fila = db.execute(text("SELECT version_num FROM alembic_version")).first()
        return fila[0] if fila else "sin registrar"
    except Exception:
        return "no disponible"


def salud() -> dict:
    """Chequeo publico: ¿responde la aplicacion y contesta la base de datos?"""
    from app.database import SessionLocal

    arranque = time.perf_counter()
    bd_ok = False
    ida_y_vuelta = None
    try:
        db = SessionLocal()
        try:
            db.execute(text("SELECT 1"))
            bd_ok = True
            # Segunda consulta sobre la conexion YA abierta. La primera incluye
            # abrir la conexion y el pre-ping; esta mide solo el viaje de ida y
            # vuelta hasta la base de datos, que es lo que se multiplica por
            # cada consulta que hace una pantalla. Si este numero es de dos
            # cifras altas o mas, el servidor de aplicacion y la base de datos
            # estan en regiones distintas y eso pesa mas que cualquier consulta.
            t = time.perf_counter()
            db.execute(text("SELECT 1"))
            ida_y_vuelta = round((time.perf_counter() - t) * 1000, 1)
        finally:
            db.close()
    except Exception as exc:
        logger.warning("Chequeo de salud: la base de datos no responde (%s)", exc)

    return {
        "status": "healthy" if bd_ok else "degraded",
        "version": VERSION,
        "commit": commit_desplegado(),
        "base_de_datos": "ok" if bd_ok else "sin respuesta",
        "latencia_bd_ms": round((time.perf_counter() - arranque) * 1000),
        "ida_y_vuelta_bd_ms": ida_y_vuelta,
        "region": (os.getenv("RAILWAY_REPLICA_REGION") or os.getenv("RAILWAY_REGION")
                   or os.getenv("FLY_REGION") or "desconocida"),
    }


def detalle() -> dict:
    """Estado ampliado para el panel del dueño de la plataforma."""
    from app.database import IS_SQLITE, MAX_OVERFLOW, POOL_SIZE, SessionLocal

    datos = {
        "version": VERSION,
        "commit": commit_desplegado(),
        "workers": int(os.getenv("WEB_CONCURRENCY", "2")),
        "pool_por_motor": POOL_SIZE + MAX_OVERFLOW,
        "entorno": os.getenv("ENVIRONMENT", "production"),
        "rls_activo": os.getenv("ENABLE_DATABASE_RLS", "0") == "1",
        "rol_restringido": bool(os.getenv("DATABASE_URL_APP", "").strip()),
        "conexiones": None,
        "tablas": [],
        "migracion": "no disponible",
        "latencia_bd_ms": None,
        "error": None,
    }

    arranque = time.perf_counter()
    try:
        db = SessionLocal()
        try:
            db.execute(text("SELECT 1"))
            datos["latencia_bd_ms"] = round((time.perf_counter() - arranque) * 1000)
            datos["migracion"] = _revision_migracion(db)

            if not IS_SQLITE:
                fila = db.execute(text(
                    "SELECT (SELECT setting::int FROM pg_settings WHERE name='max_connections'),"
                    "       (SELECT count(*) FROM pg_stat_activity)"
                )).first()
                if fila:
                    maximo, en_uso = int(fila[0] or 0), int(fila[1] or 0)
                    # El techo teorico de la aplicacion: si se acerca al
                    # maximo del servidor, subir workers deja de ser seguro.
                    techo = datos["workers"] * 2 * datos["pool_por_motor"]
                    datos["conexiones"] = {
                        "maximo": maximo,
                        "en_uso": en_uso,
                        "techo_de_la_app": techo,
                        "holgado": techo <= maximo * 0.7,
                    }

                datos["tablas"] = [
                    {"nombre": f[0], "filas": int(f[1] or 0), "tamano": f[2]}
                    for f in db.execute(text(
                        """
                        SELECT c.relname,
                               c.reltuples,
                               pg_size_pretty(pg_total_relation_size(c.oid))
                        FROM pg_class c
                        JOIN pg_namespace n ON n.oid = c.relnamespace
                        WHERE n.nspname = 'public' AND c.relkind = 'r'
                        ORDER BY pg_total_relation_size(c.oid) DESC
                        LIMIT 12
                        """
                    )).all()
                ]
        finally:
            db.close()
    except Exception as exc:
        datos["error"] = str(exc)[:200]
        logger.warning("No se pudo leer el estado de la base de datos: %s", exc)

    return datos
