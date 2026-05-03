"""Scheduler v2.1 - multi-tenant, fixed asyncio loop conflict"""
import asyncio, threading, datetime, time
from app.database import SessionLocal, Cuota, Empresa
from sqlalchemy import and_


def actualizar_estados_cuotas():
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
            print(f"Scheduler: {len(cuotas)} cuotas vencidas actualizadas")
    except Exception as e:
        print(f"Scheduler error estados: {e}")
    finally:
        db.close()


async def _recordatorios_async():
    from app.services.whatsapp_service import ejecutar_recordatorios
    db = SessionLocal()
    try:
        empresas = db.query(Empresa).filter(Empresa.activa == True).all()
        for empresa in empresas:
            resultado = await ejecutar_recordatorios(db, empresa.id)
            print(f"WP empresa {empresa.id}: {resultado}")
    except Exception as e:
        print(f"Scheduler WP error: {e}")
    finally:
        db.close()


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
        time.sleep(60)


def iniciar_scheduler():
    t = threading.Thread(target=loop_scheduler, daemon=True, name="Scheduler")
    t.start()
