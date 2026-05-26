<<<<<<< HEAD
"""Scheduler v2.2 — multi-tenant, corregido asyncio + logging centralizado"""
import asyncio
import threading
import datetime
import time
import logging

from app.database import SessionLocal, Cuota, Empresa
from sqlalchemy import and_

logger = logging.getLogger(__name__)


def actualizar_estados_cuotas():
    """Tarea síncrona: marca cuotas vencidas."""
=======
"""Scheduler v2.1 - multi-tenant, fixed asyncio loop conflict"""
import asyncio, threading, datetime, time
from app.database import SessionLocal, Cuota, Empresa
from sqlalchemy import and_


def actualizar_estados_cuotas():
>>>>>>> 7761f488b2aa6200974f069ea5072699c6dbd1e5
    db = SessionLocal()
    try:
        hoy = datetime.date.today()
        cuotas = db.query(Cuota).filter(
            and_(Cuota.estado == "Pendiente", Cuota.fecha_vencimiento < hoy)
        ).all()
        for c in cuotas:
            c.estado = "Vencida"
        if cuotas:
            db.commit()
<<<<<<< HEAD
            logger.info(f"Scheduler: {len(cuotas)} cuotas vencidas actualizadas")
        else:
            logger.debug("Scheduler: 0 cuotas vencidas hoy")
    except Exception as e:
        logger.error(f"Scheduler error estados: {e}", exc_info=True)
=======
            print(f"Scheduler: {len(cuotas)} cuotas vencidas actualizadas")
    except Exception as e:
        print(f"Scheduler error estados: {e}")
>>>>>>> 7761f488b2aa6200974f069ea5072699c6dbd1e5
    finally:
        db.close()


async def _recordatorios_async():
<<<<<<< HEAD
    """Envía recordatorios WhatsApp de forma asíncrona."""
=======
>>>>>>> 7761f488b2aa6200974f069ea5072699c6dbd1e5
    from app.services.whatsapp_service import ejecutar_recordatorios
    db = SessionLocal()
    try:
        empresas = db.query(Empresa).filter(Empresa.activa == True).all()
        for empresa in empresas:
            resultado = await ejecutar_recordatorios(db, empresa.id)
<<<<<<< HEAD
            logger.info(f"WP empresa {empresa.id}: {resultado}")
    except Exception as e:
        logger.error(f"Scheduler WP error: {e}", exc_info=True)
=======
            print(f"WP empresa {empresa.id}: {resultado}")
    except Exception as e:
        print(f"Scheduler WP error: {e}")
>>>>>>> 7761f488b2aa6200974f069ea5072699c6dbd1e5
    finally:
        db.close()


<<<<<<< HEAD
def _ejecutar_recordatorios_sync():
    """Wrapper síncrono para ejecutar async recordatorios."""
    asyncio.run(_recordatorios_async())


def loop_scheduler():
    """Bucle principal del scheduler. Corre en hilo separado."""
    ultimo_estado = None
    ultimo_wp = None
    logger.info("Scheduler iniciado correctamente")

    while True:
        ahora = datetime.datetime.now()

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

=======
def loop_scheduler():
    ultimo_estado = None
    ultimo_wp = None
    print("Scheduler iniciado")
    while True:
        ahora = datetime.datetime.now()
        if ultimo_estado is None or (ahora - ultimo_estado).total_seconds() >= 3600:
            actualizar_estados_cuotas()
            ultimo_estado = ahora
        if (ahora.hour == 8 and ahora.minute < 5 and
                (ultimo_wp is None or ultimo_wp.date() < ahora.date())):
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                loop.run_until_complete(_recordatorios_async())
            finally:
                loop.close()
            ultimo_wp = ahora
>>>>>>> 7761f488b2aa6200974f069ea5072699c6dbd1e5
        time.sleep(60)


def iniciar_scheduler():
    t = threading.Thread(target=loop_scheduler, daemon=True, name="Scheduler")
    t.start()
<<<<<<< HEAD
    return t
=======
>>>>>>> 7761f488b2aa6200974f069ea5072699c6dbd1e5
