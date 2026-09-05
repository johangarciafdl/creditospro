"""License router - endpoints para activacion y verificacion"""
import logging
from pathlib import Path

from fastapi import APIRouter, Request, Form, Depends
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.database import get_db, LicenciaActivada, Empresa
from app.utils.settings import settings
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


def get_license_manager():
    try:
        import sys
        root_dir = Path(__file__).resolve().parents[2]
        if str(root_dir) not in sys.path:
            sys.path.insert(0, str(root_dir))
        import license_manager
        return license_manager
    except ImportError:
        logger.warning("license_manager.py no esta disponible")
        return None
    except Exception:
        logger.exception("Error cargando license_manager")
        return None


@router.get("/machine-id")
async def get_machine_id():
    lm = get_license_manager()
    if not lm:
        return JSONResponse({"machine_id": "ERROR-LM-NOT-FOUND"})
    return JSONResponse({"machine_id": lm.get_fingerprint()})


@router.post("/activate")
async def activate(request: Request, license_key: str = Form(...), db: Session = Depends(get_db)):
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
async def license_status():
    lm = get_license_manager()
    if not lm:
        return JSONResponse({"valid": settings.ENVIRONMENT == "development", "dev_mode": True})
    return JSONResponse(lm.check_license())


@router.get("/activar")
async def activar_page(request: Request):
    lm = get_license_manager()
    status = lm.check_license() if lm else {"valid": settings.ENVIRONMENT == "development"}
    if status.get("valid"):
        return RedirectResponse("/", 302)
    return templates.TemplateResponse(request, "activacion.html", {})
