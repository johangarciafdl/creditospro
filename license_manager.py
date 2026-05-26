"""
CreditosPro License Manager v3
Este archivo va en la raiz del proyecto (junto a run.py)
"""
import os, sys, json, socket, hashlib, uuid, datetime, base64
from pathlib import Path

MASTER_SECRET = "CREDITOSPRO-JOHAN-GARCIA-2024-MASTER-KEY-ULTRA-SEGURA"
LICENSE_FILE  = Path(__file__).parent / "license.key"

def get_fingerprint() -> str:
    import platform
    parts = [str(uuid.getnode()), socket.gethostname(),
             platform.processor(), platform.machine(), platform.system()]
    return hashlib.sha256("|".join(parts).encode()).hexdigest()[:32].upper()

def _derive_key():
    key_bytes = hashlib.sha256(MASTER_SECRET.encode()).digest()
    return base64.urlsafe_b64encode(key_bytes)

def validate_license(license_key: str) -> dict:
    try:
        from cryptography.fernet import Fernet, InvalidToken
        f = Fernet(_derive_key())
        key_clean = license_key.strip()
        if key_clean.startswith("CPRO-"):
            raw = key_clean[5:]
        else:
            raw = key_clean
        # Decodificar con padding
        pad = len(raw) % 4
        if pad: raw += "=" * (4 - pad)
        token = base64.urlsafe_b64decode(raw.encode())
        payload = json.loads(f.decrypt(token).decode())

        current_fp = get_fingerprint()
        if payload["machine_id"] != current_fp:
            return {"valid": False, "error": f"Licencia no valida para este equipo.\nTu Machine ID: {current_fp}",
                    "machine_id": current_fp}

        expires = datetime.datetime.fromisoformat(payload["expires_at"])
        if expires < datetime.datetime.now():
            return {"valid": False, "error": f"Licencia expirada el {expires.strftime('%d/%m/%Y')}.",
                    "machine_id": current_fp}

        days_left = (expires - datetime.datetime.now()).days
        return {**payload, "valid": True, "days_left": days_left}

    except Exception as e:
        fp = get_fingerprint()
        return {"valid": False, "error": f"Licencia invalida: {str(e)[:80]}", "machine_id": fp}

def check_license() -> dict:
    if not LICENSE_FILE.exists():
        return {"valid": False, "error": "No hay licencia instalada.", "machine_id": get_fingerprint()}
    return validate_license(LICENSE_FILE.read_text(encoding="utf-8").strip())

def save_license(key: str) -> dict:
    result = validate_license(key)
    if result["valid"]:
        LICENSE_FILE.write_text(key.strip(), encoding="utf-8")
    return result
