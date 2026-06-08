"""
Blacklist de tokens JWT (jti) en memoria + persistencia opcional.

Cuando un usuario hace logout, cambia su contrasena, o el admin revoca
una sesion, agregamos el jti del token a esta blacklist. La verificacion
se hace en get_current_user().

Limitaciones:
- Es en memoria del proceso: si hay multiples workers (gunicorn -w 4),
  los workers no comparten la blacklist. Para produccion multi-worker,
  cambiar a Redis. El modulo expone la misma interfaz para minimizar
  el cambio.
- La blacklist crece linealmente. Limitamos a los ultimos 10k jtis y
  purhamos los que ya expiraron cada vez que agregamos uno nuevo.
"""
import logging
import threading
import time
from typing import Optional

logger = logging.getLogger(__name__)

_MAX_ENTRIES = 10_000
_revoked: dict[str, int] = {}  # jti -> exp_epoch
_active_by_user: dict[str, list[dict]] = {}  # user_id -> [{jti, exp, issued, ip}]
_lock = threading.Lock()


def _purge_expired():
    """Quita entradas expiradas. Llamar con _lock tomado."""
    now = int(time.time())
    expired = [jti for jti, exp in _revoked.items() if exp <= now]
    for jti in expired:
        _revoked.pop(jti, None)
    # Tambien limpiar sesiones activas expiradas
    for uid in list(_active_by_user.keys()):
        _active_by_user[uid] = [
            s for s in _active_by_user[uid] if s["exp"] > now
        ]
        if not _active_by_user[uid]:
            _active_by_user.pop(uid, None)


def revoke_jti(jti: str, exp_epoch: int) -> None:
    """Agrega un jti a la blacklist hasta su expiracion."""
    if not jti:
        return
    with _lock:
        _purge_expired()
        if len(_revoked) >= _MAX_ENTRIES:
            # Evitar crecimiento ilimitado: descarta el mas antiguo
            oldest = min(_revoked.items(), key=lambda x: x[1])[0]
            _revoked.pop(oldest, None)
        _revoked[jti] = int(exp_epoch) if exp_epoch else int(time.time()) + 3600
        logger.debug("jti revocado: %s...", jti[:8])


def is_jti_revoked(jti: str) -> bool:
    with _lock:
        return jti in _revoked


def revoke_jti_by_prefix_and_user(prefix: str, user_id: str) -> bool:
    """Revoca un jti buscando por prefijo + usuario (para endpoint sesiones).

    Devuelve True si encontro y revoco alguno.
    """
    with _lock:
        sesiones = _active_by_user.get(user_id, [])
        for s in sesiones:
            if s["jti"].startswith(prefix):
                _revoked[s["jti"]] = s["exp"]
                sesiones.remove(s)
                return True
        return False


def register_active_jti(user_id: str, jti: str, exp_epoch: int, ip: str = "?") -> None:
    """Registra una sesion activa (para listar/revocar)."""
    if not user_id or not jti:
        return
    with _lock:
        _purge_expired()
        _active_by_user.setdefault(user_id, []).append({
            "jti": jti,
            "exp": int(exp_epoch),
            "issued": int(time.time()),
            "ip": ip,
        })


def list_active_jti_for_user(user_id: str) -> list[dict]:
    with _lock:
        return list(_active_by_user.get(user_id, []))
