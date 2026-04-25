"""Zonas router - FIXED"""
from fastapi import APIRouter, Request, Depends, Form
from fastapi.responses import JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.auth import require_login, get_current_empresa
from app.database import get_db, Zona, Cliente, Prestamo

router = APIRouter()
templates = Jinja2Templates(directory="templates")


@router.get("/")
async def listar_zonas(
    request: Request,
    db: Session = Depends(get_db),
    current_user=Depends(require_login),
    empresa_id: int = Depends(get_current_empresa)
):
    zonas = db.query(Zona).filter(Zona.empresa_id == empresa_id).all()
    data = []
    for z in zonas:
        clientes = db.query(Cliente).filter(Cliente.zona_id == z.id, Cliente.activo == True).count()
        prestamos = db.query(Prestamo).filter(Prestamo.zona_id == z.id, Prestamo.estado == "Activo").count()
        data.append({
            "id": z.id, "codigo": z.codigo, "nombre": z.nombre,
            "ciudad": z.ciudad or "—",
            "cobrador": z.cobrador_nombre or "—",
            "cobrador_tel": z.cobrador_tel or "—",
            "cobrador_moto": z.cobrador_moto or "—",
            "clientes": clientes, "prestamos": prestamos,
            "activa": z.activa, "lat": z.lat, "lng": z.lng,
        })
    return templates.TemplateResponse("zonas.html", {
        "request": request, "current_user": current_user,
        "page": "zonas", "zonas": data,
    })


@router.post("/nueva")
async def crear_zona(
    codigo: str = Form(...),
    nombre: str = Form(...),
    ciudad: str = Form("Medellín"),
    departamento: str = Form("Antioquia"),
    pais: str = Form("Colombia"),
    cobrador_nombre: str = Form(""),
    cobrador_tel: str = Form(""),
    cobrador_moto: str = Form(""),
    lat: str = Form(""),
    lng: str = Form(""),
    db: Session = Depends(get_db),
    current_user=Depends(require_login),
    empresa_id: int = Depends(get_current_empresa)
):
    try:
        zona = Zona(
            empresa_id=empresa_id,
            codigo=codigo.strip().upper(),
            nombre=nombre.strip(),
            ciudad=ciudad.strip() or "Medellín",
            departamento=departamento or "Antioquia",
            pais=pais or "Colombia",
            cobrador_nombre=cobrador_nombre.strip() or None,
            cobrador_tel=cobrador_tel.strip() or None,
            cobrador_moto=cobrador_moto.strip() or None,
            lat=float(lat) if lat and lat.strip() else None,
            lng=float(lng) if lng and lng.strip() else None,
            activa=True,
        )
        db.add(zona)
        db.commit()
        return JSONResponse({"ok": True, "id": zona.id, "mensaje": "Zona creada exitosamente"})
    except Exception as e:
        db.rollback()
        return JSONResponse({"ok": False, "error": str(e)}, status_code=500)


@router.post("/{zona_id}/editar")
async def editar_zona(
    zona_id: int,
    nombre: str = Form(...),
    cobrador_nombre: str = Form(""),
    cobrador_tel: str = Form(""),
    cobrador_moto: str = Form(""),
    activa: str = Form("true"),
    db: Session = Depends(get_db),
    current_user=Depends(require_login),
    empresa_id: int = Depends(get_current_empresa)
):
    zona = db.query(Zona).filter(Zona.id == zona_id, Zona.empresa_id == empresa_id).first()
    if not zona:
        return JSONResponse({"error": "Zona no encontrada"}, status_code=404)
    zona.nombre = nombre.strip()
    zona.cobrador_nombre = cobrador_nombre.strip() or None
    zona.cobrador_tel = cobrador_tel.strip() or None
    zona.cobrador_moto = cobrador_moto.strip() or None
    zona.activa = activa.lower() in ("true", "on", "1", "si", "yes")
    db.commit()
    return JSONResponse({"ok": True, "mensaje": "Zona actualizada"})
