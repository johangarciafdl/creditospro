"""
CreditosPro License Manager (modulo legacy)

NOTA: Este modulo NO se usa en runtime. La validacion de licencias activa
es la de `license_manager.py` en la raiz del proyecto. Se conserva por
compatibilidad con scripts antiguos.
"""
import os, hashlib, json, uuid, platform, logging
from pathlib import Path
from datetime import datetime, timedelta
from cryptography.fernet import Fernet

logger = logging.getLogger(__name__)

LICENSE_FILE = Path("data/license.json")
MASTER_KEY = os.getenv("LICENSE_MASTER_KEY", "").encode()
if not MASTER_KEY:
    raise EnvironmentError(
        "La variable de entorno LICENSE_MASTER_KEY no esta configurada. "
        "Crea un archivo .env a partir de .env.example"
    )
SIGN_KEY = hashlib.sha256(MASTER_KEY).digest()[:32]


def get_machine_id() -> str:
    """Huella unica de la maquina (no cambia al reinstalar)"""
    parts = [
        platform.node(),
        platform.machine(),
        platform.processor(),
        str(uuid.getnode()),
    ]
    raw = "|".join(parts)
    return hashlib.sha256(raw.encode()).hexdigest()[:24]


def generate_license_key(machine_id: str, plan: str = "pro", days: int = 365) -> str:
    """[ADMIN] Genera una clave de licencia para una maquina"""
    import base64
    key = base64.urlsafe_b64encode(SIGN_KEY)[:43] + b"="
    f = Fernet(key)
    data = json.dumps({
        "machine_id": machine_id,
        "plan": plan,
        "issued": datetime.now().isoformat(),
        "expires": (datetime.now() + timedelta(days=days)).isoformat(),
        "owner": os.getenv("SOFTWARE_OWNER", ""),
    }).encode()
    token = f.encrypt(data)
    raw = token.decode()[:28].upper().replace("/", "A").replace("+", "B").replace("=", "C")
    chunks = [raw[i:i + 4] for i in range(0, 20, 4)]
    return "CPRO-" + "-".join(chunks)


def verify_license(key: str) -> dict:
    """Verifica una clave de licencia"""
    LICENSE_FILE.parent.mkdir(exist_ok=True)
    if LICENSE_FILE.exists():
        try:
            data = json.loads(LICENSE_FILE.read_text())
            if data.get("machine_id") == get_machine_id():
                exp = datetime.fromisoformat(data["expires"])
                if exp > datetime.now():
                    data["valid"] = True
                    data["days_left"] = (exp - datetime.now()).days
                    return data
        except (OSError, ValueError, KeyError) as e:
            logger.warning("No se pudo verificar la licencia: %s", e)
    return {"valid": False, "error": "Licencia no valida o expirada"}


def is_licensed() -> bool:
    try:
        r = verify_license("")
        return r.get("valid", False)
    except Exception:
        logger.exception("Error inesperado verificando licencia")
        return False

