"""
Tokens de recuperacion de contrasena (admin-assisted, sin SMTP).

Modelo: un usuario pide reset -> admin lo aprueba -> token de un solo
uso con expiracion -> usuario canjea token por nueva contrasena.

Los tokens son seguros contra timing attack: el almacenamiento es por
hash SHA-256, y consume_recovery_token() recorre la lista comparando
en tiempo constante.
"""
import hashlib
import hmac
import logging
import secrets
import threading
import time
from typing import Optional

logger = logging.getLogger(__name__)

_TOKEN_TTL_SECONDS = 60 * 60 * 4  # 4 horas


_tokens_lock = threading.Lock()
_tokens: dict[str, dict] = {}  # token_hash -> {user_id, empresa_id, username, exp, used}


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def create_recovery_token(empresa_id: int, user_id: int, username: str) -> str:
    """Crea un token de recuperacion. Devuelve el token en texto plano
    (el caller lo entregara al usuario). Solo el hash se guarda.
    """
    token = secrets.token_urlsafe(32)
    token_h = _hash_token(token)
    with _tokens_lock:
        # Limpieza de tokens expirados
        now = int(time.time())
        expired = [h for h, info in _tokens.items() if info["exp"] <= now]
        for h in expired:
            _tokens.pop(h, None)
        _tokens[token_h] = {
            "user_id": user_id,
            "empresa_id": empresa_id,
            "username": username,
            "exp": now + _TOKEN_TTL_SECONDS,
            "used": False,
        }
    logger.info("Token de recuperacion emitido para username=%s expira en 4h", username)
    return token


def consume_recovery_token(token: str) -> Optional[dict]:
    """Canjea un token. Devuelve info del usuario si valido, None si no.

    Hace la comparacion en tiempo constante para evitar timing attacks.
    El token se marca como usado inmediatamente para que no pueda
    reutilizarse.
    """
    if not token:
        return None
    token_h = _hash_token(token)
    now = int(time.time())
    with _tokens_lock:
        # Busqueda en tiempo constante
        for stored_hash, info in _tokens.items():
            if hmac.compare_digest(stored_hash, token_h):
                if info["used"] or info["exp"] <= now:
                    return None
                info["used"] = True
                return {
                    "user_id": info["user_id"],
                    "empresa_id": info["empresa_id"],
                    "username": info["username"],
                }
        return None
