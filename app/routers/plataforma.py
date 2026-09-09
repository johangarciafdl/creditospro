"""Panel del dueno de la plataforma: gestion de plan comercial por empresa.

Estrictamente superadmin -- ni siquiera un admin de una empresa individual
puede ver ni tocar esto. Usa get_db_system (conexion privilegiada) porque
por definicion necesita ver TODAS las empresas, no solo la del usuario
actual -- el unico caso legitimo de acceso cross-empresa junto con el
scheduler, la activacion de licencia y el selector de empresa.
"""
from fastapi import APIRouter, Request, Depends, Form
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.database import get_db_system, Empresa, Usuario
from app.routers.auth import get_current_user
from app.templates import templates
from app.utils.audit import log_action
from app.utils.plan_limits import PLANES_VALIDOS

router = APIRouter()


def _requiere_superadmin(request: Request, db: Session):
    user = get_current_user(request, db)
    if not user or user.rol != "superadmin":
        return None
    return user


@router.get("")
@router.get("/")
async def panel_plataforma(request: Request, db: Session = Depends(get_db_system)):
    user = _requiere_superadmin(request, db)
    if not user:
        return RedirectResponse(url="/dashboard", status_code=302)

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
