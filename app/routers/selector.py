"""Selector de empresa - landing page multi-tenant"""
from fastapi import APIRouter, Request, Depends, Response
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.database import get_db, Empresa, Usuario
from app.routers.auth import get_current_user
from app.utils.settings import settings

router = APIRouter()
templates = Jinja2Templates(directory="templates")


@router.get("/seleccionar-empresa")
async def selector_empresa(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if user:
        return RedirectResponse("/dashboard", 302)

    empresas_raw = db.query(Empresa).filter(Empresa.activa == True).order_by(Empresa.nombre).all()
    empresas = []
    for e in empresas_raw:
        count = db.query(func.count(Usuario.id)).filter(
            Usuario.empresa_id == e.id, Usuario.activo == True
        ).scalar() or 0
        empresas.append({
            "id": e.id, "nombre": e.nombre,
            "ciudad": e.ciudad or "Colombia",
            "usuarios_count": count,
        })

    # Si solo hay 1 empresa, ir directo al login
    if len(empresas) == 1:
        return RedirectResponse(f"/auth/login?empresa_id={empresas[0]['id']}", 302)

    return templates.TemplateResponse(request, "selector_empresa.html", {
        "empresas": empresas,
        "allow_public_registration": settings.ALLOW_PUBLIC_REGISTRATION,
    })
