"""Middleware que bloquea el acceso hasta que la empresa active su clave comercial.

Unica capa de activacion: una clave por-empresa (ver app/utils/company_activation.py
y app/routers/license_router.py) que el usuario ingresa en /license/activar y que
marca `activated_empresa_id` en su sesion de navegador. No hay licencia por-maquina.
"""
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import RedirectResponse

RUTAS_LIBRES_EXACTAS = {"/", "/inicio", "/comprar", "/license/activar", "/license/activate",
                        "/license/status", "/favicon.ico", "/health", "/csp-report",
                        "/auth/logout"}
# /plataforma es el panel del dueno de la plataforma (superadmin) -- administra
# TODAS las empresas, no es cliente de ninguna, asi que no tiene (ni deberia
# necesitar) una clave comercial de empresa para entrar. Su propia autenticacion
# (ver /plataforma/login en app/routers/plataforma.py) es el control de acceso real.
RUTAS_LIBRES_PREFIJOS = {"/static", "/plataforma"}


class LicenseMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if request.session.get("activated_empresa_id"):
            return await call_next(request)

        path = request.url.path
        if path in RUTAS_LIBRES_EXACTAS or path == "/auth/login" or any(path.startswith(r) for r in RUTAS_LIBRES_PREFIJOS):
            return await call_next(request)

        accept = request.headers.get("accept", "")
        if "application/json" in accept:
            from starlette.responses import JSONResponse
            return JSONResponse({"error": "Empresa no activada", "redirect": "/license/activar"}, status_code=403)

        return RedirectResponse("/license/activar", status_code=302)
