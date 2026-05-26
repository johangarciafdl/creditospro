"""Configuración centralizada leída desde variables de entorno."""
import os
import socket
from pathlib import Path


def _get_local_ip():
    """Obtiene la IP local de la máquina para CORS"""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


class Settings:
    """Configuración centralizada de la aplicación."""

    # ── Base de datos ──────────────────────────────────────────
    DATABASE_URL: str = ""  # Obligatoria, se valida en startup

    # ── Seguridad ──────────────────────────────────────────────
    SECRET_KEY: str = ""  # Obligatoria, se valida en startup
    SESSION_SECRET_KEY: str = ""
    ACCESS_TOKEN_EXPIRE_HOURS: int = 12

    # ── Licencia ───────────────────────────────────────────────
    LICENSE_MASTER_KEY: str = ""

    # ── WhatsApp ────────────────────────────────────────────────
    WP_API_KEY: str = ""
    WP_PHONE_ID: str = ""
    WP_TOKEN: str = ""
    WP_ACTIVO: bool = False

    # ── Servidor ───────────────────────────────────────────────
    PORT: int = 8000
    ENVIRONMENT: str = "production"
    NO_BROWSER: bool = False
    CORS_ORIGINS: list[str] = [
        "http://127.0.0.1:8000",
        "http://localhost:8000",
        f"http://{_get_local_ip()}:8000",
    ]
    DEFAULT_COMPANY_NAME: str = "ElRusso"
    ALLOW_PUBLIC_REGISTRATION: bool = False

    # ── PWA ────────────────────────────────────────────────────
    PWA_OFFLINE_LIMIT: int = 500  # Límite de registros para sync offline
    SOFTWARE_NAME: str = "CreditosPro"
    SOFTWARE_OWNER: str = "Johan Garcia"

    @property
    def IS_PRODUCTION(self) -> bool:
        return self.ENVIRONMENT == "production"

    @property
    def BASE_DIR(self) -> Path:
        return Path(__file__).resolve().parent.parent.parent


# Cargar desde variables de entorno
def get_settings() -> Settings:
    settings = Settings()

    def env_int(name: str, default: int) -> int:
        raw = os.getenv(name, str(default))
        try:
            return int(raw)
        except (TypeError, ValueError):
            return default

    def env_bool(name: str, default: bool = False) -> bool:
        raw = os.getenv(name)
        if raw is None:
            return default
        return raw.strip().lower() in {"1", "true", "yes", "on", "si", "sí"}

    # Cargar valores desde entorno
    settings.DATABASE_URL = os.getenv("DATABASE_URL", "")
    settings.SECRET_KEY = os.getenv("SECRET_KEY", "")
    settings.SESSION_SECRET_KEY = os.getenv("SESSION_SECRET_KEY", settings.SECRET_KEY)
    settings.LICENSE_MASTER_KEY = os.getenv("LICENSE_MASTER_KEY", "")
    settings.WP_API_KEY = os.getenv("WP_API_KEY", "")
    settings.WP_PHONE_ID = os.getenv("WP_PHONE_ID", "")
    settings.WP_TOKEN = os.getenv("WP_TOKEN", "")
    settings.WP_ACTIVO = env_bool("WP_ACTIVO", False)
    settings.ACCESS_TOKEN_EXPIRE_HOURS = env_int("ACCESS_TOKEN_EXPIRE_HOURS", 12)
    settings.PORT = env_int("PORT", 8000)
    settings.ENVIRONMENT = os.getenv("ENVIRONMENT", "production")
    settings.NO_BROWSER = env_bool("CREDITOSPRO_NO_BROWSER", False)
    settings.PWA_OFFLINE_LIMIT = env_int("PWA_OFFLINE_LIMIT", 500)
    settings.SOFTWARE_NAME = os.getenv("SOFTWARE_NAME", "CreditosPro").strip() or "CreditosPro"
    settings.SOFTWARE_OWNER = os.getenv("SOFTWARE_OWNER", "Johan Garcia").strip() or "Johan Garcia"
    settings.DEFAULT_COMPANY_NAME = os.getenv("DEFAULT_COMPANY_NAME", "ElRusso").strip() or "ElRusso"
    settings.ALLOW_PUBLIC_REGISTRATION = env_bool("ALLOW_PUBLIC_REGISTRATION", False)
    origins = os.getenv("CORS_ORIGINS", "")
    if origins.strip():
        settings.CORS_ORIGINS = [o.strip() for o in origins.split(",") if o.strip()]

    return settings


settings = get_settings()
