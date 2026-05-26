"""Middleware que bloquea el sistema si la licencia es inválida."""
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

        path = request.url.path
        if path in RUTAS_LIBRES_EXACTAS or any(path.startswith(r) for r in RUTAS_LIBRES_PREFIJOS):
            return await call_next(request)

        accept = request.headers.get("accept", "")
        if "application/json" in accept:
            from starlette.responses import JSONResponse
            return JSONResponse({"error": "Software no activado", "redirect": "/license/activar"}, status_code=403)

        return RedirectResponse("/license/activar", status_code=302)
