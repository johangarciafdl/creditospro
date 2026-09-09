"""Crea un usuario superadmin (dueno de la plataforma), sin empresa asociada.

El superadmin administra TODAS las empresas desde /plataforma -- no es un
usuario de ninguna empresa cliente, por eso su empresa_id queda en NULL
(a diferencia de admin/supervisor/cobrador, que siempre pertenecen a una).
Entra por /plataforma/login, no por /auth/login -- no necesita activar
ninguna clave comercial.

No hay forma de crear esta cuenta desde la interfaz web -- es deliberado,
evita que un admin de cualquier empresa se la asigne a si mismo. Este
script es la unica via, y debe correrlo el dueno de la plataforma
directamente contra la base de datos.

Uso:
    python scripts/crear_superadmin.py --username johan_admin --nombre "Johan Garcia"
    (pide la contrasena de forma oculta; o pasala con --password para uso no interactivo)
"""
import argparse
import getpass
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))
load_dotenv(ROOT_DIR / ".env")

from app.database import SessionLocal, Usuario  # noqa: E402
from app.utils.password_policy import validar_password  # noqa: E402
from app.utils.security import get_password_hash  # noqa: E402
from fastapi import HTTPException  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Crear un usuario superadmin de plataforma")
    parser.add_argument("--username", required=True)
    parser.add_argument("--nombre", required=True)
    parser.add_argument("--password", help="Si se omite, se pide de forma oculta")
    args = parser.parse_args()

    username_clean = args.username.strip().lower()
    password = args.password or getpass.getpass("Contrasena para el superadmin: ")

    try:
        validar_password(password)
    except HTTPException as exc:
        print(f"ERROR: {exc.detail}")
        return 1

    db = SessionLocal()
    try:
        existente = db.query(Usuario).filter(Usuario.username == username_clean).first()
        if existente:
            print(f"ERROR: el username '{username_clean}' ya existe (empresa_id={existente.empresa_id})")
            return 1

        user = Usuario(
            empresa_id=None,
            username=username_clean,
            nombre=args.nombre.strip(),
            password_hash=get_password_hash(password),
            rol="superadmin",
            activo=True,
        )
        db.add(user)
        db.commit()
        print(f"Listo: superadmin '{username_clean}' creado.")
        print("Entra en /plataforma/login (no necesita clave de empresa).")
        return 0
    except Exception as exc:
        db.rollback()
        print(f"ERROR: {exc}")
        return 1
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
