"""Auditoria transversal de operaciones mutables."""
import logging

from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger(__name__)

_SKIP_PREFIXES = ("/static", "/health", "/api/docs", "/openapi.json")
_MUTATING = {"POST", "PUT", "PATCH", "DELETE"}


class AuditMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        response = await call_next(request)
        path = request.url.path
        if request.method not in _MUTATING or path.startswith(_SKIP_PREFIXES):
            return response

        try:
            from app.database import AuditLog, SessionLocal
            from app.routers.auth import get_current_user

            db = SessionLocal()
            try:
                user = get_current_user(request, db)
                if user:
                    db.add(AuditLog(
                        empresa_id=user.empresa_id,
                        usuario_id=user.id,
                        username=user.username,
                        action=f"request_{request.method.lower()}",
                        category="request",
                        details=f"path={path[:430]} status={response.status_code}",
                        ip=(request.client.host if request.client else "unknown")[:45],
                    ))
                    db.commit()
            finally:
                db.close()
        except Exception:
            logger.exception("No se pudo registrar auditoria transversal")
        return response
