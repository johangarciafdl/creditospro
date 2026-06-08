import secrets

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse, Response


CSRF_COOKIE = "cp_csrf"
CSRF_HEADER = "x-csrf-token"
CSRF_FORM_FIELD = "csrf_token"
SAFE_METHODS = {"GET", "HEAD", "OPTIONS", "TRACE"}
EXEMPT_PATHS = {
    "/auth/login",
    "/auth/logout",
    "/health",
    "/license/activate",
}
# Endpoints que cambian el "nivel de confianza" (login, cambiar password, etc.).
# Despues de ejecutarse, el token CSRF se rota para que un atacante que ya
# robó el token anterior no pueda continuar haciendo acciones sensibles.
ROTATION_TRIGGER_PATHS = {
    "/auth/login",
    "/auth/cambiar-password",
    "/auth/recovery/reset",
}


def _new_token() -> str:
    return secrets.token_urlsafe(32)


def generate_csrf_token() -> str:
    """Expone el generador de tokens para que otros modulos (login) lo usen
    al rotar el token tras un cambio de contexto de seguridad.
    """
    return _new_token()


def ensure_csrf_token(request, response: Response | None = None) -> str:
    """Obtiene el token CSRF del request o genera uno nuevo y lo setea en la response.

    Util para vistas que renderizan formularios HTML: se garantiza que el
    template reciba el mismo token que el navegador tendra en cookie.
    """
    token = request.cookies.get(CSRF_COOKIE)
    if token:
        return token
    token = _new_token()
    if response is not None:
        response.set_cookie(
            CSRF_COOKIE,
            token,
            httponly=False,
            samesite="strict",
            secure=request.url.scheme == "https",
            max_age=60 * 60 * 12,
        )
    return token


async def _read_form_token(request) -> str | None:
    """Lee el token del cuerpo del request si es un form HTML."""
    content_type = request.headers.get("content-type", "")
    if not content_type.startswith(("application/x-www-form-urlencoded", "multipart/form-data")):
        return None
    try:
        form = await request.form()
        token = form.get(CSRF_FORM_FIELD)
        return token if isinstance(token, str) else None
    except Exception:
        return None


def _should_rotate(path: str, method: str) -> bool:
    return method in {"POST", "PUT", "PATCH", "DELETE"} and path in ROTATION_TRIGGER_PATHS


class CSRFMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        token = request.cookies.get(CSRF_COOKIE)
        if request.method not in SAFE_METHODS and request.url.path not in EXEMPT_PATHS:
            sent_token = request.headers.get(CSRF_HEADER)
            if not sent_token:
                sent_token = await _read_form_token(request)
            if not token or not sent_token or not secrets.compare_digest(token, sent_token):
                return JSONResponse({"error": "Solicitud bloqueada por CSRF"}, status_code=403)

        response = await call_next(request)

        # CSRF rotation: en endpoints sensibles, siempre emitir token nuevo
        if _should_rotate(request.url.path, request.method):
            new_token = _new_token()
            response.set_cookie(
                CSRF_COOKIE,
                new_token,
                httponly=False,
                samesite="strict",
                secure=request.url.scheme == "https",
                max_age=60 * 60 * 12,
            )
        elif not token:
            # No habia cookie, emitir una para futuras requests
            token = _new_token()
            response.set_cookie(
                CSRF_COOKIE,
                token,
                httponly=False,
                samesite="strict",
                secure=request.url.scheme == "https",
                max_age=60 * 60 * 12,
            )
        return response


