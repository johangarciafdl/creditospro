"""
WhatsApp Service v3.0 - CallMeBot por zona
- Cada zona puede tener su propio número y apikey de CallMeBot
- Fallback a configuración global de la empresa
- Sin dependencia de Meta/WhatsApp Business API
"""
import datetime
import logging
import urllib.parse
import httpx
from sqlalchemy.orm import Session
from app.database import NotificacionWP, ConfiguracionApp, Cuota, Zona
from app.services.prestamo_service import get_cuotas_proximas_vencer, get_cuotas_vencidas_hoy

logger = logging.getLogger(__name__)


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


async def _callmebot(telefono: str, mensaje: str, apikey: str) -> bool:
    """Envía mensaje vía CallMeBot"""
    url = f"https://api.callmebot.com/whatsapp.php?phone={telefono}&text={urllib.parse.quote(mensaje)}&apikey={apikey}"
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.get(url)
            return r.status_code == 200
    except httpx.HTTPError as e:
        logger.warning("CallMeBot HTTP error para %s: %s", telefono, e)
        return False
    except Exception:
        logger.exception("CallMeBot error inesperado para %s", telefono)
        return False


async def enviar_a_zona(
    telefono_cliente: str, mensaje: str,
    zona_id: int, db: Session,
    cliente_id: int, cuota_id: int,
    tipo: str, empresa_id: int
) -> bool:
    """
    Envía WA usando el bot de la zona si está configurado,
    sino usa la config global de la empresa.
    """
    zona = db.query(Zona).filter(Zona.id == zona_id).first() if zona_id else None
    config = get_config_by_empresa(db, empresa_id)
    tel_fmt = formatear_telefono(telefono_cliente)

    notif = NotificacionWP(
        empresa_id=empresa_id, cliente_id=cliente_id,
        cuota_id=cuota_id, telefono=tel_fmt,
        mensaje=mensaje, tipo=tipo, estado="Pendiente",
    )
    db.add(notif); db.flush()

    ok = False
    try:
        # Prioridad 1: bot propio de la zona
        if zona and zona.bot_activo and zona.bot_phone and zona.bot_apikey:
            ok = await _callmebot(tel_fmt, mensaje, zona.bot_apikey)
        # Prioridad 2: config global callmebot
        elif config.wp_activo and config.wp_api_key:
            ok = await _callmebot(tel_fmt, mensaje, config.wp_api_key)
        else:
            ok = True  # simulación sin bot configurado

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


async def ejecutar_recordatorios(db: Session, empresa_id: int):
    config = get_config_by_empresa(db, empresa_id)
    empresa = config.empresa_nombre or "CreditosPro"
    enviados = errores = 0

    proximas = get_cuotas_proximas_vencer(db, empresa_id=empresa_id, dias=config.dias_aviso_vencimiento)
    for c in proximas:
        msg = construir_mensaje(config.wp_mensaje_recordatorio or "Hola {nombre}, su cuota #{num_cuota} vence el {fecha}.", c, empresa)
        ok = await enviar_a_zona(c["telefono"], msg, c.get("zona_id"), db, c["cliente_id"], c["cuota_id"], "Recordatorio", empresa_id)
        if ok:
            cuota = db.query(Cuota).filter(Cuota.id == c["cuota_id"]).first()
            if cuota: cuota.notificado_wp = True; db.commit()
            enviados += 1
        else: errores += 1

    vencidas = get_cuotas_vencidas_hoy(db, empresa_id=empresa_id)
    for c in vencidas[:20]:
        msg = construir_mensaje(config.wp_mensaje_vencida or "Hola {nombre}, su cuota #{num_cuota} vencio el {fecha}.", c, empresa)
        ok = await enviar_a_zona(c["telefono"], msg, c.get("zona_id"), db, c["cliente_id"], c["cuota_id"], "Vencimiento", empresa_id)
        if ok: enviados += 1
        else: errores += 1

    return {"enviados": enviados, "errores": errores}
