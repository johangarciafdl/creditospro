"""
CreditosPro v2.1 - Seguridad
bcrypt directo (compatible con bcrypt >= 4.0) + JWT con python-jose
"""
import logging
import hashlib
import hmac
import json
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

import bcrypt
import jwt
from jwt import InvalidTokenError
from cryptography.fernet import Fernet, InvalidToken

from app.utils.settings import settings

logger = logging.getLogger(__name__)

ALGORITHM = "HS256"


def activation_key_hash(key: str) -> str:
    """Obtiene un hash determinista para buscar una clave de empresa.

    La clave original nunca se almacena en la base de datos.
    """
    normalized = (key or "").strip().upper().encode("utf-8")
    return hashlib.sha256(normalized).hexdigest()


def activation_key_matches(key: str, expected_hash: str | None) -> bool:
    if not expected_hash:
        return False
    return hmac.compare_digest(activation_key_hash(key), expected_hash)


def _secret_cipher() -> Fernet:
    if not settings.SECRET_KEY:
        raise RuntimeError("SECRET_KEY no esta configurada")
    material = hashlib.sha256(settings.SECRET_KEY.encode("utf-8")).digest()
    import base64
    return Fernet(base64.urlsafe_b64encode(material))


def encrypt_secret(value: str) -> str:
    return _secret_cipher().encrypt(value.encode("utf-8")).decode("ascii")


def decrypt_secret(value: str) -> str | None:
    try:
        return _secret_cipher().decrypt(value.encode("ascii")).decode("utf-8")
    except (InvalidToken, ValueError, TypeError):
        return None


def serialize_backup_hashes(values: list[str]) -> str:
    return json.dumps(values, separators=(",", ":"))


def get_password_hash(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except (ValueError, TypeError) as e:
        logger.warning("Hash de contrasena invalido: %s", e)
        return False


# Hash de un valor dummy con la misma configuracion que las contrasenas reales.
# Se usa para igualar el tiempo de respuesta del login cuando el usuario
# no existe, evitando ataques de timing/enumeracion de usuarios.
# Pre-generado al import time para que el primer login no sufra el costo
# extra de la generacion del hash (que seria medible por un atacante).
_DUMMY_HASH: str = bcrypt.hashpw(b"__timing_dummy__", bcrypt.gensalt()).decode("utf-8")


def _get_dummy_hash() -> str:
    """Devuelve el hash dummy pre-generado."""
    return _DUMMY_HASH


def verify_password_with_timing_safety(plain: str, hashed: Optional[str]) -> bool:
    """Verifica una contrasena manteniendo tiempo constante.

    Si hashed es None (usuario no existe en BD), aun asi ejecuta bcrypt
    contra un hash dummy para que el tiempo de respuesta sea indistinguible
    de cuando el usuario existe. Esto bloquea ataques de enumeracion por
    timing.
    """
    if not hashed:
        # Usuario no existe: ejecutar dummy bcrypt para igualar timing
        try:
            bcrypt.checkpw(plain.encode("utf-8"), _get_dummy_hash().encode("utf-8"))
        except Exception:
            pass
        return False
    return verify_password(plain, hashed)


def create_access_token(data: dict) -> str:
    """Crea un JWT con iat, nbf, exp y jti para permitir revocacion futura."""
    if not settings.SECRET_KEY:
        raise RuntimeError("SECRET_KEY no esta configurada")

    now = datetime.now(timezone.utc)
    expire = now + timedelta(hours=settings.ACCESS_TOKEN_EXPIRE_HOURS)

    to_encode = data.copy()
    to_encode.update({
        "iat": int(now.timestamp()),
        "nbf": int(now.timestamp()),
        "exp": int(expire.timestamp()),
        "jti": uuid.uuid4().hex,
    })
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=ALGORITHM)


def decode_token(token: str) -> Optional[dict]:
    try:
        payload = jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=[ALGORITHM],
            options={"require": ["exp", "iat"]},
        )
        return payload
    except InvalidTokenError:
        return None
