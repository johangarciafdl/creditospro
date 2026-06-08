"""
Middleware que limita el tamano del body de las peticiones.

Por defecto rechaza cualquier peticion con Content-Length mayor a
MAX_BODY_SIZE. Esto previene DoS con JSON de 100MB o subida de archivos
no restringida en endpoints JSON.

Las excepciones se controlan con EXEMPT_PATHS (p.ej. uploads de imagenes).
"""
import logging

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

logger = logging.getLogger(__name__)

MAX_BODY_SIZE = 1 * 1024 * 1024  # 1 MB para requests JSON por defecto
UPLOAD_MAX_BODY_SIZE = 6 * 1024 * 1024  # 6 MB para endpoints con upload
UPLOAD_PATH_PREFIXES = (
    "/cobros/registrar",
    "/clientes/",
    "/uploads/",
)

# Endpoints que intencionalmente aceptan bodies mas grandes
EXEMPT_PATHS: set[str] = set()


def _max_for_path(path: str) -> int:
    if any(path.startswith(p) for p in UPLOAD_PATH_PREFIXES):
        return UPLOAD_MAX_BODY_SIZE
    return MAX_BODY_SIZE


class BodySizeLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        if request.url.path in EXEMPT_PATHS:
            return await call_next(request)

        cl = request.headers.get("content-length")
        if cl:
            try:
                size = int(cl)
                limit = _max_for_path(request.url.path)
                if size > limit:
                    logger.warning(
                        "Body demasiado grande: path=%s size=%s limit=%s",
                        request.url.path, size, limit,
                    )
                    return JSONResponse(
                        {
                            "error": (
                                f"Solicitud demasiado grande "
                                f"(max {limit // 1024} KB)"
                            )
                        },
                        status_code=413,
                    )
            except ValueError:
                pass
        return await call_next(request)
