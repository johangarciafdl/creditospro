"""Servicio WhatsApp v2.1 - multi-tenant"""
import datetime
import httpx
from sqlalchemy.orm import Session
from app.database import NotificacionWP, ConfiguracionApp, Cuota
from app.services.prestamo_service import get_cuotas_proximas_vencer, get_cuotas_vencidas_hoy


def get_config_by_empresa(db: Session, empresa_id: int) -> ConfiguracionApp:
    """FIX: busca config por empresa, no por id=1"""
    config = db.query(ConfiguracionApp).filter(
        ConfiguracionApp.empresa_id == empresa_id
    ).first()
    if not config:
        config = ConfiguracionApp(empresa_id=empresa_id)
        db.add(config)
        db.commit()
    return config


# Alias para compatibilidad con código legado
def get_config(db: Session) -> ConfiguracionApp:
    return db.query(ConfiguracionApp).first()


def formatear_telefono(tel: str, pais: str = "57") -> str:
    tel = tel.strip().replace(" ", "").replace("-", "").replace("+", "")
    if tel.startswith("0"):
        tel = tel[1:]
    if not tel.startswith(pais) and len(tel) == 10:
        tel = pais + tel
    return tel


def construir_mensaje(plantilla: str, datos: dict, empresa: str) -> str:
    return (plantilla
        .replace("{nombre}", datos.get("nombre", ""))
        .replace("{num_cuota}", str(datos.get("num_cuota", "")))
        .replace("{valor}", f"{datos.get('valor', 0):,.0f}")
        .replace("{fecha}", str(datos.get("fecha_vencimiento", "")))
        .replace("{empresa}", empresa)
        .replace("{dias}", str(datos.get("dias_restantes", datos.get("dias_vencida", ""))))
    )


async def _enviar_meta(telefono: str, mensaje: str, config: ConfiguracionApp) -> bool:
    url = f"https://graph.facebook.com/v18.0/{config.wp_phone_id}/messages"
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.post(url, json={
            "messaging_product": "whatsapp", "to": telefono,
            "type": "text", "text": {"body": mensaje}
        }, headers={"Authorization": f"Bearer {config.wp_token}", "Content-Type": "application/json"})
        return r.status_code == 200


async def _enviar_callmebot(telefono: str, mensaje: str, api_key: str) -> bool:
    import urllib.parse
    url = f"https://api.callmebot.com/whatsapp.php?phone={telefono}&text={urllib.parse.quote(mensaje)}&apikey={api_key}"
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.get(url)
        return r.status_code == 200


async def enviar_notificacion(
    telefono: str, mensaje: str, db: Session,
    cliente_id: int, cuota_id: int, tipo: str, empresa_id: int
) -> bool:
    config = get_config_by_empresa(db, empresa_id)
    tel_fmt = formatear_telefono(telefono)

    notif = NotificacionWP(
        empresa_id=empresa_id, cliente_id=cliente_id,
        cuota_id=cuota_id, telefono=tel_fmt,
        mensaje=mensaje, tipo=tipo, estado="Pendiente",
    )
    db.add(notif)
    db.flush()

    try:
        if config.wp_activo and config.wp_token and config.wp_phone_id:
            ok = await _enviar_meta(tel_fmt, mensaje, config)
        elif config.wp_activo and config.wp_api_key:
            ok = await _enviar_callmebot(tel_fmt, mensaje, config.wp_api_key)
        else:
            ok = True  # simulación

        notif.estado = "Enviado" if ok else "Error"
        notif.enviado_at = datetime.datetime.now()
        db.commit()
        return ok
    except Exception as e:
        notif.estado = "Error"
        db.commit()
        print(f"WP error: {e}")
        return False


async def ejecutar_recordatorios(db: Session, empresa_id: int):
    config = get_config_by_empresa(db, empresa_id)
    empresa = config.empresa_nombre or "CreditosPro"
    enviados = errores = 0

    proximas = get_cuotas_proximas_vencer(db, empresa_id=empresa_id, dias=config.dias_aviso_vencimiento)
    for c in proximas:
        msg = construir_mensaje(config.wp_mensaje_recordatorio or "", c, empresa)
        ok = await enviar_notificacion(c["telefono"], msg, db, c["cliente_id"], c["cuota_id"], "Recordatorio", empresa_id)
        if ok:
            cuota = db.query(Cuota).filter(Cuota.id == c["cuota_id"]).first()
            if cuota:
                cuota.notificado_wp = True
                db.commit()
            enviados += 1
        else:
            errores += 1

    vencidas = get_cuotas_vencidas_hoy(db, empresa_id=empresa_id)
    for c in vencidas[:20]:
        msg = construir_mensaje(config.wp_mensaje_vencida or "", c, empresa)
        ok = await enviar_notificacion(c["telefono"], msg, db, c["cliente_id"], c["cuota_id"], "Vencimiento", empresa_id)
        if ok: enviados += 1
        else: errores += 1

    return {"enviados": enviados, "errores": errores}
