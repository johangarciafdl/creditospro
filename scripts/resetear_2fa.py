"""Quita la verificacion en dos pasos de un usuario que perdio el celular.

Uso:
    python scripts/resetear_2fa.py --username admin --empresa-id 1
    python scripts/resetear_2fa.py --username johan_admin --superadmin

Para cuando un administrador pierde el celular y tambien sus codigos de
respaldo. Solo lo puede correr quien tiene acceso al servidor y a la base (el
dueño de la plataforma): no hay forma de hacerlo desde la aplicacion, a
proposito -- si la hubiera, quien robe una contraseña la usaria.

Al entrar de nuevo, el administrador tendra que volver a activarla.
"""
import argparse
import sys
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")
sys.path.insert(0, str(BASE_DIR))

from app.database import SessionLocal, Usuario  # noqa: E402
from app.utils.audit import log_action  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Quitar la verificacion en dos pasos de un usuario")
    parser.add_argument("--username", required=True)
    grupo = parser.add_mutually_exclusive_group(required=True)
    grupo.add_argument("--empresa-id", type=int)
    grupo.add_argument("--superadmin", action="store_true")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        q = db.query(Usuario).filter(Usuario.username == args.username.strip().lower())
        q = (q.filter(Usuario.empresa_id.is_(None), Usuario.rol == "superadmin")
             if args.superadmin else q.filter(Usuario.empresa_id == args.empresa_id))
        user = q.first()
        if not user:
            print("ERROR: usuario no encontrado")
            return 1
        if not user.two_factor_enabled and not user.two_factor_secret:
            print("El usuario no tiene verificacion en dos pasos. Nada que hacer.")
            return 0
        user.two_factor_enabled = False
        user.two_factor_secret = None
        user.two_factor_backup_hashes = None
        db.commit()
        log_action(db, user, "2fa_reseteado", "auth",
                   f"username={user.username} via scripts/resetear_2fa.py")
        print(f"Listo: {user.username} ya no tiene verificacion en dos pasos.")
        print("Al entrar de nuevo tendra que activarla otra vez.")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
