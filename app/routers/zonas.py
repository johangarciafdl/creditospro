"""Zonas router v2.1 - multi-tenant"""
from fastapi import APIRouter, Request, Depends, Form, HTTPException
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.database import get_db, Zona, Cliente, Prestamo, Cobro
from app.routers.auth import get_current_user
from app.utils.validators import validar_nombre, validar_telefono, limpiar_texto
from app.utils.zone_permissions import get_allowed_zone_ids

router = APIRouter()
templates = Jinja2Templates(directory="templates")


def _sin_html(texto: str, campo: str, max_len: int = 100) -> str:
    """Limpia y rechaza '<'/'>' -- estos campos se muestran en varios lugares
    del frontend y no tienen un formato fijo (a diferencia de cedula/telefono),
    asi que en vez de una lista blanca estricta solo bloqueamos lo que
    permitiria inyectar HTML/JS."""
    t = limpiar_texto(texto, max_len)
    if "<" in t or ">" in t:
        raise HTTPException(400, f"{campo} no puede contener '<' o '>'")
    return t


@router.get("")
@router.get("/")
async def listar_zonas(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url="/auth/login?next=/zonas", status_code=302)

    eid = user.empresa_id
    allowed_zones = get_allowed_zone_ids(db, user)
    zonas_q = db.query(Zona).filter(Zona.empresa_id == eid)
    if allowed_zones is not None:
        zonas_q = zonas_q.filter(Zona.id.in_(allowed_zones or [-1]))
    zonas = zonas_q.all()
    data = []
    for z in zonas:
        clientes = db.query(Cliente).filter(Cliente.empresa_id == eid, Cliente.zona_id == z.id, Cliente.activo == True).count()
        prestamos = db.query(Prestamo).filter(Prestamo.empresa_id == eid, Prestamo.zona_id == z.id, Prestamo.estado == "Activo").count()
        data.append({
            "id": z.id, "codigo": z.codigo, "nombre": z.nombre,
            "ciudad": z.ciudad, "cobrador": z.cobrador_nombre or "—",
            "cobrador_tel": z.cobrador_tel or "—",
            "cobrador_moto": z.cobrador_moto or "—",
            "clientes": clientes, "prestamos": prestamos,
            "activa": z.activa, "lat": z.lat, "lng": z.lng,
        })

    return templates.TemplateResponse(request, "zonas.html", {
        "page": "zonas", "zonas": data, "current_user": user,
    })


@router.post("/nueva")
async def crear_zona(
    request: Request,
    codigo: str = Form(...), nombre: str = Form(...),
    ciudad: str = Form("Medellín"), departamento: str = Form("Antioquia"),
    pais: str = Form("Colombia"), cobrador_nombre: str = Form(""),
    cobrador_tel: str = Form(""), cobrador_moto: str = Form(""),
    lat: float = Form(None), lng: float = Form(None),
    db: Session = Depends(get_db)
):
    user = get_current_user(request, db)
    if not user or user.rol not in ("admin", "superadmin"):
        return JSONResponse({"error": "Sin permisos"}, status_code=403)

    existente = db.query(Zona).filter(
        Zona.empresa_id == user.empresa_id, Zona.codigo == codigo.upper()
    ).first()
    if existente:
        return JSONResponse({"error": "Código de zona ya existe"}, status_code=400)

    try:
        nombre = _sin_html(nombre, "Nombre de zona")
        cobrador_nombre_limpio = _sin_html(cobrador_nombre, "Cobrador") if cobrador_nombre else None
        cobrador_moto_limpio = _sin_html(cobrador_moto, "Moto/placa", 50) if cobrador_moto else None
        cobrador_tel_limpio = validar_telefono(cobrador_tel, requerido=False)
    except HTTPException as e:
        return JSONResponse({"error": e.detail}, status_code=e.status_code)

    zona = Zona(
        empresa_id=user.empresa_id,
        codigo=codigo.upper(), nombre=nombre,
        ciudad=ciudad, departamento=departamento, pais=pais,
        cobrador_nombre=cobrador_nombre_limpio,
        cobrador_tel=cobrador_tel_limpio,
        cobrador_moto=cobrador_moto_limpio,
        lat=lat, lng=lng,
    )
    db.add(zona)
    db.commit()
    return JSONResponse({"ok": True, "mensaje": "Zona creada"})


@router.post("/{zona_id}/editar")
async def editar_zona(
    request: Request, zona_id: int,
    nombre: str = Form(...), cobrador_nombre: str = Form(""),
    cobrador_tel: str = Form(""), cobrador_moto: str = Form(""),
    activa: str = Form("true"),
    bot_phone: str = Form(""), bot_apikey: str = Form(""),
    bot_activo: str = Form("false"),
    db: Session = Depends(get_db)
):
    user = get_current_user(request, db)
    if not user or user.rol not in ("admin", "superadmin"):
        return JSONResponse({"error": "Sin permisos"}, status_code=403)

    zona = db.query(Zona).filter(
        Zona.id == zona_id, Zona.empresa_id == user.empresa_id
    ).first()
    if not zona:
        return JSONResponse({"error": "No encontrado"}, status_code=404)

    try:
        zona.nombre = _sin_html(nombre, "Nombre de zona")
        zona.cobrador_nombre = _sin_html(cobrador_nombre, "Cobrador") if cobrador_nombre else None
        zona.cobrador_moto = _sin_html(cobrador_moto, "Moto/placa", 50) if cobrador_moto else None
        zona.cobrador_tel = validar_telefono(cobrador_tel, requerido=False)
    except HTTPException as e:
        return JSONResponse({"error": e.detail}, status_code=e.status_code)
    zona.activa = activa.lower() in ("true", "1", "on")
    zona.bot_phone = bot_phone.strip() or None
    zona.bot_apikey = bot_apikey.strip() or None
    zona.bot_activo = bot_activo.lower() in ("true", "1", "on")
    db.commit()
    return JSONResponse({"ok": True})
