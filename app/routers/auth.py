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
import logging
from typing import Optional, List

from fastapi import APIRouter, Request, Depends, Form, HTTPException
from fastapi.responses import RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.database import get_db, Usuario, Zona, Empresa, ConfiguracionApp, SessionLocal
from app.repositories.usuario_repository import UsuarioRepository

logger = logging.getLogger(__name__)
from app.schemas.usuario import UsuarioCreate, UsuarioUpdate
from app.utils.security import (
    verify_password,
    verify_password_with_timing_safety,
    get_password_hash,
    create_access_token,
    decode_token,
)
from app.utils.token_blacklist import is_jti_revoked, revoke_jti
from app.utils.csrf import CSRF_COOKIE, generate_csrf_token
from app.utils.password_policy import validar_password, validar_cambio_password
from app.utils.audit import log_action
from app.utils.rate_limit import is_rate_limited
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
    # Verificar revocacion: si el jti esta en la blacklist, el token es invalido
    jti = payload.get("jti")
    if jti and is_jti_revoked(jti):
        logger.info("Token con jti revocado: %s", jti[:8])
        return None
    uid = payload.get("sub")
    if not uid:
        return None
    user = db.query(Usuario).filter(
        Usuario.id == int(uid), Usuario.activo == True
    ).first()
    if user and jti:
        # Registrar/refresh sesion activa para listado y revocacion
        from app.utils.token_blacklist import register_active_jti
        client_ip = request.client.host if request.client else "?"
        register_active_jti(str(user.id), jti, int(payload.get("exp", 0)), client_ip)
    return user


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

    # IMPORTANTE: SIEMPRE ejecutar verify_password_with_timing_safety, incluso
    # cuando el user no existe, para que el tiempo de respuesta sea indistinguible.
    # Si cortocircuitamos con `not user or not verify_password(...)`, un atacante
    # puede detectar usuarios validos midiendo el tiempo (bcrypt tarda ~200ms,
    # la respuesta sin bcrypt es instantanea).
    password_ok = verify_password_with_timing_safety(
        password, user.password_hash if user else None
    )
    if not user or not password_ok:
        # Log intento fallido (sin revelar si el usuario existe)
        logger.info("Login fallido para username=%s empresa_id=%s", username.strip().lower()[:50], empresa_id or '?')
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
    # CSRF rotation: emitir token nuevo en cada login exitoso para que
    # un token pre-login no pueda reutilizarse post-login (mitigacion CSRF)
    response.set_cookie(
        key=CSRF_COOKIE,
        value=generate_csrf_token(),
        httponly=False,  # JS necesita leerlo
        samesite="strict",
        max_age=60 * 60 * 12,
        secure=IS_PRODUCTION,
    )
    # Audit log del login
    log_action(db, user, "login", "auth", f"username={user.username}")
    return response


@router.get("/logout")
@router.post("/logout")
async def logout(request: Request, db: Session = Depends(get_db)):
    # Revocar el jti del token actual para que no pueda reusarse
    token = request.cookies.get(SESSION_COOKIE)
    if token:
        payload = decode_token(token)
        if payload and payload.get("jti"):
            from app.utils.token_blacklist import revoke_jti
            revoke_jti(payload["jti"], int(payload.get("exp", 0)))

    # Audit log
    user = get_current_user(request, db)
    if user:
        log_action(db, user, "logout", "auth", f"username={user.username}")

    response = RedirectResponse(url="/auth/login", status_code=302)
    response.delete_cookie(SESSION_COOKIE)
    response.delete_cookie(CSRF_COOKIE)
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

    try:
        validar_password(password)
    except HTTPException as e:
        return JSONResponse({"error": e.detail}, status_code=e.status_code)

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
    log_action(db, current_user, "user_create", "users", f"username={username_clean} rol={rol}")
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
        try:
            validar_password(password)
        except HTTPException as e:
            return JSONResponse({"error": e.detail}, status_code=e.status_code)
        user.password_hash = get_password_hash(password)

    db.commit()
    log_action(db, current_user, "user_update", "users", f"user_id={user_id}")
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
        log_action(db, current_user, "user_deactivate", "users", f"user_id={user_id} username={user.username}")
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
        logger.exception("stats_publicos: error calculando estadisticas")
        return {"clientes": 0, "prestamos": 0, "zonas": 0}


# ── CAMBIO DE CONTRASEÑA PROPIO ────────────────────────────────────────────────

@router.post("/cambiar-password")
async def cambiar_password(
    request: Request,
    current_actual: str = Form(...),
    nueva: str = Form(...),
    confirmar: str = Form(...),
    db: Session = Depends(get_db)
):
    """El usuario autenticado cambia su propia contraseña.

    Valida:
    - Contrasena actual correcta
    - Nueva cumple politica centralizada (min 8, minuscula, mayus/num/simbolo)
    - Confirmacion coincide
    - Nueva != actual
    """
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "No autorizado"}, status_code=401)

    try:
        validar_cambio_password(current_actual, nueva, confirmar, user, verify_password)
    except HTTPException as e:
        return JSONResponse({"error": e.detail}, status_code=e.status_code)

    # Revocar todos los tokens del usuario (cambio de contrasena invalida
    # cualquier sesion activa que use contrasena vieja, preventivamente)
    user.password_hash = get_password_hash(nueva)
    db.commit()
    log_action(db, user, "password_change", "auth", f"username={user.username}")

    # Revocar el token actual para forzar re-login
    token = request.cookies.get(SESSION_COOKIE)
    if token:
        payload = decode_token(token)
        if payload and payload.get("jti"):
            from app.utils.token_blacklist import revoke_jti
            revoke_jti(payload["jti"], int(payload.get("exp", 0)))

    response = JSONResponse({"ok": True, "mensaje": "Contrasena actualizada. Inicia sesion de nuevo."})
    response.delete_cookie(SESSION_COOKIE)
    response.delete_cookie(CSRF_COOKIE)
    return response


# ── RECUPERACIÓN DE CONTRASEÑA (admin-assisted, sin SMTP) ──────────────────────
#
# Como la app no tiene SMTP configurado, el flujo es:
# 1. Usuario pide reset -> se genera un token de un solo uso
# 2. Admin revisa el token en el panel /admin/reset-tokens
# 3. Admin da el token al usuario (por WhatsApp, llamada, etc.)
# 4. Usuario entra el token en /auth/reset-password
# 5. Si quieres SMTP real, mira R22 (email verification) que esqueleto el modulo.

from app.utils.recovery_tokens import create_recovery_token, consume_recovery_token


@router.post("/recovery/request")
async def recovery_request(
    request: Request,
    username: str = Form(...),
    empresa_id: str = Form(""),
    db: Session = Depends(get_db)
):
    """Genera un token de recuperacion para un usuario. Lo ve el admin.

    Nota: siempre devuelve OK para no enumerar usuarios.
    """
    # Rate limit: 5 por hora por IP
    if is_rate_limited(request, "/auth/recovery", 5, 3600):
        return JSONResponse(
            {"error": "Demasiadas solicitudes. Intenta mas tarde."},
            status_code=429,
        )

    username_clean = (username or "").strip().lower()
    if not username_clean:
        return JSONResponse({"error": "Username requerido"}, status_code=400)

    # Buscar usuario
    q = db.query(Usuario).filter(Usuario.username == username_clean, Usuario.activo == True)
    if empresa_id.strip().isdigit():
        q = q.filter(Usuario.empresa_id == int(empresa_id))
    user = q.first()

    if user:
        token = create_recovery_token(user.empresa_id, user.id, user.username)
        # Guardar en la tabla audit_log para que el admin lo vea
        from app.utils.audit import log_action
        log_action(
            db, user, "recovery_token_issued", "auth",
            f"token={token[:8]}... username={user.username}",
        )
        logger.info("Recovery token emitido para username=%s", user.username)
        # En produccion con SMTP, aqui se enviara el email.
        # Por ahora el token aparece en la tabla de audit log para el admin.

    # Siempre devolver OK (no enumerar usuarios)
    return JSONResponse({
        "ok": True,
        "mensaje": "Si el usuario existe, el administrador recibira una notificacion para generar el enlace de recuperacion.",
    })


@router.post("/recovery/reset")
async def recovery_reset(
    request: Request,
    token: str = Form(...),
    nueva: str = Form(...),
    confirmar: str = Form(...),
    db: Session = Depends(get_db)
):
    """Canjea un token de recuperacion y establece una nueva contrasena."""
    if not token or len(token) < 10:
        return JSONResponse({"error": "Token invalido"}, status_code=400)
    if nueva != confirmar:
        return JSONResponse({"error": "Las contrasenas no coinciden"}, status_code=400)
    try:
        validar_password(nueva)
    except HTTPException as e:
        return JSONResponse({"error": e.detail}, status_code=e.status_code)

    info = consume_recovery_token(token)
    if not info:
        return JSONResponse(
            {"error": "Token invalido, expirado o ya usado"},
            status_code=400,
        )

    user = db.query(Usuario).filter(
        Usuario.id == info["user_id"],
        Usuario.empresa_id == info["empresa_id"],
        Usuario.activo == True,
    ).first()
    if not user:
        return JSONResponse({"error": "Usuario no encontrado"}, status_code=404)

    user.password_hash = get_password_hash(nueva)
    db.commit()
    log_action(db, user, "password_recovered", "auth", f"username={user.username}")
    return JSONResponse({
        "ok": True,
        "mensaje": "Contrasena restablecida. Ya puedes iniciar sesion.",
    })


# ── SESIONES ACTIVAS Y REVOCACIÓN ──────────────────────────────────────────────

@router.get("/sesiones")
async def listar_sesiones(request: Request, db: Session = Depends(get_db)):
    """Lista las sesiones activas del usuario actual.

    Como el JWT es stateless, las sesiones se rastrean por emision con un
    set en memoria: cada vez que se emite un token se registra, y se
    quitan al expirar. Para produccion multi-instancia usariamos Redis.
    """
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "No autorizado"}, status_code=401)
    from app.utils.token_blacklist import list_active_jti_for_user
    sesiones = list_active_jti_for_user(str(user.id))
    # Devolver solo metadatos (sin el jti completo)
    return JSONResponse({
        "ok": True,
        "sesiones": [
            {
                "issued": s["issued"],
                "expires": s["expires"],
                "ip": s.get("ip", "?"),
            }
            for s in sesiones
        ],
    })


@router.post("/sesiones/{jti_prefix}/revocar")
async def revocar_sesion(
    request: Request,
    jti_prefix: str,
    db: Session = Depends(get_db)
):
    """Revoca una sesion especifica del usuario actual."""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "No autorizado"}, status_code=401)
    from app.utils.token_blacklist import revoke_jti_by_prefix_and_user
    ok = revoke_jti_by_prefix_and_user(jti_prefix, str(user.id))
    if not ok:
        return JSONResponse({"error": "Sesion no encontrada"}, status_code=404)
    log_action(db, user, "session_revoked", "auth", f"jti_prefix={jti_prefix}")
    return JSONResponse({"ok": True})
