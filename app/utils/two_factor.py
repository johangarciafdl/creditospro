"""
Esqueleto para autenticacion de dos factores (TOTP, RFC 6238).

ESTADO ACTUAL: solo la interfaz y stubs. Para activarlo:

1. Anadir dependencia: pip install pyotp qrcode[pil]
2. Crear tabla para 'two_factor_secrets' en database.py
3. Implementar setup_2fa() y verify_2fa() con pyotp
4. Modificar /auth/login para que despues de la contrasena, si el
   usuario tiene 2FA activo, redirija a /auth/2fa-challenge y pida
   el codigo TOTP
5. Agregar endpoint /auth/2fa/setup con QR para que el usuario escanee
   con Google Authenticator / Authy

El flujo seria:
  - Setup: genera secret, lo guarda hasheado en BD, devuelve QR
  - Login: si usuario tiene 2FA, redirige a /2fa-challenge
  - Verify: usuario ingresa codigo de 6 digitos, se valida con pyotp.TOTP(secret).verify(code)
  - Backup codes: 10 codigos de un solo uso generados al setup

Esto es un esqueleto seguro: no hay activacion accidental sin querer
implementar el flujo completo.
"""
import logging
import secrets
import hashlib

logger = logging.getLogger(__name__)


def generate_secret() -> str:
    """Genera un secret base32 de 160 bits (estandar TOTP)."""
    return secrets.token_hex(20)


def hash_backup_code(code: str) -> str:
    """Hashea un codigo de respaldo para guardarlo en BD."""
    return hashlib.sha256(code.encode("utf-8")).hexdigest()


def generate_backup_codes(n: int = 10) -> list[str]:
    """Genera N codigos de respaldo de 8 caracteres.

    Guardar solo el hash, devolver el codigo en claro UNA sola vez.
    """
    return [secrets.token_hex(4).upper() for _ in range(n)]


def verify_totp(secret: str, code: str) -> bool:
    """Verifica un codigo TOTP. Esqueleto.

    Implementacion real:
        import pyotp
        totp = pyotp.TOTP(secret)
        # window=1 acepta el codigo anterior y el siguiente (60s tolerancia)
        return totp.verify(code, valid_window=1)
    """
    logger.warning("verify_totp() es un esqueleto — no usar en produccion")
    return False
