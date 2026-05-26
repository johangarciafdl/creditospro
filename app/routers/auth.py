"""
Auth v2.1 - BUG FIX:
- require_admin/require_login usaban Depends() anidados que no funcionan
  con redirect → ahora cada ruta llama get_current_user directamente.
- Crear usuario redirigía al login porque require_admin lanzaba 303
  sin cookie en la respuesta del POST → corregido con verificación directa.
- TemplateResponse usa nueva firma (request, name, context).
- Cookies ahora usan secure=True en producción y samesite=strict
"""
import os
import datetime
from typing import Optional, List

from fastapi import APIRouter, Request, Depends, Form, HTTPException
from fastapi.responses import RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.database import get_db, Usuario, Zona, Empresa, ConfiguracionApp, SessionLocal
from app.repositories.usuario_repository import UsuarioRepository
from app.schemas.usuario import UsuarioCreate, UsuarioUpdate
from app.utils.security import verify_password, get_password_hash, create_access_token, decode_token
from app.utils.roles import normalize_role
from app.utils.zone_permissions import validate_user_zones

router = APIRouter()
templates = Jinja2Templates(directory="templates")
SESSION_COOKIE = "cp_session"

# Determinar si estamos en producción
IS_PRODUCTION = os.getenv("ENVIRONMENT", "production") == "production"


# ── CORE AUTH ─────────────────────────────────────────────────────────────────

def get_current_user(request: Request, db: Session) -> Optional[Usuario]:
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        return None
    payload = decode_token(token)
    if not payload:
        return None
    uid = payload.get("sub")
    if not uid:
        return None
    return db.query(Usuario).filter(
        Usuario.id == int(uid), Usuario.activo == True
    ).first()


def _require(request: Request, db: Session, roles: tuple = ()) -> Usuario:
    """Helper síncrono: obtiene usuario o lanza 401 JSON (para endpoints que usan fetch)."""
    user = get_current_user(request, db)
    if not user:
        raise HTTPException(status_code=401, detail="No autenticado")
    if roles and user.rol not in roles:
        raise HTTPException(status_code=403, detail="Sin permisos suficientes")
    return user


def _redirect_if_no_session(request: Request, db: Session, next_url: str):
    """Para rutas que renderizan HTML: redirige al login si no hay sesión."""
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url=f"/auth/login?next={next_url}", status_code=302), None
    return None, user


# ── LOGIN / LOGOUT ────────────────────────────────────────────────────────────

@router.get("/login")
async def login_page(request: Request, next: str = "/dashboard",
                     empresa_id: int = None, db: Session = Depends(get_db)):
    token = request.cookies.get(SESSION_COOKIE)
    if token and decode_token(token):
        return RedirectResponse(url=next, status_code=302)
    empresa_nombre = None
    if empresa_id:
        from app.database import Empresa
        emp = db.query(Empresa).filter(Empresa.id == empresa_id).first()
        empresa_nombre = emp.nombre if emp else None
    return templates.TemplateResponse(request, "auth/login.html", {
        "next": next, "error": None,
        "empresa_id": empresa_id, "empresa_nombre": empresa_nombre
    })


@router.post("/login")
async def login_submit(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    next: str = Form("/dashboard"),
    empresa_id: str = Form(""),
    db: Session = Depends(get_db)
):
    q = db.query(Usuario).filter(
        Usuario.username == username.strip().lower(),
        Usuario.activo == True
    )
    if empresa_id.strip().isdigit():
        q = q.filter(Usuario.empresa_id == int(empresa_id))
    user = q.first()

    if not user or not verify_password(password, user.password_hash):
        return templates.TemplateResponse(
            request, "auth/login.html",
            {"next": next, "error": "Usuario o contraseña incorrectos"},
            status_code=401
        )

    user.ultimo_login = datetime.datetime.now()
    db.commit()

    token = create_access_token({
        "sub": str(user.id),
        "rol": user.rol,
        "nombre": user.nombre,
        "empresa_id": user.empresa_id,
    })

    redirect_url = next if next.startswith("/") else "/dashboard"
    response = RedirectResponse(url=redirect_url, status_code=302)
    response.set_cookie(
        key=SESSION_COOKIE,
        value=token,
        httponly=True,
        samesite="strict",
        max_age=60 * 60 * 12,
        secure=IS_PRODUCTION,
    )
    return response


@router.get("/logout")
async def logout():
    response = RedirectResponse(url="/auth/login", status_code=302)
    response.delete_cookie(SESSION_COOKIE)
    return response


# ── GESTIÓN DE USUARIOS ───────────────────────────────────────────────────────

@router.get("/usuarios")
async def listar_usuarios(request: Request, db: Session = Depends(get_db)):
    redir, current_user = _redirect_if_no_session(request, db, "/auth/usuarios")
    if redir:
        return redir
    if current_user.rol not in ("admin", "superadmin"):
        raise HTTPException(status_code=403)

    usuarios = UsuarioRepository(db).list_by_empresa(current_user.empresa_id)

    zonas = db.query(Zona).filter(Zona.empresa_id == current_user.empresa_id).all()

    return templates.TemplateResponse(request, "auth/usuarios.html", {
        "page": "usuarios",
        "usuarios": usuarios,
        "zonas": zonas,
        "current_user": current_user,
    })


@router.post("/usuarios/nuevo")
async def crear_usuario(
    request: Request,
    username: str = Form(...),
    nombre: str = Form(...),
    password: str = Form(...),
    rol: str = Form("cobrador"),
    zona_id: str = Form(""),
    zona_ids: List[str] = Form([]),
    db: Session = Depends(get_db)
):
    # BUG FIX: verificación directa, no via Depends anidado
    current_user = get_current_user(request, db)
    if not current_user:
        return JSONResponse({"error": "No autenticado"}, status_code=401)
    if current_user.rol not in ("admin", "superadmin"):
        return JSONResponse({"error": "Sin permisos"}, status_code=403)

    try:
        rol = normalize_role(rol)
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)

    username_clean = username.strip().lower()
    if not username_clean or len(username_clean) > 100:
        return JSONResponse({"error": "Username invalido"}, status_code=400)
    nombre_clean = nombre.strip()
    if not nombre_clean or len(nombre_clean) > 200:
        return JSONResponse({"error": "Nombre invalido"}, status_code=400)
    existente = db.query(Usuario).filter(
        Usuario.empresa_id == current_user.empresa_id,
        Usuario.username == username_clean
    ).first()
    if existente:
        return JSONResponse({"error": "Ese username ya existe en tu empresa"}, status_code=400)

    if len(password) < 6:
        return JSONResponse({"error": "La contraseña debe tener al menos 6 caracteres"}, status_code=400)

    selected_zone_ids = [int(z) for z in zona_ids if str(z).strip().isdigit()]
    if not selected_zone_ids and zona_id.strip().isdigit():
        selected_zone_ids = [int(zona_id)]
    try:
        zonas_asignadas = validate_user_zones(db, current_user.empresa_id, selected_zone_ids)
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)
    if rol in ("cobrador", "supervisor") and not zonas_asignadas:
        return JSONResponse({"error": "Asigna minimo 1 zona"}, status_code=400)

    user = Usuario(
        empresa_id=current_user.empresa_id,
        username=username_clean,
        nombre=nombre_clean,
        password_hash=get_password_hash(password),
        rol=rol,
        zona_id=zonas_asignadas[0].id if zonas_asignadas else None,
    )
    user.zonas_asignadas = zonas_asignadas
    db.add(user)
    db.commit()
    return JSONResponse({"ok": True, "mensaje": f"Usuario {nombre_clean} creado correctamente"})


@router.post("/usuarios/{user_id}/editar")
async def editar_usuario(
    request: Request,
    user_id: int,
    nombre: str = Form(...),
    rol: str = Form("cobrador"),
    zona_id: str = Form(""),
    password: str = Form(""),
    activo: str = Form("true"),
    zona_ids: List[str] = Form([]),
    db: Session = Depends(get_db)
):
    current_user = get_current_user(request, db)
    if not current_user or current_user.rol not in ("admin", "superadmin"):
        return JSONResponse({"error": "Sin permisos"}, status_code=403)

    user = db.query(Usuario).filter(
        Usuario.id == user_id,
        Usuario.empresa_id == current_user.empresa_id
    ).first()
    if not user:
        return JSONResponse({"error": "Usuario no encontrado"}, status_code=404)

    try:
        rol = normalize_role(rol)
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)

    nombre_clean = nombre.strip()
    if not nombre_clean or len(nombre_clean) > 200:
        return JSONResponse({"error": "Nombre invalido"}, status_code=400)

    selected_zone_ids = [int(z) for z in zona_ids if str(z).strip().isdigit()]
    if not selected_zone_ids and zona_id.strip().isdigit():
        selected_zone_ids = [int(zona_id)]
    try:
        zonas_asignadas = validate_user_zones(db, current_user.empresa_id, selected_zone_ids)
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)
    if rol in ("cobrador", "supervisor") and not zonas_asignadas:
        return JSONResponse({"error": "Asigna minimo 1 zona"}, status_code=400)

    user.nombre = nombre_clean
    user.rol = rol
    user.zona_id = zonas_asignadas[0].id if zonas_asignadas else None
    user.zonas_asignadas = zonas_asignadas
    user.activo = activo.lower() in ("true", "1", "on")
    if password.strip():
        if len(password) < 6:
            return JSONResponse({"error": "Contraseña muy corta (min 6)"}, status_code=400)
        user.password_hash = get_password_hash(password)

    db.commit()
    return JSONResponse({"ok": True, "mensaje": "Usuario actualizado"})


@router.delete("/usuarios/{user_id}")
async def eliminar_usuario(
    request: Request,
    user_id: int,
    db: Session = Depends(get_db)
):
    current_user = get_current_user(request, db)
    if not current_user or current_user.rol not in ("admin", "superadmin"):
        return JSONResponse({"error": "Sin permisos"}, status_code=403)
    if user_id == current_user.id:
        return JSONResponse({"error": "No puedes desactivarte a ti mismo"}, status_code=400)

    user = db.query(Usuario).filter(
        Usuario.id == user_id,
        Usuario.empresa_id == current_user.empresa_id
    ).first()
    if user:
        user.activo = False
        db.commit()
    return JSONResponse({"ok": True})
@router.get("/stats")
async def stats_publicos(request: Request, db: Session = Depends(get_db)):
    """Stats públicos para la pantalla de login — filtrados por empresa si hay sesión."""
    try:
        from sqlalchemy import func
        from app.database import Cliente, Prestamo, Zona

        # Intentar obtener empresa del usuario logueado
        from app.routers.auth import get_current_user
        user = get_current_user(request, db)
        if not user:
            return {"clientes": 0, "prestamos": 0, "zonas": 0}
        empresa_id = user.empresa_id

        q_clientes = db.query(func.count(Cliente.id))
        q_prestamos = db.query(func.count(Prestamo.id))
        q_zonas = db.query(func.count(Zona.id))

        if empresa_id:
            q_clientes = q_clientes.filter(Cliente.empresa_id == empresa_id)
            q_prestamos = q_prestamos.filter(Prestamo.empresa_id == empresa_id)
            q_zonas = q_zonas.filter(Zona.empresa_id == empresa_id)

        clientes = q_clientes.scalar() or 0
        prestamos = q_prestamos.scalar() or 0
        zonas = q_zonas.scalar() or 0
        return {"clientes": clientes, "prestamos": prestamos, "zonas": zonas}
    except Exception:
        return {"clientes": 0, "prestamos": 0, "zonas": 0}
