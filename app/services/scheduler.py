"""Scheduler v2.2 — multi-tenant, corregido asyncio + logging centralizado"""
import asyncio
import threading
import datetime
import time
import logging

from app.database import (SessionLocal, Cuota, Empresa, IS_SQLITE, ahora_local,
                          hoy_local, inicio_dia_negocio)
from sqlalchemy import and_, text

logger = logging.getLogger(__name__)

# Claves arbitrarias para pg_try_advisory_lock: evitan que dos workers/replicas
# corran el mismo job a la vez si algun dia se sube --workers por encima de 1.
# No tienen efecto en SQLite (dev), donde solo corre un proceso de todos modos.
_LOCK_KEY_ESTADOS = 987001
_LOCK_KEY_RECORDATORIOS = 987002
_LOCK_KEY_RESPALDO = 987003


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
        hoy = hoy_local()
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


ACCION_RECORDATORIOS = "recordatorios_wp_enviados"
ACCION_RESPALDO = "respaldo_diario"


def _ya_se_respaldo_hoy(db) -> bool:
    """La marca es duradera y compartida, no una variable de este proceso.

    Un lock impide que dos procesos respalden a la vez, no que respalden uno
    detras de otro: en cuanto el primero suelta el lock, el segundo entra
    dentro de la misma ventana y se genera la copia dos veces. Por eso hacen
    falta las dos cosas.
    """
    from app.database import AuditLog

    return db.query(AuditLog.id).filter(
        AuditLog.action == ACCION_RESPALDO,
        AuditLog.created_at >= inicio_dia_negocio(),
    ).first() is not None


def respaldo_diario():
    """Genera la copia de seguridad del dia, una sola vez entre todos."""
    from app.database import SessionLocal
    from app.database import AuditLog
    from app.services.respaldo import crear_respaldo

    db = SessionLocal()

    def _run():
        if _ya_se_respaldo_hoy(db):
            logger.debug("Respaldo: ya se hizo hoy")
            return
        try:
            resumen = crear_respaldo(db)
        except Exception as e:
            logger.error("Respaldo diario fallido: %s", e, exc_info=True)
            # No se marca como hecho: en la siguiente vuelta se reintenta.
            return
        db.add(AuditLog(
            action=ACCION_RESPALDO,
            category="scheduler",
            details=(f"{resumen['nombre']}: {resumen['tablas']} tablas, "
                     f"{resumen['filas']} filas, {resumen['bytes'] // 1024} KB"),
        ))
        db.commit()

    try:
        _con_advisory_lock(db, _LOCK_KEY_RESPALDO, "respaldo_diario", _run)
    except Exception as e:
        logger.error("Scheduler error respaldo: %s", e, exc_info=True)
    finally:
        db.close()


def _ya_se_enviaron_hoy(db) -> bool:
    """¿Quedo registrado hoy un envio de recordatorios?

    Se usa audit_log en vez de una tabla nueva: ya es el registro duradero
    y comun a todos los procesos de las acciones del sistema, y de paso el
    envio queda visible en el panel de monitoreo.
    """
    from app.database import AuditLog

    inicio = inicio_dia_negocio()
    return db.query(AuditLog.id).filter(
        AuditLog.action == ACCION_RECORDATORIOS,
        AuditLog.created_at >= inicio,
    ).first() is not None


def _marcar_enviados_hoy(db, num_empresas: int) -> None:
    from app.database import AuditLog

    try:
        db.add(AuditLog(
            action=ACCION_RECORDATORIOS,
            category="scheduler",
            details=f"Recordatorios enviados a {num_empresas} empresa(s)",
        ))
        db.commit()
    except Exception as e:
        db.rollback()
        logger.warning("No se pudo registrar el envio de recordatorios: %s", e)


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
        # El lock evita que dos workers envien A LA VEZ, pero no que envien
        # uno detras de otro: la ventana de disparo dura cinco minutos y
        # `ultimo_wp` es memoria de cada proceso, asi que el segundo worker
        # reintenta cuando el primero ya solto el lock y los clientes
        # reciben el recordatorio dos veces. La marca en la auditoria es
        # comun a todos los procesos y sobrevive a un reinicio.
        if _ya_se_enviaron_hoy(db):
            logger.info("Scheduler: los recordatorios de hoy ya se enviaron, se salta")
            return

        empresas = db.query(Empresa).filter(Empresa.activa == True).all()
        for empresa in empresas:
            resultado = await ejecutar_recordatorios(db, empresa.id)
            logger.info(f"WP empresa {empresa.id}: {resultado}")
        _marcar_enviados_hoy(db, len(empresas))
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
    ultimo_limpieza = None
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

        # Cada hora, con el mismo pulso: borrar las ventanas del rate limit
        # que ya nadie puede consultar. Sin esto la tabla crece una fila por
        # cada combinacion de ruta e IP que haya pasado alguna vez.
        if ultimo_limpieza is None or (ahora - ultimo_limpieza).total_seconds() >= 3600:
            try:
                from app.database import SessionLocal
                from app.utils.rate_limit import limpiar_ventanas_viejas

                db = SessionLocal()
                try:
                    borradas = limpiar_ventanas_viejas(db)
                    if borradas:
                        logger.info("Rate limit: %d ventanas antiguas borradas", borradas)
                finally:
                    db.close()
            except Exception as e:
                logger.warning("No se pudieron limpiar las ventanas del rate limit: %s", e)
            ultimo_limpieza = ahora

        # Cada dia de madrugada: copia de seguridad. A las 3 porque no hay
        # nadie cobrando y la base esta ociosa. La hora es la del negocio,
        # no la del contenedor, que corre en UTC.
        local = ahora_local()
        if local.hour == 3 and local.minute < 5:
            try:
                respaldo_diario()
            except Exception as e:
                logger.error(f"Error ejecutando el respaldo: {e}", exc_info=True)

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
