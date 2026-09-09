"""Panel del dueno de la plataforma: gestion de plan comercial por empresa.

Estrictamente superadmin -- ni siquiera un admin de una empresa individual
puede ver ni tocar esto. Usa get_db_system (conexion privilegiada) porque
por definicion necesita ver TODAS las empresas, no solo la del usuario
actual -- el unico caso legitimo de acceso cross-empresa junto con el
scheduler, la activacion de licencia y el selector de empresa.
"""
from fastapi import APIRouter, Request, Depends, Form, HTTPException
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.database import get_db_system, Empresa, Usuario, ConfiguracionApp, Zona
from app.routers.auth import get_current_user, SESSION_COOKIE, IS_PRODUCTION
from app.templates import templates
from app.utils.audit import log_action
from app.utils.company_activation import assign_company_key
from app.utils.csrf import CSRF_COOKIE, generate_csrf_token
from app.utils.password_policy import validar_password
from app.utils.plan_limits import PLANES_VALIDOS
from app.utils.rate_limit import is_rate_limited
from app.utils.security import (
    create_access_token,
    get_password_hash,
    verify_password_with_timing_safety,
)

router = APIRouter()


def _requiere_superadmin(request: Request, db: Session):
    user = get_current_user(request, db)
    if not user or user.rol != "superadmin":
        return None
    return user


@router.get("/login")
async def plataforma_login_page(request: Request, db: Session = Depends(get_db_system)):
    if _requiere_superadmin(request, db):
        return RedirectResponse(url="/plataforma", status_code=302)
    return templates.TemplateResponse(request, "plataforma_login.html", {"error": None})


@router.post("/login")
async def plataforma_login_submit(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db_system),
):
    username_clean = username.strip().lower()
    if is_rate_limited(request, "/plataforma/login", 10, 900, key_suffix=f":{username_clean}"):
        return templates.TemplateResponse(
            request, "plataforma_login.html",
            {"error": "Demasiados intentos. Intenta mas tarde."}, status_code=429,
        )

    user = db.query(Usuario).filter(
        Usuario.username == username_clean,
        Usuario.rol == "superadmin",
        Usuario.empresa_id.is_(None),
        Usuario.activo == True,
    ).first()

    # Timing-safe incluso si el usuario no existe -- ver login_submit en auth.py.
    password_ok = verify_password_with_timing_safety(password, user.password_hash if user else None)
    if not user or not password_ok:
        return templates.TemplateResponse(
            request, "plataforma_login.html",
            {"error": "Usuario o contraseña incorrectos"}, status_code=401,
        )

    token = create_access_token({
        "sub": str(user.id), "rol": user.rol, "nombre": user.nombre, "empresa_id": None,
    })
    response = RedirectResponse(url="/plataforma", status_code=302)
    response.set_cookie(
        key=SESSION_COOKIE, value=token, httponly=True, samesite="strict",
        max_age=60 * 60 * 12, secure=IS_PRODUCTION,
    )
    response.set_cookie(
        key=CSRF_COOKIE, value=generate_csrf_token(), httponly=False, samesite="strict",
        max_age=60 * 60 * 12, secure=IS_PRODUCTION,
    )
    log_action(db, user, "login", "plataforma", f"username={user.username}")
    return response


@router.get("")
@router.get("/")
async def panel_plataforma(request: Request, db: Session = Depends(get_db_system)):
    user = _requiere_superadmin(request, db)
    if not user:
        destino = "/plataforma/login" if not get_current_user(request, db) else "/dashboard"
        return RedirectResponse(url=destino, status_code=302)

    empresas = db.query(Empresa).order_by(Empresa.nombre).all()
    data = []
    for e in empresas:
        cobradores_activos = db.query(Usuario).filter(
            Usuario.empresa_id == e.id,
            Usuario.rol.in_(("cobrador", "supervisor")),
            Usuario.activo == True,
        ).count()
        overrides = e.overrides or {}
        data.append({
            "id": e.id, "nombre": e.nombre, "plan": e.plan or "basico",
            "activa": e.activa, "cobradores_activos": cobradores_activos,
            "tiene_clave": bool(e.activation_key_hash),
            "override_whatsapp": overrides.get("whatsapp"),
            "override_max_cobradores": overrides.get("max_cobradores"),
        })

    return templates.TemplateResponse(request, "plataforma.html", {
        "page": "plataforma", "empresas": data, "current_user": user,
        "planes_validos": PLANES_VALIDOS,
    })


@router.post("/empresas/{empresa_id}/plan")
async def cambiar_plan(
    request: Request, empresa_id: int,
    plan: str = Form(...),
    db: Session = Depends(get_db_system)
):
    user = _requiere_superadmin(request, db)
    if not user:
        return JSONResponse({"error": "Sin permisos"}, status_code=403)

    if plan not in PLANES_VALIDOS:
        return JSONResponse({"error": f"Plan invalido. Usa: {', '.join(PLANES_VALIDOS)}"}, status_code=400)

    empresa = db.query(Empresa).filter(Empresa.id == empresa_id).first()
    if not empresa:
        return JSONResponse({"error": "Empresa no encontrada"}, status_code=404)

    plan_anterior = empresa.plan
    empresa.plan = plan
    db.commit()
    log_action(db, user, "plan_change", "empresas", f"empresa_id={empresa_id} {plan_anterior}->{plan}")
    return JSONResponse({"ok": True, "mensaje": f"Plan de {empresa.nombre} actualizado a {plan}"})


@router.post("/empresas/{empresa_id}/overrides")
async def cambiar_overrides(
    request: Request, empresa_id: int,
    whatsapp: str = Form(""),  # "heredar" | "activar" | "desactivar"
    max_cobradores: str = Form(""),  # "" = heredar del plan, o un numero
    db: Session = Depends(get_db_system)
):
    user = _requiere_superadmin(request, db)
    if not user:
        return JSONResponse({"error": "Sin permisos"}, status_code=403)

    empresa = db.query(Empresa).filter(Empresa.id == empresa_id).first()
    if not empresa:
        return JSONResponse({"error": "Empresa no encontrada"}, status_code=404)

    overrides = dict(empresa.overrides or {})

    if whatsapp == "activar":
        overrides["whatsapp"] = True
    elif whatsapp == "desactivar":
        overrides["whatsapp"] = False
    else:
        overrides.pop("whatsapp", None)

    max_cobradores = max_cobradores.strip()
    if max_cobradores.isdigit():
        overrides["max_cobradores"] = int(max_cobradores)
    else:
        overrides.pop("max_cobradores", None)

    empresa.overrides = overrides or None
    db.commit()
    log_action(db, user, "plan_override_change", "empresas", f"empresa_id={empresa_id} overrides={overrides}")
    return JSONResponse({"ok": True, "mensaje": f"Excepciones de {empresa.nombre} actualizadas"})


@router.post("/empresas/{empresa_id}/activa")
async def cambiar_activa(
    request: Request, empresa_id: int,
    activa: str = Form(...),
    db: Session = Depends(get_db_system)
):
    user = _requiere_superadmin(request, db)
    if not user:
        return JSONResponse({"error": "Sin permisos"}, status_code=403)

    empresa = db.query(Empresa).filter(Empresa.id == empresa_id).first()
    if not empresa:
        return JSONResponse({"error": "Empresa no encontrada"}, status_code=404)

    empresa.activa = activa.lower() in ("true", "1", "on")
    db.commit()
    log_action(db, user, "empresa_activa_change", "empresas", f"empresa_id={empresa_id} activa={empresa.activa}")
    verbo = "habilitada" if empresa.activa else "inhabilitada"
    return JSONResponse({"ok": True, "mensaje": f"{empresa.nombre} {verbo}"})


@router.post("/empresas/{empresa_id}/clave")
async def generar_clave(
    request: Request, empresa_id: int,
    rotar: str = Form("false"),
    db: Session = Depends(get_db_system)
):
    user = _requiere_superadmin(request, db)
    if not user:
        return JSONResponse({"error": "Sin permisos"}, status_code=403)

    empresa = db.query(Empresa).filter(Empresa.id == empresa_id).first()
    if not empresa:
        return JSONResponse({"error": "Empresa no encontrada"}, status_code=404)

    rotar_bool = rotar.lower() in ("true", "1", "on")
    if empresa.activation_key_hash and not rotar_bool:
        return JSONResponse(
            {"error": "Esta empresa ya tiene una clave activa. Confirma para rotarla (invalida la anterior)."},
            status_code=409,
        )

    clave = assign_company_key(db, empresa)
    db.commit()
    log_action(db, user, "empresa_clave_change", "empresas", f"empresa_id={empresa_id} rotada={rotar_bool}")
    return JSONResponse({"ok": True, "clave": clave, "hint": empresa.activation_key_hint})


@router.post("/empresas/nueva")
async def crear_empresa(
    request: Request,
    empresa_nombre: str = Form(...),
    empresa_nit: str = Form(""),
    pais: str = Form("Colombia"),
    admin_nombre: str = Form(...),
    admin_username: str = Form(...),
    admin_password: str = Form(...),
    db: Session = Depends(get_db_system)
):
    user = _requiere_superadmin(request, db)
    if not user:
        return JSONResponse({"error": "Sin permisos"}, status_code=403)

    empresa_nombre_clean = empresa_nombre.strip()
    if not empresa_nombre_clean or len(empresa_nombre_clean) > 200:
        return JSONResponse({"error": "Nombre de empresa invalido"}, status_code=400)

    username_clean = admin_username.strip().lower()
    if not username_clean or len(username_clean) > 100:
        return JSONResponse({"error": "Username invalido"}, status_code=400)
    admin_nombre_clean = admin_nombre.strip()
    if not admin_nombre_clean or len(admin_nombre_clean) > 200:
        return JSONResponse({"error": "Nombre de administrador invalido"}, status_code=400)

    # Mismo chequeo que usa el registro publico (/registro): username unico
    # en toda la plataforma, no solo dentro de la empresa nueva.
    existente = db.query(Usuario).filter(Usuario.username == username_clean).first()
    if existente:
        return JSONResponse({"error": "Ese username ya existe en otra empresa"}, status_code=400)

    try:
        validar_password(admin_password)
    except HTTPException as e:
        return JSONResponse({"error": e.detail}, status_code=e.status_code)

    try:
        empresa = Empresa(
            nombre=empresa_nombre_clean,
            nit=empresa_nit.strip() or None,
            pais=pais,
            plan="basico",
            activa=True,
        )
        db.add(empresa)
        db.flush()

        config = ConfiguracionApp(
            empresa_id=empresa.id,
            empresa_nombre=empresa_nombre_clean,
            pais=pais,
            moneda="COP" if pais == "Colombia" else "USD",
        )
        db.add(config)

        zona = Zona(empresa_id=empresa.id, codigo="Z001", nombre="Zona Principal", activa=True)
        db.add(zona)

        admin = Usuario(
            empresa_id=empresa.id,
            username=username_clean,
            nombre=admin_nombre_clean,
            password_hash=get_password_hash(admin_password),
            rol="admin",
            activo=True,
        )
        db.add(admin)
        db.flush()

        clave = assign_company_key(db, empresa)
        db.commit()
        log_action(db, user, "empresa_create", "empresas", f"empresa_id={empresa.id} nombre={empresa_nombre_clean}")

        return JSONResponse({
            "ok": True,
            "empresa_id": empresa.id,
            "clave": clave,
            "mensaje": f"Empresa {empresa_nombre_clean} creada, con zona inicial y usuario administrador",
        })
    except Exception:
        db.rollback()
        return JSONResponse({"error": "No se pudo crear la empresa. Intenta de nuevo."}, status_code=500)
