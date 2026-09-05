"""Utilidades TOTP para autenticacion de dos factores."""
import hashlib
import json
import secrets


def generate_secret() -> str:
    """Genera un secreto base32 de 160 bits para apps autenticadoras."""
    import pyotp
    return pyotp.random_base32()


def hash_backup_code(code: str) -> str:
    return hashlib.sha256(code.encode("utf-8")).hexdigest()


def generate_backup_codes(n: int = 10) -> list[str]:
    return [secrets.token_hex(4).upper() for _ in range(n)]


def verify_totp(secret: str, code: str) -> bool:
    import pyotp
    return bool(secret and code and pyotp.TOTP(secret).verify(code.strip(), valid_window=1))


def provisioning_uri(secret: str, username: str, issuer: str = "CreditosPro") -> str:
    import pyotp
    return pyotp.TOTP(secret).provisioning_uri(name=username, issuer_name=issuer)


def backup_hashes_json(codes: list[str]) -> str:
    return json.dumps([hash_backup_code(code) for code in codes], separators=(",", ":"))


def consume_backup_code(raw_code: str, stored_json: str | None) -> tuple[bool, str]:
    try:
        hashes = json.loads(stored_json or "[]")
    except json.JSONDecodeError:
        hashes = []
    candidate = hash_backup_code((raw_code or "").strip().upper())
    if candidate not in hashes:
        return False, stored_json or "[]"
    hashes.remove(candidate)
    return True, json.dumps(hashes, separators=(",", ":"))
