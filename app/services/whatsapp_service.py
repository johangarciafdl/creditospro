"""
WhatsApp Service v4.0 - Green API por zona
- Cada zona puede tener su propia instancia de Green API
- Fallback a configuración global de la empresa
- Sin dependencia de Meta/WhatsApp Business API
"""
import asyncio
import datetime
import logging
import httpx
from sqlalchemy.orm import Session
from app.database import Empresa, NotificacionWP, ConfiguracionApp, Cuota, Zona
from app.services.prestamo_service import get_cuotas_proximas_vencer, get_cuotas_vencidas_hoy
from app.utils.plan_limits import tiene_funcion

# Cuantos mensajes se mandan en paralelo como maximo. El cuello de botella es
# la latencia de red hacia Green API (~1-2s por mensaje), no CPU, asi que
# superponer las llamadas HTTP baja el tiempo total del lote de N*latencia a
# aprox. (N/limite)*latencia. No conviene subirlo mucho mas: Green API tiene
# su propio limite de requests por instancia.
_MAX_ENVIOS_CONCURRENTES = 5

logger = logging.getLogger(__name__)

GREEN_API_BASE_URL = "https://api.green-api.com"


def get_config_by_empresa(db: Session, empresa_id: int) -> ConfiguracionApp:
    config = db.query(ConfiguracionApp).filter(ConfiguracionApp.empresa_id == empresa_id).first()
    if not config:
        config = ConfiguracionApp(empresa_id=empresa_id)
        db.add(config); db.commit()
    return config


def formatear_telefono(tel: str, pais: str = "57") -> str:
    tel = tel.strip().replace(" ","").replace("-","").replace("+","")
    if tel.startswith("0"): tel = tel[1:]
    if not tel.startswith(pais) and len(tel) == 10: tel = pais + tel
    return tel


def construir_mensaje(plantilla: str, datos: dict, empresa: str) -> str:
    return (plantilla
        .replace("{nombre}", datos.get("nombre",""))
        .replace("{num_cuota}", str(datos.get("num_cuota","")))
        .replace("{valor}", f"{datos.get('valor',0):,.0f}")
        .replace("{fecha}", str(datos.get("fecha_vencimiento","")))
        .replace("{empresa}", empresa)
        .replace("{dias}", str(datos.get("dias_restantes", datos.get("dias_vencida",""))))
    )


async def _green_api(telefono: str, mensaje: str, instance_id: str, token: str) -> bool:
    """Envía mensaje vía Green API (https://green-api.com)."""
    url = f"{GREEN_API_BASE_URL}/waInstance{instance_id}/sendMessage/{token}"
    payload = {"chatId": f"{telefono}@c.us", "message": mensaje}
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.post(url, json=payload)
            if r.status_code == 200 and r.json().get("idMessage"):
                return True
            logger.warning("Green API respuesta inesperada para %s: %s %s", telefono, r.status_code, r.text[:200])
            return False
    except httpx.HTTPError as e:
        logger.warning("Green API HTTP error para %s: %s", telefono, e)
        return False
    except Exception:
        logger.exception("Green API error inesperado para %s", telefono)
        return False


def _resolver_creds(zona: Zona | None, config: ConfiguracionApp) -> tuple[str, str] | None:
    """Prioridad 1: instancia Green API propia de la zona (bot_phone/bot_apikey
    se reutilizan como instance_id/token). Prioridad 2: instancia global de la
    empresa. None si no hay ninguna configurada (se simula el envio)."""
    if zona and zona.bot_activo and zona.bot_phone and zona.bot_apikey:
        return (zona.bot_phone, zona.bot_apikey)
    if config.wp_activo and config.wp_phone_id and config.wp_token:
        return (config.wp_phone_id, config.wp_token)
    return None


def _crear_notificacion(db: Session, empresa_id: int, cliente_id: int, cuota_id: int,
                         telefono: str, mensaje: str, tipo: str, bloqueado: bool) -> NotificacionWP:
    notif = NotificacionWP(
        empresa_id=empresa_id, cliente_id=cliente_id, cuota_id=cuota_id,
        telefono=telefono, mensaje=mensaje, tipo=tipo,
        estado="Bloqueado" if bloqueado else "Pendiente",
    )
    db.add(notif)
    db.flush()
    return notif


async def _ejecutar_envio(creds: tuple[str, str] | None, tel_fmt: str, mensaje: str) -> bool:
    """Solo la llamada HTTP (o la simulacion si no hay bot configurado) -- sin
    tocar la base de datos, para poder correr muchas de estas concurrentemente
    con asyncio.gather sin compartir la Session entre tareas paralelas."""
    if creds is None:
        return True  # simulación sin bot configurado
    return await _green_api(tel_fmt, mensaje, creds[0], creds[1])


async def enviar_a_zona(
    telefono_cliente: str, mensaje: str,
    zona_id: int, db: Session,
    cliente_id: int, cuota_id: int,
    tipo: str, empresa_id: int
) -> bool:
    """
    Envío individual e inmediato -- usa el bot de la zona si está configurado,
    sino la config global de la empresa. Para enviar muchos a la vez con
    concurrencia real (scheduler, "enviar ahora"), ver ejecutar_recordatorios.
    """
    zona = db.query(Zona).filter(Zona.id == zona_id).first() if zona_id else None
    config = get_config_by_empresa(db, empresa_id)
    tel_fmt = formatear_telefono(telefono_cliente)

    # Punto unico de control por plan: cubre tanto el scheduler automatico
    # como los envios manuales, sin importar por donde se haya llegado hasta
    # aqui (ninguna otra ruta llama a Green API directamente).
    empresa = db.query(Empresa).filter(Empresa.id == empresa_id).first()
    plan_ok = bool(empresa and tiene_funcion(empresa, "whatsapp"))
    notif = _crear_notificacion(db, empresa_id, cliente_id, cuota_id, tel_fmt, mensaje, tipo, bloqueado=not plan_ok)

    if not plan_ok:
        db.commit()
        logger.info("WhatsApp bloqueado por plan para empresa_id=%s (cliente=%s)", empresa_id, cliente_id)
        return False

    ok = False
    try:
        ok = await _ejecutar_envio(_resolver_creds(zona, config), tel_fmt, mensaje)
        notif.estado = "Enviado" if ok else "Error"
        notif.enviado_at = datetime.datetime.now()
        db.commit()
    except Exception:
        logger.exception("Error enviando WhatsApp a %s (cliente=%s, cuota=%s)",
                         tel_fmt, cliente_id, cuota_id)
        try:
            notif.estado = "Error"
            db.commit()
        except Exception:
            db.rollback()
            logger.exception("No se pudo actualizar estado de notificacion id=%s", notif.id)
    return ok


# Alias para compatibilidad
async def enviar_notificacion(telefono, mensaje, db, cliente_id, cuota_id, tipo, empresa_id, zona_id=None):
    return await enviar_a_zona(telefono, mensaje, zona_id, db, cliente_id, cuota_id, tipo, empresa_id)


async def _enviar_lote(db: Session, empresa_id: int, items: list[dict], tipo: str) -> tuple[int, int, list[dict]]:
    """Envía varios mensajes en paralelo (acotado por _MAX_ENVIOS_CONCURRENTES)
    en vez de uno por uno como antes. Cada item lleva: telefono, mensaje,
    cliente_id, cuota_id y opcionalmente zona_id.

    De paso evita el problema N+1 de resolver plan/zona/config por cada
    mensaje por separado: se consultan una sola vez para todo el lote.
    Devuelve (enviados, errores, items que sí se enviaron con éxito).
    """
    if not items:
        return 0, 0, []

    empresa = db.query(Empresa).filter(Empresa.id == empresa_id).first()
    plan_ok = bool(empresa and tiene_funcion(empresa, "whatsapp"))
    config = get_config_by_empresa(db, empresa_id)

    zona_ids = {it["zona_id"] for it in items if it.get("zona_id")}
    zonas_por_id = {z.id: z for z in db.query(Zona).filter(Zona.id.in_(zona_ids)).all()} if zona_ids else {}

    preparados = []
    for it in items:
        tel_fmt = formatear_telefono(it["telefono"])
        notif = _crear_notificacion(
            db, empresa_id, it["cliente_id"], it["cuota_id"], tel_fmt, it["mensaje"], tipo,
            bloqueado=not plan_ok,
        )
        creds = _resolver_creds(zonas_por_id.get(it.get("zona_id")), config) if plan_ok else None
        preparados.append({"item": it, "notif": notif, "creds": creds, "tel_fmt": tel_fmt, "mensaje": it["mensaje"]})
    db.commit()

    if not plan_ok:
        logger.info("WhatsApp bloqueado por plan para empresa_id=%s (%d mensajes)", empresa_id, len(items))
        return 0, len(items), []

    semaforo = asyncio.Semaphore(_MAX_ENVIOS_CONCURRENTES)

    async def _uno(p: dict) -> tuple[dict, bool]:
        async with semaforo:
            try:
                ok = await _ejecutar_envio(p["creds"], p["tel_fmt"], p["mensaje"])
            except Exception:
                logger.exception("Error enviando WhatsApp a %s (cliente=%s, cuota=%s)",
                                 p["tel_fmt"], p["item"]["cliente_id"], p["item"]["cuota_id"])
                ok = False
            return p, ok

    resultados = await asyncio.gather(*[_uno(p) for p in preparados])

    enviados = errores = 0
    exitosos = []
    for p, ok in resultados:
        p["notif"].estado = "Enviado" if ok else "Error"
        p["notif"].enviado_at = datetime.datetime.now()
        if ok:
            enviados += 1
            exitosos.append(p["item"])
        else:
            errores += 1
    db.commit()
    return enviados, errores, exitosos


async def ejecutar_recordatorios(db: Session, empresa_id: int):
    config = get_config_by_empresa(db, empresa_id)
    empresa_nombre = config.empresa_nombre or "CreditosPro"

    proximas = get_cuotas_proximas_vencer(db, empresa_id=empresa_id, dias=config.dias_aviso_vencimiento)
    items_proximas = [{
        "telefono": c["telefono"], "cliente_id": c["cliente_id"], "cuota_id": c["cuota_id"],
        "zona_id": c.get("zona_id"),
        "mensaje": construir_mensaje(
            config.wp_mensaje_recordatorio or "Hola {nombre}, su cuota #{num_cuota} vence el {fecha}.", c, empresa_nombre
        ),
    } for c in proximas]
    enviados_p, errores_p, exitosos_p = await _enviar_lote(db, empresa_id, items_proximas, "Recordatorio")
    if exitosos_p:
        # Bulk update en vez de un commit por cada cuota notificada.
        cuota_ids = [it["cuota_id"] for it in exitosos_p]
        db.query(Cuota).filter(Cuota.id.in_(cuota_ids)).update(
            {"notificado_wp": True}, synchronize_session=False
        )
        db.commit()

    vencidas = get_cuotas_vencidas_hoy(db, empresa_id=empresa_id)[:20]
    items_vencidas = [{
        "telefono": c["telefono"], "cliente_id": c["cliente_id"], "cuota_id": c["cuota_id"],
        "zona_id": c.get("zona_id"),
        "mensaje": construir_mensaje(
            config.wp_mensaje_vencida or "Hola {nombre}, su cuota #{num_cuota} vencio el {fecha}.", c, empresa_nombre
        ),
    } for c in vencidas]
    enviados_v, errores_v, _ = await _enviar_lote(db, empresa_id, items_vencidas, "Vencimiento")

    return {"enviados": enviados_p + enviados_v, "errores": errores_p + errores_v}
