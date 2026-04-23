"""
Setup router — Registro inicial de empresa
Al primer acceso, la empresa configura su cuenta
"""
from fastapi import APIRouter, Request, Depends, Form
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.database import get_db, Empresa, Usuario, Zona
from app.auth import hash_password

router = APIRouter()
templates = Jinja2Templates(directory="templates")


@router.get("/")
async def pagina_setup(request: Request, db: Session = Depends(get_db)):
    """Muestra formulario de registro si no hay empresas configuradas"""
    total = db.query(Empresa).filter(Empresa.setup_completo == True).count()
    if total > 0:
        return RedirectResponse(url="/auth/login", status_code=303)
    return templates.TemplateResponse("setup.html", {"request": request})


@router.post("/")
async def crear_empresa(
    empresa_nombre: str = Form(...),
    empresa_nit: str = Form(""),
    empresa_tel: str = Form(""),
    admin_nombre: str = Form(...),
    admin_username: str = Form(...),
    admin_password: str = Form(...),
    db: Session = Depends(get_db),
):
    # Validaciones
    if len(admin_password) < 6:
        return JSONResponse({"error": "La contraseña debe tener al menos 6 caracteres"}, status_code=400)
    if db.query(Usuario).filter(Usuario.username == admin_username).first():
        return JSONResponse({"error": f"El usuario '{admin_username}' ya existe"}, status_code=400)

    # Crear empresa
    empresa = Empresa(
        nombre=empresa_nombre.strip(),
        nit=empresa_nit.strip() or None,
        telefono=empresa_tel.strip() or None,
        plan="trial",
        setup_completo=True,
    )
    db.add(empresa)
    db.flush()

    # Crear zona por defecto
    zona = Zona(
        empresa_id=empresa.id,
        codigo="PRINCIPAL",
        nombre="Zona Principal",
        ciudad="Medellín",
    )
    db.add(zona)
    db.flush()

    # Crear admin
    admin = Usuario(
        empresa_id=empresa.id,
        username=admin_username.strip().lower(),
        nombre_completo=admin_nombre.strip(),
        password_hash=hash_password(admin_password),
        rol="admin",
    )
    db.add(admin)
    db.commit()

    return JSONResponse({"ok": True, "mensaje": "Empresa configurada exitosamente"})
