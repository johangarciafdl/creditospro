"""WhatsApp Bot router v2.1 - multi-tenant + auth"""
import datetime
from fastapi import APIRouter, Request, Depends, Form
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.database import get_db, NotificacionWP, ConfiguracionApp, Cliente, Cuota, Prestamo
from app.routers.auth import get_current_user
from app.services.whatsapp_service import ejecutar_recordatorios, enviar_notificacion, get_config_by_empresa

router = APIRouter()
templates = Jinja2Templates(directory="templates")


@router.get("")
@router.get("/")
async def panel_whatsapp(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url="/auth/login?next=/whatsapp", status_code=302)

    eid = user.empresa_id
    config = get_config_by_empresa(db, eid)
    hoy = datetime.date.today()
    limite = hoy + datetime.timedelta(days=config.dias_aviso_vencimiento)

    notifs = db.query(NotificacionWP).filter(
        NotificacionWP.empresa_id == eid
    ).order_by(NotificacionWP.creado.desc()).limit(100).all()

    clientes_map = {
        c.id: c for c in db.query(Cliente).filter(Cliente.empresa_id == eid).all()
    }
    notifs_data = []
    for n in notifs:
        c = clientes_map.get(n.cliente_id)
        notifs_data.append({
            "id": n.id, "cliente": c.nombre if c else "—",
            "telefono": n.telefono, "tipo": n.tipo, "estado": n.estado,
            "mensaje": n.mensaje[:80] + "..." if len(n.mensaje) > 80 else n.mensaje,
            "enviado": n.enviado_at.strftime("%d/%m %H:%M") if n.enviado_at else "—",
            "creado": n.creado.strftime("%d/%m %H:%M") if n.creado else "—",
        })

    proximas = db.query(Cuota, Prestamo, Cliente).join(
        Prestamo, Cuota.prestamo_id == Prestamo.id
    ).join(Cliente, Prestamo.cliente_id == Cliente.id).filter(
        Cuota.empresa_id == eid,
        Cuota.estado == "Pendiente",
        Cuota.fecha_vencimiento >= hoy,
        Cuota.fecha_vencimiento <= limite,
    ).all()

    proximas_data = [
        {"cliente": c.nombre, "tel": c.whatsapp or c.telefono,
         "num_cuota": cu.numero, "valor": cu.valor,
         "vencimiento": cu.fecha_vencimiento.strftime("%d/%m/%Y"),
         "dias": (cu.fecha_vencimiento - hoy).days}
        for cu, p, c in proximas
    ]

    return templates.TemplateResponse(request, "whatsapp.html", {
        "page": "whatsapp", "config": config,
        "notifs": notifs_data, "proximas": proximas_data,
        "current_user": user,
        "total_enviados": db.query(NotificacionWP).filter(NotificacionWP.empresa_id == eid, NotificacionWP.estado == "Enviado").count(),
        "total_errores": db.query(NotificacionWP).filter(NotificacionWP.empresa_id == eid, NotificacionWP.estado == "Error").count(),
        "total_pendientes": len(proximas_data),
    })


@router.post("/configurar")
async def configurar_wp(
    request: Request,
    wp_api_key: str = Form(""), wp_phone_id: str = Form(""),
    wp_token: str = Form(""), wp_activo: bool = Form(False),
    dias_aviso: int = Form(2),
    wp_mensaje_recordatorio: str = Form(""),
    wp_mensaje_vencida: str = Form(""),
    db: Session = Depends(get_db)
):
    user = get_current_user(request, db)
    if not user or user.rol not in ("admin", "superadmin"):
        return JSONResponse({"error": "Sin permisos"}, status_code=403)

    config = get_config_by_empresa(db, user.empresa_id)
    config.wp_api_key = wp_api_key or None
    config.wp_phone_id = wp_phone_id or None
    config.wp_token = wp_token or None
    config.wp_activo = wp_activo
    config.dias_aviso_vencimiento = dias_aviso
    if wp_mensaje_recordatorio:
        config.wp_mensaje_recordatorio = wp_mensaje_recordatorio
    if wp_mensaje_vencida:
        config.wp_mensaje_vencida = wp_mensaje_vencida
    db.commit()
    return JSONResponse({"ok": True, "mensaje": "Configuración guardada"})


@router.post("/enviar-ahora")
async def enviar_ahora(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user or user.rol not in ("admin", "superadmin"):
        return JSONResponse({"error": "Sin permisos"}, status_code=403)
    resultado = await ejecutar_recordatorios(db, user.empresa_id)
    return JSONResponse({"ok": True, **resultado})


@router.post("/enviar-manual")
async def enviar_manual(
    request: Request,
    cliente_id: int = Form(...),
    mensaje: str = Form(...),
    db: Session = Depends(get_db)
):
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "No autenticado"}, status_code=401)

    cliente = db.query(Cliente).filter(
        Cliente.id == cliente_id, Cliente.empresa_id == user.empresa_id
    ).first()
    if not cliente:
        return JSONResponse({"error": "Cliente no encontrado"}, status_code=404)

    tel = cliente.whatsapp or cliente.telefono
    ok = await enviar_notificacion(tel, mensaje, db, cliente_id, None, "Manual", user.empresa_id)
    return JSONResponse({"ok": ok, "mensaje": "Enviado" if ok else "Error al enviar"})
