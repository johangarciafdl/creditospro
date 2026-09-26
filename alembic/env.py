import os
from pathlib import Path
from logging.config import fileConfig

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

from alembic import context
from sqlalchemy import engine_from_config, pool

from app.database import Base
from app.utils.url_bd import normalizar as normalizar_url_bd

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def get_url():
    url = os.getenv("DATABASE_URL")
    if not url:
        raise RuntimeError("DATABASE_URL es obligatoria para migraciones")
    # El mismo ayudante que usa la aplicacion: si alembic y la app
    # resolvieran controladores distintos, las migraciones se aplicarian
    # por un camino que nadie prueba.
    return normalizar_url_bd(url)


def run_migrations_offline():
    context.configure(
        url=get_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online():
    configuration = config.get_section(config.config_ini_section) or {}
    configuration["sqlalchemy.url"] = get_url()
    connectable = engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
