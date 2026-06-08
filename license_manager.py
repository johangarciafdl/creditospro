"""
CreditosPro License Manager v3
Lee la clave maestra desde la variable de entorno LICENSE_MASTER_KEY.
"""
import os, json, socket, hashlib, uuid, datetime, base64
from pathlib import Path

LICENSE_FILE = Path(__file__).parent / "license.key"


def _get_master_secret() -> str:
    """Obtiene la clave maestra desde la variable de entorno.

    En produccion debe estar siempre definida.
    """
    key = os.getenv("LICENSE_MASTER_KEY", "").strip()
    if not key:
        raise RuntimeError(
            "LICENSE_MASTER_KEY no esta definida. Configurala en .env "
            "o como variable de entorno antes de validar licencias."
        )
    return key


def get_fingerprint() -> str:
    import platform
    parts = [str(uuid.getnode()), socket.gethostname(),
             platform.processor(), platform.machine(), platform.system()]
    return hashlib.sha256("|".join(parts).encode()).hexdigest()[:32].upper()


def _derive_key():
    key_bytes = hashlib.sha256(_get_master_secret().encode()).digest()
    return base64.urlsafe_b64encode(key_bytes)


def validate_license(license_key: str) -> dict:
    try:
        from cryptography.fernet import Fernet
        f = Fernet(_derive_key())
        key_clean = license_key.strip()
        raw = key_clean[5:] if key_clean.startswith("CPRO-") else key_clean
        pad = len(raw) % 4
        if pad:
            raw += "=" * (4 - pad)
        token = base64.urlsafe_b64decode(raw.encode())
        payload = json.loads(f.decrypt(token).decode())

        current_fp = get_fingerprint()
        if payload["machine_id"] != current_fp:
            return {
                "valid": False,
                "error": f"Licencia no valida para este equipo.\nTu Machine ID: {current_fp}",
                "machine_id": current_fp,
            }

        expires = datetime.datetime.fromisoformat(payload["expires_at"])
        if expires < datetime.datetime.now():
            return {
                "valid": False,
                "error": f"Licencia expirada el {expires.strftime('%d/%m/%Y')}.",
                "machine_id": current_fp,
            }

        days_left = (expires - datetime.datetime.now()).days
        return {**payload, "valid": True, "days_left": days_left}

    except RuntimeError as e:
        return {"valid": False, "error": str(e), "machine_id": get_fingerprint()}
    except Exception as e:
        return {
            "valid": False,
            "error": f"Licencia invalida: {str(e)[:80]}",
            "machine_id": get_fingerprint(),
        }


def check_license() -> dict:
    if not LICENSE_FILE.exists():
        return {"valid": False, "error": "No hay licencia instalada.", "machine_id": get_fingerprint()}
    return validate_license(LICENSE_FILE.read_text(encoding="utf-8").strip())


def save_license(key: str) -> dict:
    result = validate_license(key)
    if result.get("valid"):
        LICENSE_FILE.write_text(key.strip(), encoding="utf-8")
    return result
