"""Zonas router"""
from fastapi import APIRouter, Request, Depends, Form
from fastapi.responses import JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from pathlib import Path

from app.auth import require_login
from app.database import get_db, Zona, Cliente, Prestamo, Cobro

BASE_DIR = Path(__file__).parent.parent.parent
router = APIRouter()
templates = Jinja2Templates(directory="templates")


@router.get("/")
async def listar_zonas(request: Request, db: Session = Depends(get_db), current_user=Depends(require_login)):
    zonas = db.query(Zona).all()
    data = []
    for z in zonas:
        clientes = db.query(Cliente).filter(Cliente.zona_id == z.id, Cliente.activo == True).count()
        prestamos = db.query(Prestamo).filter(Prestamo.zona_id == z.id, Prestamo.estado == "Activo").count()
        data.append({
            "id": z.id, "codigo": z.codigo, "nombre": z.nombre,
            "ciudad": z.ciudad, "cobrador": z.cobrador_nombre or "—",
            "cobrador_tel": z.cobrador_tel or "—", "cobrador_moto": z.cobrador_moto or "—",
            "clientes": clientes, "prestamos": prestamos,
            "activa": z.activa, "lat": z.lat, "lng": z.lng,
        })
    return templates.TemplateResponse("zonas.html", context= {
        "request": request, "current_user": current_user, "page": "zonas", "zonas": data,
    })


@router.post("/nueva")
async def crear_zona(
    codigo: str = Form(...), nombre: str = Form(...), ciudad: str = Form("Medellín"),
    departamento: str = Form("Antioquia"), pais: str = Form("Colombia"),
    cobrador_nombre: str = Form(""), cobrador_tel: str = Form(""), cobrador_moto: str = Form(""),
    lat: float = Form(None), lng: float = Form(None),
    db: Session = Depends(get_db)
):
    zona = Zona(
        codigo=codigo.upper(), nombre=nombre, ciudad=ciudad,
        departamento=departamento, pais=pais,
        cobrador_nombre=cobrador_nombre or None, cobrador_tel=cobrador_tel or None,
        cobrador_moto=cobrador_moto or None, lat=lat, lng=lng,
    )
    db.add(zona)
    db.commit()
    return JSONResponse({"ok": True, "mensaje": "Zona creada"})


@router.post("/{zona_id}/editar")
async def editar_zona(
    zona_id: int, nombre: str = Form(...), cobrador_nombre: str = Form(""),
    cobrador_tel: str = Form(""), cobrador_moto: str = Form(""),
    activa: bool = Form(True), db: Session = Depends(get_db)
):
    zona = db.query(Zona).filter(Zona.id == zona_id).first()
    if not zona:
        return JSONResponse({"error": "No encontrado"}, status_code=404)
    zona.nombre = nombre
    zona.cobrador_nombre = cobrador_nombre or None
    zona.cobrador_tel = cobrador_tel or None
    zona.cobrador_moto = cobrador_moto or None
    zona.activa = activa
    db.commit()
    return JSONResponse({"ok": True})
