"""Middleware que inyecta headers de seguridad HTTP en todas las respuestas."""
import contextvars
import secrets

from starlette.middleware.base import BaseHTTPMiddleware

# ContextVar para que los templates Jinja puedan leer el nonce actual
_csp_nonce_var: contextvars.ContextVar[str] = contextvars.ContextVar(
    "csp_nonce", default=""
)

# CSP estricto SIN 'unsafe-inline' (modo estricto nonce-based).
# Los templates pueden usar {{ csp_nonce }} para marcar scripts/estilos
# inline legitimos sin perder proteccion contra inyecciones.
# 'unsafe-inline' en style-src es necesario para los <style> inline de los
# templates actuales; el nonce protege <script>. Migrar estilos a archivos
# .css para cerrar tambien ahi.
DEFAULT_CSP = (
    "default-src 'self'; "
    "script-src 'self' 'nonce-{nonce}' https://cdnjs.cloudflare.com https://cdn.jsdelivr.net; "
    "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com https://cdn.jsdelivr.net; "
    "font-src 'self' https://fonts.gstatic.com data:; "
    "img-src 'self' data: blob: https:; "
    "connect-src 'self' https:; "
    "frame-ancestors 'none'; "
    "base-uri 'self'; "
    "form-action 'self'; "
    "object-src 'none'"
)

# CSP estricto en modo "solo reporte": el navegador NUNCA bloquea nada con
# este header (a diferencia de Content-Security-Policy), solo reporta a
# report-uri lo que SI bloquearia si estuviera activo. Se usa para migrar
# de forma segura: primero se observa que se romperia con uso real, se
# corrige, y recien despues se activa DEFAULT_CSP de verdad.
REPORT_ONLY_CSP = (
    "default-src 'self'; "
    "script-src 'self' 'nonce-{nonce}' https://cdnjs.cloudflare.com https://cdn.jsdelivr.net; "
    "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com https://cdn.jsdelivr.net; "
    "font-src 'self' https://fonts.gstatic.com data:; "
    "img-src 'self' data: blob: https:; "
    "connect-src 'self' https:; "
    "frame-ancestors 'none'; "
    "base-uri 'self'; "
    "form-action 'self'; "
    "object-src 'none'; "
    "report-uri /csp-report"
)

# Fallback: si el template no incluye el nonce, mantener compatibilidad
# usando 'unsafe-inline' (menos seguro pero funcional).
LEGACY_CSP = (
    "default-src 'self'; "
    "script-src 'self' 'unsafe-inline' https://cdnjs.cloudflare.com https://cdn.jsdelivr.net; "
    "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com https://cdn.jsdelivr.net; "
    "font-src 'self' https://fonts.gstatic.com data:; "
    "img-src 'self' data: blob: https:; "
    "connect-src 'self' https:; "
    "frame-ancestors 'none'; "
    "base-uri 'self'; "
    "form-action 'self'; "
    "object-src 'none'"
)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Inyecta headers de seguridad recomendados por OWASP.

    Genera un nonce por request para CSP estricto y lo expone en
    request.state.csp_nonce para que los templates lo usen asi:
        <script nonce="{{ csp_nonce }}">...</script>
    """

    def __init__(self, app, is_production: bool = True, csp: str | None = None,
                 use_strict_csp: bool = False, enable_csp_reporting: bool = True):
        super().__init__(app)
        self.is_production = is_production
        self.csp = csp or (DEFAULT_CSP if use_strict_csp else LEGACY_CSP)
        self.use_strict = use_strict_csp
        # Independiente de use_strict: envia el CSP estricto en modo
        # solo-reporte aunque el CSP que realmente aplica siga siendo LEGACY.
        self.enable_csp_reporting = enable_csp_reporting

    async def dispatch(self, request, call_next):
        nonce = secrets.token_urlsafe(16)
        # Exponer el nonce para que las vistas/templates lo lean
        request.state.csp_nonce = nonce
        token = _csp_nonce_var.set(nonce)
        try:
            response = await call_next(request)
        finally:
            _csp_nonce_var.reset(token)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers.setdefault(
            "Permissions-Policy",
            "geolocation=(self), camera=(self), microphone=(), payment=()",
        )
        # CSP con nonce si es estricto, o legacy si no
        if self.use_strict:
            csp_value = self.csp.format(nonce=nonce)
        else:
            csp_value = self.csp
        response.headers.setdefault("Content-Security-Policy", csp_value)
        # CSP estricto en modo solo-reporte: no bloquea nada (el header de
        # arriba es el que realmente aplica), pero el navegador reporta a
        # /csp-report cualquier cosa que el modo estricto SI bloquearia.
        if self.enable_csp_reporting and not self.use_strict:
            response.headers.setdefault(
                "Content-Security-Policy-Report-Only", REPORT_ONLY_CSP.format(nonce=nonce)
            )
        # Cross-origin policies
        response.headers.setdefault("Cross-Origin-Opener-Policy", "same-origin")
        response.headers.setdefault("Cross-Origin-Resource-Policy", "same-origin")
        # HSTS solo si la peticion vino por HTTPS o estamos detras de un proxy con TLS
        if self.is_production:
            forwarded_proto = request.headers.get("x-forwarded-proto", "")
            if request.url.scheme == "https" or forwarded_proto == "https":
                response.headers.setdefault(
                    "Strict-Transport-Security",
                    "max-age=31536000; includeSubDomains",
                )
        # Exponer el nonce tambien en header para debugging
        if self.use_strict:
            response.headers["X-CSP-Nonce"] = nonce
        return response
