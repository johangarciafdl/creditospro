"""Middleware que bloquea el sistema si la licencia es inválida.

Verifica en 3 niveles:
1. app.state.license_valid (cache en memoria)
2. license.key archivo local
3. CREDITOSPRO_LICENSE_KEY env var
4. Tabla licencias_activadas en DB
"""
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import RedirectResponse

RUTAS_LIBRES_EXACTAS = {"/", "/inicio", "/license/activar", "/license/machine-id",
                        "/license/activate", "/license/status", "/favicon.ico", "/health"}
RUTAS_LIBRES_PREFIJOS = {"/static"}


class LicenseMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, license_valid: bool = False):
        super().__init__(app)
        self._default_valid = license_valid

    async def dispatch(self, request: Request, call_next):
        license_valid = getattr(request.app.state, "license_valid", self._default_valid)
        if license_valid:
            return await call_next(request)

        # Re-verificar en DB (puede haber cambiado tras activacion o restart)
        try:
            import sys
            from pathlib import Path
            root_dir = Path(__file__).resolve().parents[2]
            if str(root_dir) not in sys.path:
                sys.path.insert(0, str(root_dir))
            import license_manager as lm
            _lic = lm.check_license()
            if _lic.get("valid"):
                request.app.state.license_valid = True
                request.app.state.license_info = _lic
                return await call_next(request)
            # Intentar DB
            from app.database import SessionLocal, LicenciaActivada
            db = SessionLocal()
            try:
                fp = lm.get_fingerprint()
                db_lic = db.query(LicenciaActivada).filter(
                    LicenciaActivada.machine_id == fp,
                    LicenciaActivada.activa == True,
                ).first()
                if db_lic:
                    _lic = lm.validate_license(db_lic.license_key)
                    if _lic.get("valid"):
                        request.app.state.license_valid = True
                        request.app.state.license_info = _lic
                        return await call_next(request)
            finally:
                db.close()
        except Exception:
            pass

        path = request.url.path
        if path in RUTAS_LIBRES_EXACTAS or any(path.startswith(r) for r in RUTAS_LIBRES_PREFIJOS):
            return await call_next(request)

        accept = request.headers.get("accept", "")
        if "application/json" in accept:
            from starlette.responses import JSONResponse
            return JSONResponse({"error": "Software no activado", "redirect": "/license/activar"}, status_code=403)

        return RedirectResponse("/license/activar", status_code=302)
