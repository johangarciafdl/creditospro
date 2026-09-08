"""License router - activacion de la clave comercial por empresa"""
import logging

from fastapi import APIRouter, Request, Form, Depends
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.database import get_db_system, Empresa
from app.utils.company_activation import (
    clear_failed_activation,
    get_retry_after,
    is_valid_key_format,
    normalize_company_key,
    register_failed_activation,
)
from app.utils.security import activation_key_hash

router = APIRouter()
templates = Jinja2Templates(directory="templates")
logger = logging.getLogger(__name__)


@router.post("/activate")
async def activate(request: Request, license_key: str = Form(...), db: Session = Depends(get_db_system)):
    client_ip = request.client.host if request.client else "unknown"
    retry_after = get_retry_after(client_ip)
    if retry_after:
        return JSONResponse(
            {"valid": False, "error": "Espera antes de volver a intentar.", "retry_after": retry_after},
            status_code=429,
            headers={"Retry-After": str(retry_after)},
        )

    key = normalize_company_key(license_key)
    if not is_valid_key_format(key):
        register_failed_activation(client_ip)
        return JSONResponse(
            {"valid": False, "error": "Clave de activacion invalida.", "retry_after": 30},
            status_code=401,
        )

    empresa = db.query(Empresa).filter(
        Empresa.activation_key_hash == activation_key_hash(key),
        Empresa.activation_enabled == True,
        Empresa.activa == True,
    ).first()
    if not empresa:
        register_failed_activation(client_ip)
        return JSONResponse(
            {"valid": False, "error": "Clave de activacion invalida.", "retry_after": 30},
            status_code=401,
        )

    clear_failed_activation(client_ip)
    request.session["activated_empresa_id"] = empresa.id
    request.session["activated_at"] = __import__("time").time()
    logger.info("Empresa activada para sesion: empresa_id=%s ip=%s", empresa.id, client_ip)
    return JSONResponse({
        "valid": True,
        "empresa_id": empresa.id,
        "empresa_nombre": empresa.nombre,
        "key_hint": empresa.activation_key_hint,
        "redirect": f"/auth/login?empresa_id={empresa.id}",
    })


@router.get("/status")
async def license_status(request: Request):
    return JSONResponse({"valid": bool(request.session.get("activated_empresa_id"))})


@router.get("/activar")
async def activar_page(request: Request):
    if request.session.get("activated_empresa_id"):
        return RedirectResponse("/", 302)
    return templates.TemplateResponse(request, "activacion.html", {})
