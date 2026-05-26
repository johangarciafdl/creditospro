"""Zonas router v2.1 - multi-tenant"""
from fastapi import APIRouter, Request, Depends, Form
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.database import get_db, Zona, Cliente, Prestamo, Cobro
from app.routers.auth import get_current_user
<<<<<<< HEAD
from app.utils.zone_permissions import get_allowed_zone_ids
=======
>>>>>>> 7761f488b2aa6200974f069ea5072699c6dbd1e5

router = APIRouter()
templates = Jinja2Templates(directory="templates")


@router.get("")
@router.get("/")
async def listar_zonas(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url="/auth/login?next=/zonas", status_code=302)

    eid = user.empresa_id
<<<<<<< HEAD
    allowed_zones = get_allowed_zone_ids(db, user)
    zonas_q = db.query(Zona).filter(Zona.empresa_id == eid)
    if allowed_zones is not None:
        zonas_q = zonas_q.filter(Zona.id.in_(allowed_zones or [-1]))
    zonas = zonas_q.all()
=======
    zonas = db.query(Zona).filter(Zona.empresa_id == eid).all()
>>>>>>> 7761f488b2aa6200974f069ea5072699c6dbd1e5
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

    zona = Zona(
        empresa_id=user.empresa_id,
        codigo=codigo.upper(), nombre=nombre,
        ciudad=ciudad, departamento=departamento, pais=pais,
        cobrador_nombre=cobrador_nombre or None,
        cobrador_tel=cobrador_tel or None,
        cobrador_moto=cobrador_moto or None,
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
<<<<<<< HEAD
    bot_phone: str = Form(""), bot_apikey: str = Form(""),
    bot_activo: str = Form("false"),
=======
>>>>>>> 7761f488b2aa6200974f069ea5072699c6dbd1e5
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

    zona.nombre = nombre
    zona.cobrador_nombre = cobrador_nombre or None
    zona.cobrador_tel = cobrador_tel or None
    zona.cobrador_moto = cobrador_moto or None
    zona.activa = activa.lower() in ("true", "1", "on")
<<<<<<< HEAD
    zona.bot_phone = bot_phone.strip() or None
    zona.bot_apikey = bot_apikey.strip() or None
    zona.bot_activo = bot_activo.lower() in ("true", "1", "on")
=======
>>>>>>> 7761f488b2aa6200974f069ea5072699c6dbd1e5
    db.commit()
    return JSONResponse({"ok": True})
