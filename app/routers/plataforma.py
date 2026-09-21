"""Panel del dueno de la plataforma: gestion de plan comercial por empresa.

Estrictamente superadmin -- ni siquiera un admin de una empresa individual
puede ver ni tocar esto. Usa get_db_system (conexion privilegiada) porque
por definicion necesita ver TODAS las empresas, no solo la del usuario
actual -- el unico caso legitimo de acceso cross-empresa junto con el
scheduler, la activacion de licencia y el selector de empresa.
"""
import datetime
import logging
import secrets
import time

from fastapi import APIRouter, Request, Depends, Form, HTTPException
from fastapi.responses import JSONResponse, RedirectResponse, Response
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.database import (
    get_db_system, AuditLog, Cobro, Empresa, SesionJWT, Usuario, ConfiguracionApp, Zona,
    hoy_local,
)
from app.routers.auth import get_current_user, SESSION_COOKIE, IS_PRODUCTION
from app.templates import templates
from app.utils.audit import log_action
from app.utils.company_activation import (
    assign_company_key,
    is_valid_key_format,
    normalize_company_key,
)
from app.utils.csrf import CSRF_COOKIE, generate_csrf_token
from app.utils.password_policy import validar_password
from app.utils.plan_limits import PLANES_VALIDOS
from app.utils import estado_sistema, metricas, token_blacklist
from app.utils.rate_limit import estado as rate_limit_estado, is_rate_limited
from app.utils.security import (
    activation_key_hash,
    create_access_token,
    decrypt_secret,
    encrypt_secret,
    get_password_hash,
    verify_password_with_timing_safety,
)

router = APIRouter()

logger = logging.getLogger(__name__)


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

    # 1 consulta agrupada en vez de 1 por empresa (N+1).
    cobradores_por_empresa = dict(
        db.query(Usuario.empresa_id, func.count(Usuario.id))
        .filter(Usuario.rol.in_(("cobrador", "supervisor")), Usuario.activo == True)
        .group_by(Usuario.empresa_id).all()
    )

    data = []
    for e in empresas:
        overrides = e.overrides or {}
        data.append({
            "id": e.id, "nombre": e.nombre, "plan": e.plan or "basico",
            "activa": e.activa, "cobradores_activos": cobradores_por_empresa.get(e.id, 0),
            "tiene_clave": bool(e.activation_key_hash),
            "clave_visible": bool(e.activation_key_encrypted),
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


@router.get("/empresas/{empresa_id}/clave")
async def ver_clave(
    request: Request, empresa_id: int,
    db: Session = Depends(get_db_system)
):
    user = _requiere_superadmin(request, db)
    if not user:
        return JSONResponse({"error": "Sin permisos"}, status_code=403)

    empresa = db.query(Empresa).filter(Empresa.id == empresa_id).first()
    if not empresa:
        return JSONResponse({"error": "Empresa no encontrada"}, status_code=404)
    if not empresa.activation_key_encrypted:
        return JSONResponse({"error": "Esta empresa no tiene una clave para mostrar"}, status_code=404)

    clave = decrypt_secret(empresa.activation_key_encrypted)
    if not clave:
        # La copia legible se cifra con SECRET_KEY. Si esa clave se rota, las
        # copias anteriores dejan de descifrarse -- la activacion sigue
        # funcionando, porque eso va por hash, pero el superadmin ya no puede
        # volver a leerlas. Antes se respondia "genera una nueva", que invalida
        # la clave en uso y obliga al cliente a reactivar. Casi siempre la
        # clave no se ha perdido: esta en manos del cliente, y basta con
        # volver a guardarla.
        return JSONResponse(
            {"error": "La copia legible de esta clave se cifro con una SECRET_KEY "
                      "anterior y ya no se puede descifrar. La clave sigue siendo "
                      "valida: si la tienes, usa \"Restaurar copia\" para volver a "
                      "guardarla sin invalidarla.",
             "recuperable": True,
             "hint": empresa.activation_key_hint},
            status_code=409,
        )

    log_action(db, user, "empresa_clave_ver", "empresas", f"empresa_id={empresa_id}")
    return JSONResponse({"ok": True, "clave": clave})


@router.get("/respaldos")
async def listar_copias(request: Request, db: Session = Depends(get_db_system)):
    """Las copias de seguridad disponibles."""
    user = _requiere_superadmin(request, db)
    if not user:
        return JSONResponse({"error": "Sin permisos"}, status_code=403)
    from app.services.respaldo import DIAS_A_CONSERVAR, listar_respaldos
    from app.utils import supabase_storage

    return JSONResponse({
        "ok": True,
        "configurado": supabase_storage.disponible(),
        "conserva_dias": DIAS_A_CONSERVAR,
        "respaldos": listar_respaldos(),
    })


@router.post("/respaldos/ahora")
async def respaldar_ahora(request: Request, db: Session = Depends(get_db_system)):
    """Lanza una copia en el momento, sin esperar a la de la madrugada."""
    user = _requiere_superadmin(request, db)
    if not user:
        return JSONResponse({"error": "Sin permisos"}, status_code=403)
    from app.services.respaldo import crear_respaldo

    try:
        resumen = crear_respaldo(db)
    except Exception as e:
        logger.exception("Respaldo manual fallido")
        return JSONResponse({"error": str(e)[:300]}, status_code=500)
    log_action(db, user, "respaldo_manual", "sistema", resumen["nombre"])
    db.commit()
    return JSONResponse({"ok": True, **resumen})


@router.get("/respaldos/{nombre}")
async def descargar_copia(request: Request, nombre: str,
                          db: Session = Depends(get_db_system)):
    """Baja una copia al equipo del dueno.

    Es lo que convierte esto en un respaldo de verdad: la copia vive en el
    mismo proyecto de Supabase que la base, asi que protege de un borrado
    por error pero no de perder la cuenta entera. Bajarse una de vez en
    cuando cubre ese hueco.
    """
    user = _requiere_superadmin(request, db)
    if not user:
        return JSONResponse({"error": "Sin permisos"}, status_code=403)
    from app.services.respaldo import descargar_respaldo

    datos = descargar_respaldo(nombre)
    if datos is None:
        return JSONResponse({"error": "No se encontro esa copia"}, status_code=404)
    log_action(db, user, "respaldo_descarga", "sistema", nombre)
    db.commit()
    return Response(
        content=datos,
        media_type="application/gzip",
        headers={"Content-Disposition": f'attachment; filename="{nombre}"'},
    )


@router.post("/empresas/{empresa_id}/clave/restaurar")
async def restaurar_copia_clave(
    request: Request, empresa_id: int,
    clave: str = Form(...),
    db: Session = Depends(get_db_system)
):
    """Vuelve a guardar la copia legible de una clave que sigue en uso.

    No genera nada ni cambia el hash: solo comprueba que la clave escrita es
    de verdad la de esta empresa y, si lo es, guarda su copia cifrada con la
    SECRET_KEY actual. Sirve para el caso en que se roto SECRET_KEY y las
    copias viejas quedaron ilegibles, sin obligar al cliente a reactivar con
    una clave nueva.

    La comprobacion es contra el hash, que es la misma que usa la activacion:
    una clave equivocada no puede colarse.
    """
    user = _requiere_superadmin(request, db)
    if not user:
        return JSONResponse({"error": "Sin permisos"}, status_code=403)

    empresa = db.query(Empresa).filter(Empresa.id == empresa_id).first()
    if not empresa:
        return JSONResponse({"error": "Empresa no encontrada"}, status_code=404)
    if not empresa.activation_key_hash:
        return JSONResponse(
            {"error": "Esta empresa no tiene clave asignada; genera una."}, status_code=404)

    escrita = normalize_company_key(clave)
    if not is_valid_key_format(escrita):
        return JSONResponse({"error": "El formato de la clave no es valido"}, status_code=400)
    if not secrets.compare_digest(activation_key_hash(escrita), empresa.activation_key_hash):
        log_action(db, user, "empresa_clave_restaurar_fallida", "empresas",
                   f"empresa_id={empresa_id}")
        db.commit()
        return JSONResponse(
            {"error": "Esa no es la clave de esta empresa."}, status_code=400)

    empresa.activation_key_encrypted = encrypt_secret(escrita)
    empresa.activation_key_hint = f"...{escrita[-8:]}"
    db.commit()
    log_action(db, user, "empresa_clave_restaurar", "empresas", f"empresa_id={empresa_id}")
    db.commit()
    return JSONResponse({
        "ok": True,
        "mensaje": "Copia restaurada. La clave sigue siendo la misma y no hubo que reactivar.",
        "hint": empresa.activation_key_hint,
    })


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


def _como_fecha(valor):
    """Cobro.fecha es un Date, pero segun el motor puede llegar como
    datetime. Normalizar evita el AttributeError de llamar .date() sobre un
    date, que es lo que tumbaba esta pantalla con un 500."""
    if valor is None:
        return None
    return valor.date() if hasattr(valor, "date") else valor


@router.get("/monitoreo")
async def panel_monitoreo(request: Request, db: Session = Depends(get_db_system)):
    """Estado tecnico de toda la plataforma.

    Responde las preguntas que antes solo se podian contestar entrando a
    los logs del proveedor: que version esta desplegada, si la base de
    datos va bien y cuanta capacidad queda, que rutas van lentas o estan
    fallando, y si hay empresas que dejaron de operar.
    """
    user = _requiere_superadmin(request, db)
    if not user:
        destino = "/plataforma/login" if not get_current_user(request, db) else "/dashboard"
        return RedirectResponse(url=destino, status_code=302)

    hoy = hoy_local()
    hace_24h = datetime.datetime.now() - datetime.timedelta(hours=24)

    # Actividad real del negocio, leida de la base de datos: estas cifras si
    # son exactas y sobreviven a un reinicio, a diferencia de las metricas
    # del proceso.
    actividad = []
    cobros_por_empresa = dict(
        db.query(Cobro.empresa_id, func.count(Cobro.id))
        .filter(func.date(Cobro.fecha) == hoy)
        .group_by(Cobro.empresa_id).all()
    )
    ultimo_cobro = dict(
        db.query(Cobro.empresa_id, func.max(Cobro.fecha))
        .group_by(Cobro.empresa_id).all()
    )
    for e in db.query(Empresa).order_by(Empresa.nombre).all():
        ultimo = _como_fecha(ultimo_cobro.get(e.id))
        dias_sin_cobrar = (hoy - ultimo).days if ultimo else None
        actividad.append({
            "nombre": e.nombre,
            "activa": e.activa,
            "cobros_hoy": cobros_por_empresa.get(e.id, 0),
            "ultimo_cobro": ultimo.strftime("%d/%m/%Y") if ultimo else "nunca",
            # Una empresa que lleva dias sin registrar un cobro puede estar
            # de vacaciones o puede tener la aplicacion rota; conviene verlo.
            "dias_sin_cobrar": dias_sin_cobrar,
        })

    # Acciones sensibles de las ultimas 24 horas, por categoria.
    auditoria = [
        {"categoria": c, "veces": n}
        for c, n in db.query(AuditLog.category, func.count(AuditLog.id))
        .filter(AuditLog.created_at >= hace_24h)
        .group_by(AuditLog.category)
        .order_by(func.count(AuditLog.id).desc())
        .all()
    ]

    sesiones_activas = 0
    try:
        sesiones_activas = (
            db.query(func.count(SesionJWT.jti))
            .filter(SesionJWT.revocada.is_(False), SesionJWT.expira_en > int(time.time()))
            .scalar() or 0
        )
    except Exception:
        pass

    return templates.TemplateResponse(request, "plataforma_monitoreo.html", {
        "page": "plataforma",
        "current_user": user,
        "sistema": estado_sistema.detalle(),
        "proceso": metricas.resumen(),
        "actividad": actividad,
        "auditoria": auditoria,
        "sesiones_activas": sesiones_activas,
        "sesiones": token_blacklist.estado(),
        "limite_peticiones": rate_limit_estado(),
    })
