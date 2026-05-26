"""Deja la base en modo una sola empresa: ElRusso.

Hace backup automatico si DATABASE_URL apunta a SQLite en archivo.
Ejecutar:
    python normalizar_empresa_elrusso.py
"""
from pathlib import Path
import os
import shutil

from dotenv import load_dotenv


BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")
if os.getenv("FORCE_LOCAL_SQLITE", "0").strip() == "1":
    os.environ["DATABASE_URL"] = f"sqlite:///{BASE_DIR / 'creditospro_dev.db'}"
else:
    os.environ.setdefault("DATABASE_URL", f"sqlite:///{BASE_DIR / 'creditospro_dev.db'}")
os.environ.setdefault("SECRET_KEY", "local-normalize-secret")
os.environ.setdefault("SESSION_SECRET_KEY", "local-normalize-session-secret")

from app.database import (  # noqa: E402
    SessionLocal,
    Empresa,
    Usuario,
    Zona,
    Cliente,
    Prestamo,
    Cuota,
    Cobro,
    NotificacionWP,
    ConfiguracionApp,
    SQLALCHEMY_DATABASE_URL,
    engine,
)
from app.utils.security import get_password_hash  # noqa: E402
from sqlalchemy import text  # noqa: E402


TARGET_NAME = os.getenv("DEFAULT_COMPANY_NAME", "ElRusso").strip() or "ElRusso"


def backup_sqlite():
    url = SQLALCHEMY_DATABASE_URL
    if not url.startswith("sqlite:///"):
        return None
    raw = url.replace("sqlite:///", "", 1)
    db_path = Path(raw)
    if not db_path.is_absolute():
        db_path = BASE_DIR / db_path
    if not db_path.exists() or db_path.name == ":memory:":
        return None
    backup_dir = BASE_DIR / "backups"
    backup_dir.mkdir(exist_ok=True)
    backup_path = backup_dir / f"{db_path.stem}_antes_elrusso{db_path.suffix}"
    shutil.copy2(db_path, backup_path)
    return backup_path


def ensure_sqlite_columns():
    if not SQLALCHEMY_DATABASE_URL.startswith("sqlite:///"):
        return
    additions = {
        "zonas": {
            "bot_phone": "VARCHAR(20)",
            "bot_apikey": "VARCHAR(100)",
            "bot_activo": "BOOLEAN DEFAULT 0",
            "lat": "FLOAT",
            "lng": "FLOAT",
        },
        "clientes": {
            "telefono2": "VARCHAR(20)",
            "codeudor_nombre": "VARCHAR(200)",
            "codeudor_cedula": "VARCHAR(20)",
            "codeudor_tel": "VARCHAR(20)",
            "lat": "FLOAT",
            "lng": "FLOAT",
        },
        "cobros": {
            "lat_cobro": "FLOAT",
            "lng_cobro": "FLOAT",
            "usuario_id": "INTEGER",
        },
    }
    with engine.begin() as conn:
        for table, columns in additions.items():
            existing = {row[1] for row in conn.execute(text(f"PRAGMA table_info({table})")).fetchall()}
            for name, ddl in columns.items():
                if name not in existing:
                    conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}"))


def unique_value(db, model, column_name, empresa_id, desired, current_id=None):
    base = (desired or "").strip() or "SIN-DATO"
    value = base
    n = 2
    column = getattr(model, column_name)
    while True:
        q = db.query(model).filter(model.empresa_id == empresa_id, column == value)
        if current_id is not None:
            q = q.filter(model.id != current_id)
        if not q.first():
            return value
        value = f"{base}-{n}"
        n += 1


def main():
    backup = backup_sqlite()
    ensure_sqlite_columns()
    db = SessionLocal()
    try:
        empresas = db.query(Empresa).order_by(Empresa.id).all()
        if not empresas:
            empresa = Empresa(nombre=TARGET_NAME, ciudad="Medellin", pais="Colombia", activa=True)
            db.add(empresa)
            db.flush()
        else:
            empresa = next((e for e in empresas if (e.nombre or "").lower() == TARGET_NAME.lower()), empresas[0])

        empresa.nombre = TARGET_NAME
        empresa.ciudad = empresa.ciudad or "Medellin"
        empresa.pais = empresa.pais or "Colombia"
        empresa.moneda = empresa.moneda or "COP"
        empresa.activa = True
        target_id = empresa.id

        for usuario in db.query(Usuario).all():
            usuario.empresa_id = target_id
            usuario.username = unique_value(db, Usuario, "username", target_id, usuario.username, usuario.id)
        for zona in db.query(Zona).all():
            zona.empresa_id = target_id
            zona.codigo = unique_value(db, Zona, "codigo", target_id, zona.codigo or "ZONA", zona.id)
        for cliente in db.query(Cliente).all():
            cliente.empresa_id = target_id
            cliente.cedula = unique_value(db, Cliente, "cedula", target_id, cliente.cedula or f"CLIENTE-{cliente.id}", cliente.id)
        for model in (Prestamo, Cuota, Cobro, NotificacionWP):
            db.query(model).update({model.empresa_id: target_id}, synchronize_session=False)

        db.query(ConfiguracionApp).filter(ConfiguracionApp.empresa_id != target_id).delete(synchronize_session=False)
        config = db.query(ConfiguracionApp).filter(ConfiguracionApp.empresa_id == target_id).first()
        if not config:
            config = ConfiguracionApp(empresa_id=target_id)
            db.add(config)
        config.empresa_nombre = TARGET_NAME
        config.pais = config.pais or "Colombia"
        config.moneda = config.moneda or "COP"

        if not db.query(Zona).filter(Zona.empresa_id == target_id).first():
            db.add(Zona(empresa_id=target_id, codigo="Z001", nombre="Zona Principal", ciudad="Medellin", activa=True))
        if not db.query(Usuario).filter(Usuario.empresa_id == target_id, Usuario.activo == True).first():
            db.add(Usuario(
                empresa_id=target_id,
                username="admin",
                nombre="Administrador",
                hashed_password=get_password_hash("Admin123"),
                rol="admin",
                activo=True,
            ))

        db.query(Empresa).filter(Empresa.id != target_id).delete(synchronize_session=False)
        db.commit()

        print(f"OK: base normalizada a una sola empresa: {TARGET_NAME} (id={target_id})")
        if backup:
            print(f"Backup creado: {backup}")
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
