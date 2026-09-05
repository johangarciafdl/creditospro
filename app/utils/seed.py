"""Seed inicial opcional para desarrollo."""
import logging
import os

from app.database import SessionLocal, Empresa, Usuario, ConfiguracionApp, Zona
from app.utils.security import get_password_hash
from app.utils.settings import settings

logger = logging.getLogger(__name__)


def seed_data_demo():
    if os.getenv("ENABLE_SEED_DATA", "0").strip().lower() not in {"1", "true", "yes", "on"}:
        return
    initial_password = os.getenv("INITIAL_ADMIN_PASSWORD", "").strip()
    if not initial_password:
        raise RuntimeError("INITIAL_ADMIN_PASSWORD es obligatoria cuando ENABLE_SEED_DATA esta activo")
    db = SessionLocal()
    try:
        if db.query(Empresa).count() > 0:
            return  # ya hay datos, no hacer nada
        emp = Empresa(
            nombre=settings.DEFAULT_COMPANY_NAME,
            ciudad="Medellin",
            activa=True,
        )
        db.add(emp)
        db.flush()
        db.add(ConfiguracionApp(
            empresa_id=emp.id,
            empresa_nombre=settings.DEFAULT_COMPANY_NAME,
            pais="Colombia",
            moneda="COP",
        ))
        db.add(Zona(
            empresa_id=emp.id,
            codigo="Z001",
            nombre="Zona Principal",
            ciudad="Medellin",
            activa=True,
        ))
        user = Usuario(
            empresa_id=emp.id,
            username="admin",
            nombre="Administrador",
            password_hash=get_password_hash(initial_password),
            rol="admin",
            activo=True,
        )
        db.add(user)
        db.commit()
        logger.info("Empresa inicial creada: %s / usuario admin", settings.DEFAULT_COMPANY_NAME)
    except Exception:
        db.rollback()
        logger.exception("Error en seed inicial")
    finally:
        db.close()
