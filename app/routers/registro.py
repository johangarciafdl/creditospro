"""
Registro de nueva empresa - Onboarding multi-tenant
Permite que cualquier empresa nueva cree su cuenta independiente
"""
from fastapi import APIRouter, Request, Depends, Form
from fastapi.responses import RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.database import get_db, Empresa, Usuario, ConfiguracionApp, Zona
from app.utils.security import get_password_hash, create_access_token
<<<<<<< HEAD
from app.routers.auth import SESSION_COOKIE, IS_PRODUCTION
from app.utils.settings import settings
=======
from app.routers.auth import SESSION_COOKIE
>>>>>>> 7761f488b2aa6200974f069ea5072699c6dbd1e5

router = APIRouter()
templates = Jinja2Templates(directory="templates")


@router.get("")
@router.get("/")
async def registro_page(request: Request):
<<<<<<< HEAD
    if not settings.ALLOW_PUBLIC_REGISTRATION:
        return RedirectResponse(url="/seleccionar-empresa", status_code=302)
=======
>>>>>>> 7761f488b2aa6200974f069ea5072699c6dbd1e5
    # Si ya tiene sesión activa, ir al dashboard
    from app.routers.auth import get_current_user
    from app.database import SessionLocal
    db = SessionLocal()
    try:
        user = get_current_user(request, db)
        if user:
            return RedirectResponse(url="/dashboard", status_code=302)
    finally:
        db.close()
    return templates.TemplateResponse(request, "registro.html", {"error": None, "success": False})


@router.post("")
@router.post("/")
async def registro_submit(
    request: Request,
    empresa_nombre: str = Form(...),
    empresa_nit: str = Form(""),
    pais: str = Form("Colombia"),
    admin_nombre: str = Form(...),
    admin_username: str = Form(...),
    admin_password: str = Form(...),
    admin_password2: str = Form(...),
    db: Session = Depends(get_db)
):
<<<<<<< HEAD
    if not settings.ALLOW_PUBLIC_REGISTRATION:
        return JSONResponse({"error": "Registro publico deshabilitado"}, status_code=403)
=======
>>>>>>> 7761f488b2aa6200974f069ea5072699c6dbd1e5
    # Validaciones
    if len(admin_password) < 6:
        return templates.TemplateResponse(request, "registro.html", {
            "error": "La contraseña debe tener al menos 6 caracteres", "success": False
        })
    if admin_password != admin_password2:
        return templates.TemplateResponse(request, "registro.html", {
            "error": "Las contraseñas no coinciden", "success": False
        })

    username_clean = admin_username.strip().lower()

    # Username único globalmente para evitar confusiones
    existente = db.query(Usuario).filter(Usuario.username == username_clean).first()
    if existente:
        return templates.TemplateResponse(request, "registro.html", {
            "error": "Ese nombre de usuario ya está en uso, elige otro", "success": False
        })

    try:
        # Crear empresa
        empresa = Empresa(
            nombre=empresa_nombre.strip(),
            nit=empresa_nit.strip() or None,
            pais=pais,
            plan="free",
            activa=True,
        )
        db.add(empresa)
        db.flush()

        # Config por defecto de la empresa
        config = ConfiguracionApp(
            empresa_id=empresa.id,
            empresa_nombre=empresa_nombre.strip(),
            pais=pais,
            moneda="COP" if pais == "Colombia" else "USD",
            tasa_default=20.0,
            cuotas_default=30,
        )
        db.add(config)

        # Zona por defecto
        zona = Zona(
            empresa_id=empresa.id,
            codigo="Z001",
            nombre="Zona Principal",
            ciudad="",
            activa=True,
        )
        db.add(zona)
        db.flush()

        # Admin de la empresa
        admin = Usuario(
            empresa_id=empresa.id,
            username=username_clean,
            nombre=admin_nombre.strip(),
<<<<<<< HEAD
            password_hash=get_password_hash(admin_password),
=======
            hashed_password=get_password_hash(admin_password),
>>>>>>> 7761f488b2aa6200974f069ea5072699c6dbd1e5
            rol="admin",
            activo=True,
        )
        db.add(admin)
        db.commit()
        db.refresh(admin)

        # Login automático después del registro
        token = create_access_token({
            "sub": str(admin.id),
            "rol": admin.rol,
            "nombre": admin.nombre,
            "empresa_id": admin.empresa_id,
        })

        response = RedirectResponse(url="/dashboard", status_code=302)
        response.set_cookie(
            key=SESSION_COOKIE, value=token,
<<<<<<< HEAD
            httponly=True, samesite="strict", max_age=60 * 60 * 12, secure=IS_PRODUCTION,
=======
            httponly=True, samesite="lax", max_age=60 * 60 * 12, secure=False,
>>>>>>> 7761f488b2aa6200974f069ea5072699c6dbd1e5
        )
        return response

    except Exception as e:
        db.rollback()
        return templates.TemplateResponse(request, "registro.html", {
            "error": f"Error al crear la cuenta: {str(e)}", "success": False
        })
