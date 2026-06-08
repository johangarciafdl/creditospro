"""
Audit log de acciones sensibles.

Guarda en BD las acciones administrativas o de cambio de estado para
trazabilidad. Usado por:
- login/logout
- cambios de contrasena
- creacion/eliminacion de usuarios
- emitir/revocar tokens de recuperacion
- cualquier accion destructiva o de cambio de privilegios

El modulo expone log_action() que el codigo de negocio llama cuando
realiza una accion sensible. La tabla se crea en database.py.
"""
import logging
from typing import Optional

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


def log_action(
    db: Session,
    user,
    action: str,
    category: str = "general",
    details: str = "",
    ip: str = "",
) -> None:
    """Registra una accion en el audit log.

    Args:
        db: sesion SQLAlchemy
        user: usuario que realiza la accion (puede ser None para eventos del sistema)
        action: nombre de la accion (login, password_change, user_create, etc.)
        category: categoria (auth, users, finance, etc.)
        details: texto libre con detalles (no incluir PII sensible)
        ip: direccion IP del cliente
    """
    try:
        from app.database import AuditLog
        entry = AuditLog(
            empresa_id=user.empresa_id if user and hasattr(user, "empresa_id") else None,
            usuario_id=user.id if user and hasattr(user, "id") else None,
            username=user.username if user and hasattr(user, "username") else None,
            action=action[:80],
            category=category[:40],
            details=details[:500],
            ip=(ip or "")[:45],
        )
        db.add(entry)
        db.commit()
    except Exception:
        # Nunca dejar que un fallo de audit log rompa la operacion principal
        logger.exception("Error registrando accion de audit log")
        try:
            db.rollback()
        except Exception:
            pass
