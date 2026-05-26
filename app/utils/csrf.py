import secrets

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse


CSRF_COOKIE = "cp_csrf"
CSRF_HEADER = "x-csrf-token"
SAFE_METHODS = {"GET", "HEAD", "OPTIONS", "TRACE"}
EXEMPT_PATHS = {
    "/auth/login",
    "/auth/logout",
    "/health",
    "/license/activate",
}


class CSRFMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        token = request.cookies.get(CSRF_COOKIE)
        if request.method not in SAFE_METHODS and request.url.path not in EXEMPT_PATHS:
            sent_token = request.headers.get(CSRF_HEADER)
            if not token or not sent_token or not secrets.compare_digest(token, sent_token):
                return JSONResponse({"error": "Solicitud bloqueada por CSRF"}, status_code=403)

        response = await call_next(request)
        if not token:
            token = secrets.token_urlsafe(32)
            response.set_cookie(
                CSRF_COOKIE,
                token,
                httponly=False,
                samesite="strict",
                secure=request.url.scheme == "https",
                max_age=60 * 60 * 12,
            )
        return response
