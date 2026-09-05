"""Claves de activacion comerciales, una por empresa y compartidas por sus equipos."""
import re
import secrets
import time
from threading import Lock

from app.database import Empresa
from app.utils.security import activation_key_hash

_KEY_RE = re.compile(r"^[A-Z0-9][A-Z0-9-]{11,119}$")
_lock = Lock()
_failed_until: dict[str, float] = {}


def _slug(value: str) -> str:
    clean = re.sub(r"[^A-Z0-9]+", "-", (value or "").upper()).strip("-")
    return clean[:24] or "EMPRESA"


def generate_company_key(company_name: str) -> str:
    """Genera una clave legible que incluye el nombre, sin datos secretos."""
    return f"{_slug(company_name)}-{secrets.token_urlsafe(24).replace('_', '-').replace('=', '').upper()}"


def normalize_company_key(value: str) -> str:
    return (value or "").strip().upper()


def is_valid_key_format(value: str) -> bool:
    return bool(_KEY_RE.fullmatch(normalize_company_key(value)))


def get_retry_after(client_key: str) -> int:
    with _lock:
        remaining = int(_failed_until.get(client_key, 0) - time.monotonic())
        if remaining <= 0:
            _failed_until.pop(client_key, None)
            return 0
        return remaining


def register_failed_activation(client_key: str, seconds: int = 30) -> None:
    with _lock:
        _failed_until[client_key] = time.monotonic() + seconds


def clear_failed_activation(client_key: str) -> None:
    with _lock:
        _failed_until.pop(client_key, None)


def assign_company_key(db, empresa: Empresa, plain_key: str | None = None) -> str:
    """Asigna una clave nueva y guarda solo su hash."""
    key = normalize_company_key(plain_key) if plain_key else generate_company_key(empresa.nombre)
    if not is_valid_key_format(key):
        raise ValueError("Formato de clave de activacion invalido")
    empresa.activation_key_hash = activation_key_hash(key)
    empresa.activation_key_hint = f"...{key[-8:]}"
    empresa.activation_enabled = True
    return key
