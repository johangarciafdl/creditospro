"""License router - endpoints para activacion y verificacion"""
import logging
from pathlib import Path

from fastapi import APIRouter, Request, Form, Depends
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.database import get_db, LicenciaActivada
from app.utils.settings import settings

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
    lm = get_license_manager()
    if not lm:
        return JSONResponse({"valid": False, "error": "Sistema de licencias no disponible"})
    result = lm.save_license(license_key)
    if result.get("valid"):
        machine_id = result.get("machine_id", "")
        empresa_id = result.get("empresa_id")
        existing = db.query(LicenciaActivada).filter(
            LicenciaActivada.machine_id == machine_id
        ).first()
        if existing:
            existing.license_key = license_key.strip()
            existing.empresa_id = empresa_id
            existing.activa = True
        else:
            lic = LicenciaActivada(
                empresa_id=empresa_id,
                machine_id=machine_id,
                license_key=license_key.strip(),
                activa=True,
            )
            db.add(lic)
        db.commit()
    request.app.state.license_valid = result.get("valid", False)
    request.app.state.license_info = result
    return JSONResponse(result)


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
