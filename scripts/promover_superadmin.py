"""Promueve un usuario existente a superadmin (control de plan por empresa).

No hay forma de otorgar superadmin desde la interfaz web -- es deliberado
(evita que un admin de una empresa se auto-escale). Este script es la unica
via, y debe correrlo el dueno de la plataforma directamente contra la base
de datos, no un admin de una empresa cliente.

Uso:
    python scripts/promover_superadmin.py --empresa-id 1 --username admin1
"""
import argparse
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))
load_dotenv(ROOT_DIR / ".env")

from app.database import SessionLocal, Usuario  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Promover un usuario a superadmin")
    parser.add_argument("--empresa-id", type=int, required=True)
    parser.add_argument("--username", required=True)
    args = parser.parse_args()

    db = SessionLocal()
    try:
        user = db.query(Usuario).filter(
            Usuario.empresa_id == args.empresa_id,
            Usuario.username == args.username.strip().lower(),
        ).first()
        if not user:
            print(f"ERROR: no existe el usuario '{args.username}' en la empresa {args.empresa_id}")
            return 1
        if user.rol == "superadmin":
            print(f"{user.username} ya es superadmin -- nada que hacer.")
            return 0

        rol_anterior = user.rol
        user.rol = "superadmin"
        db.commit()
        print(f"Listo: {user.username} (empresa {args.empresa_id}) paso de '{rol_anterior}' a 'superadmin'.")
        print("Ya puede entrar a /plataforma para gestionar el plan de cada empresa.")
        return 0
    except Exception as exc:
        db.rollback()
        print(f"ERROR: {exc}")
        return 1
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
