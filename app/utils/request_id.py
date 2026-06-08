"""
Middleware que asigna un request_id a cada peticion HTTP.

- Lee el header X-Request-ID si viene (trazabilidad cross-service)
- Si no, genera un UUID4 corto
- Lo expone en el log context (logging.LoggerAdapter) y en el header
  de respuesta X-Request-ID

Beneficio: cuando un cliente reporta "el cobro fallo a las 14:32", puedes
buscar el request_id en los logs y ver TODO lo que paso en esa peticion.
"""
import logging
import uuid
from contextvars import ContextVar

from starlette.middleware.base import BaseHTTPMiddleware

REQUEST_ID_HEADER = "X-Request-ID"
_request_id_var: ContextVar[str] = ContextVar("request_id", default="-")


def get_request_id() -> str:
    """Devuelve el request_id actual (o '-' si no estamos en una request)."""
    return _request_id_var.get()


class RequestIDFilter(logging.Filter):
    """Inyecta el request_id en cada LogRecord."""
    def filter(self, record):
        record.request_id = _request_id_var.get()
        return True


class RequestIDMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        rid = request.headers.get(REQUEST_ID_HEADER) or uuid.uuid4().hex[:16]
        token = _request_id_var.set(rid)
        try:
            response = await call_next(request)
        finally:
            _request_id_var.reset(token)
        response.headers[REQUEST_ID_HEADER] = rid
        return response
