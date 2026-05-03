"""
Auth v2.1 - BUG FIX:
- require_admin/require_login usaban Depends() anidados que no funcionan
  con redirect → ahora cada ruta llama get_current_user directamente.
- Crear usuario redirigía al login porque require_admin lanzaba 303
  sin cookie en la respuesta del POST → corregido con verificación directa.
- TemplateResponse usa nueva firma (request, name, context).
"""
import datetime
from typing import Optional

from fastapi import APIRouter, Request, Depends, Form, HTTPException
from fastapi.responses import RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.database import get_db, Usuario, Zona, Empresa, ConfiguracionApp, SessionLocal
from app.utils.security import verify_password, get_password_hash, create_access_token, decode_token

router = APIRouter()
templates = Jinja2Templates(directory="templates")
SESSION_COOKIE = "cp_session"


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
async def login_page(request: Request, next: str = "/dashboard"):
    token = request.cookies.get(SESSION_COOKIE)
    if token and decode_token(token):
        return RedirectResponse(url=next, status_code=302)
    return templates.TemplateResponse(request, "auth/login.html", {"next": next, "error": None})


@router.post("/login")
async def login_submit(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    next: str = Form("/dashboard"),
    db: Session = Depends(get_db)
):
    user = db.query(Usuario).filter(
        Usuario.username == username.strip().lower(),
        Usuario.activo == True
    ).first()

    if not user or not verify_password(password, user.hashed_password):
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
        samesite="lax",
        max_age=60 * 60 * 12,
        secure=False,
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

    usuarios = db.query(Usuario).filter(
        Usuario.empresa_id == current_user.empresa_id
    ).order_by(Usuario.creado.desc()).all()

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
    db: Session = Depends(get_db)
):
    # BUG FIX: verificación directa, no via Depends anidado
    current_user = get_current_user(request, db)
    if not current_user:
        return JSONResponse({"error": "No autenticado"}, status_code=401)
    if current_user.rol not in ("admin", "superadmin"):
        return JSONResponse({"error": "Sin permisos"}, status_code=403)

    username_clean = username.strip().lower()
    existente = db.query(Usuario).filter(
        Usuario.empresa_id == current_user.empresa_id,
        Usuario.username == username_clean
    ).first()
    if existente:
        return JSONResponse({"error": "Ese username ya existe en tu empresa"}, status_code=400)

    if len(password) < 6:
        return JSONResponse({"error": "La contraseña debe tener al menos 6 caracteres"}, status_code=400)

    user = Usuario(
        empresa_id=current_user.empresa_id,
        username=username_clean,
        nombre=nombre.strip(),
        hashed_password=get_password_hash(password),
        rol=rol,
        zona_id=int(zona_id) if zona_id.strip() else None,
    )
    db.add(user)
    db.commit()
    return JSONResponse({"ok": True, "mensaje": f"Usuario {nombre} creado correctamente"})


@router.post("/usuarios/{user_id}/editar")
async def editar_usuario(
    request: Request,
    user_id: int,
    nombre: str = Form(...),
    rol: str = Form("cobrador"),
    zona_id: str = Form(""),
    password: str = Form(""),
    activo: str = Form("true"),
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

    user.nombre = nombre.strip()
    user.rol = rol
    user.zona_id = int(zona_id) if zona_id.strip() else None
    user.activo = activo.lower() in ("true", "1", "on")
    if password.strip():
        if len(password) < 6:
            return JSONResponse({"error": "Contraseña muy corta (min 6)"}, status_code=400)
        user.hashed_password = get_password_hash(password)

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
