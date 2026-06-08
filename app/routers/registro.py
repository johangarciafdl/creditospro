"""
Registro de nueva empresa - Onboarding multi-tenant
Permite que cualquier empresa nueva cree su cuenta independiente
"""
import logging

from fastapi import APIRouter, Request, Depends, Form
from fastapi.responses import RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.database import get_db, Empresa, Usuario, ConfiguracionApp, Zona
from app.utils.security import get_password_hash, create_access_token
from app.routers.auth import SESSION_COOKIE, IS_PRODUCTION
from app.utils.settings import settings
from app.utils.csrf import ensure_csrf_token

router = APIRouter()
templates = Jinja2Templates(directory="templates")
logger = logging.getLogger(__name__)


def _render_registro(request: Request, error: str | None = None, success: bool = False):
    """Renderiza la pagina de registro garantizando que el token CSRF este disponible."""
    response = templates.TemplateResponse(
        request,
        "registro.html",
        {"error": error, "success": success, "csrf_token": ""},
    )
    token = ensure_csrf_token(request, response)
    # Re-renderizar el contexto con el token correcto
    response = templates.TemplateResponse(
        request,
        "registro.html",
        {"error": error, "success": success, "csrf_token": token},
    )
    # Asegurar que la cookie viaje en esta respuesta
    ensure_csrf_token(request, response)
    return response


@router.get("")
@router.get("/")
async def registro_page(request: Request):
    if not settings.ALLOW_PUBLIC_REGISTRATION:
        return RedirectResponse(url="/seleccionar-empresa", status_code=302)
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
    return _render_registro(request)


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
    db: Session = Depends(get_db),
):
    if not settings.ALLOW_PUBLIC_REGISTRATION:
        return JSONResponse({"error": "Registro publico deshabilitado"}, status_code=403)

    from app.utils.password_policy import validar_password
    try:
        validar_password(admin_password)
    except HTTPException as e:
        return _render_registro(request, error=e.detail)
    if admin_password != admin_password2:
        return _render_registro(request, error="Las contraseñas no coinciden")

    username_clean = admin_username.strip().lower()

    existente = db.query(Usuario).filter(Usuario.username == username_clean).first()
    if existente:
        # Mensaje generico para no permitir enumeracion de usernames existentes
        return _render_registro(
            request,
            error="No se pudo completar el registro con esos datos. Revisa e intenta de nuevo.",
        )

    try:
        empresa = Empresa(
            nombre=empresa_nombre.strip(),
            nit=empresa_nit.strip() or None,
            pais=pais,
            plan="free",
            activa=True,
        )
        db.add(empresa)
        db.flush()

        config = ConfiguracionApp(
            empresa_id=empresa.id,
            empresa_nombre=empresa_nombre.strip(),
            pais=pais,
            moneda="COP" if pais == "Colombia" else "USD",
            tasa_default=20.0,
            cuotas_default=30,
        )
        db.add(config)

        zona = Zona(
            empresa_id=empresa.id,
            codigo="Z001",
            nombre="Zona Principal",
            ciudad="",
            activa=True,
        )
        db.add(zona)
        db.flush()

        admin = Usuario(
            empresa_id=empresa.id,
            username=username_clean,
            nombre=admin_nombre.strip(),
            password_hash=get_password_hash(admin_password),
            rol="admin",
            activo=True,
        )
        db.add(admin)
        db.commit()
        db.refresh(admin)

        token = create_access_token({
            "sub": str(admin.id),
            "rol": admin.rol,
            "nombre": admin.nombre,
            "empresa_id": admin.empresa_id,
        })

        response = RedirectResponse(url="/dashboard", status_code=302)
        response.set_cookie(
            key=SESSION_COOKIE,
            value=token,
            httponly=True,
            samesite="strict",
            max_age=60 * 60 * 12,
            secure=IS_PRODUCTION,
        )
        return response

    except Exception:
        db.rollback()
        logger.exception("[REGISTRO] Error creando empresa/usuario")
        return _render_registro(
            request,
            error="No se pudo crear la cuenta. Intenta nuevamente o contacta al soporte.",
        )
