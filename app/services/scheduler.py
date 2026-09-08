"""Scheduler v2.2 — multi-tenant, corregido asyncio + logging centralizado"""
import asyncio
import threading
import datetime
import time
import logging

from app.database import SessionLocal, Cuota, Empresa, IS_SQLITE
from sqlalchemy import and_, text

logger = logging.getLogger(__name__)

# Claves arbitrarias para pg_try_advisory_lock: evitan que dos workers/replicas
# corran el mismo job a la vez si algun dia se sube --workers por encima de 1.
# No tienen efecto en SQLite (dev), donde solo corre un proceso de todos modos.
_LOCK_KEY_ESTADOS = 987001
_LOCK_KEY_RECORDATORIOS = 987002


def _con_advisory_lock(db, key: int, nombre: str, fn) -> bool:
    """Ejecuta fn() solo si se obtiene el lock; si no, otro worker ya lo tiene.
    Devuelve True si se ejecuto, False si se salto por lock ocupado."""
    if IS_SQLITE:
        fn()
        return True
    got = db.execute(text("SELECT pg_try_advisory_lock(:k)"), {"k": key}).scalar()
    if not got:
        logger.debug(f"Scheduler: {nombre} ya lo esta corriendo otro worker, se salta")
        return False
    try:
        fn()
        return True
    finally:
        db.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": key})


def actualizar_estados_cuotas():
    """Tarea síncrona: marca cuotas vencidas."""
    db = SessionLocal()

    def _run():
        hoy = datetime.date.today()
        cuotas = db.query(Cuota).filter(
            and_(Cuota.estado == "Pendiente", Cuota.fecha_vencimiento < hoy)
        ).all()
        for c in cuotas:
            c.estado = "Vencida"
        if cuotas:
            db.commit()
            logger.info(f"Scheduler: {len(cuotas)} cuotas vencidas actualizadas")
        else:
            logger.debug("Scheduler: 0 cuotas vencidas hoy")

    try:
        _con_advisory_lock(db, _LOCK_KEY_ESTADOS, "actualizar_estados_cuotas", _run)
    except Exception as e:
        logger.error(f"Scheduler error estados: {e}", exc_info=True)
    finally:
        db.close()


async def _recordatorios_async():
    """Envía recordatorios WhatsApp de forma asíncrona."""
    from app.services.whatsapp_service import ejecutar_recordatorios
    db = SessionLocal()
    if not IS_SQLITE:
        got = db.execute(text("SELECT pg_try_advisory_lock(:k)"), {"k": _LOCK_KEY_RECORDATORIOS}).scalar()
        if not got:
            logger.debug("Scheduler: recordatorios ya los esta enviando otro worker, se salta")
            db.close()
            return
    try:
        empresas = db.query(Empresa).filter(Empresa.activa == True).all()
        for empresa in empresas:
            resultado = await ejecutar_recordatorios(db, empresa.id)
            logger.info(f"WP empresa {empresa.id}: {resultado}")
    except Exception as e:
        logger.error(f"Scheduler WP error: {e}", exc_info=True)
    finally:
        if not IS_SQLITE:
            db.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": _LOCK_KEY_RECORDATORIOS})
        db.close()


def _ejecutar_recordatorios_sync():
    """Wrapper síncrono para ejecutar async recordatorios."""
    asyncio.run(_recordatorios_async())


# ── Healthcheck del scheduler ────────────────────────────────────────────────
# Expuesto para /health: el endpoint puede detectar si el hilo sigue vivo.
_scheduler_heartbeat: float = 0.0
_scheduler_alive: bool = False
_scheduler_lock = threading.Lock()


def get_scheduler_status() -> dict:
    """Devuelve estado del scheduler para /health."""
    with _scheduler_lock:
        if not _scheduler_alive:
            return {"running": False, "last_heartbeat": None, "stale": True}
        age = time.time() - _scheduler_heartbeat
        return {
            "running": True,
            "last_heartbeat": _scheduler_heartbeat,
            "seconds_since_heartbeat": round(age, 1),
            # Si el latido tiene >5min de antiguedad, el hilo esta colgado
            "stale": age > 300,
        }


def loop_scheduler():
    """Bucle principal del scheduler. Corre en hilo separado."""
    global _scheduler_heartbeat, _scheduler_alive
    ultimo_estado = None
    ultimo_wp = None
    logger.info("Scheduler iniciado correctamente")

    with _scheduler_lock:
        _scheduler_alive = True
        _scheduler_heartbeat = time.time()

    while True:
        ahora = datetime.datetime.now()

        with _scheduler_lock:
            _scheduler_heartbeat = time.time()

        # Cada hora: actualizar estados de cuotas
        if ultimo_estado is None or (ahora - ultimo_estado).total_seconds() >= 3600:
            actualizar_estados_cuotas()
            ultimo_estado = ahora

        # Cada día a las 8:00 AM: enviar recordatorios WhatsApp
        if (ahora.hour == 8 and ahora.minute < 5 and
                (ultimo_wp is None or ultimo_wp.date() < ahora.date())):
            try:
                _ejecutar_recordatorios_sync()
            except Exception as e:
                logger.error(f"Error ejecutando recordatorios: {e}", exc_info=True)
            ultimo_wp = ahora

        time.sleep(60)


def iniciar_scheduler():
    t = threading.Thread(target=loop_scheduler, daemon=True, name="Scheduler")
    t.start()
    return t
