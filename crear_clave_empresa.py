"""Genera o rota la clave comercial unica de una empresa.

Uso:
    python crear_clave_empresa.py --empresa-id 1
    python crear_clave_empresa.py --empresa-id 1 --rotar

La clave se muestra una sola vez. La base guarda solo su hash.
"""
import argparse
import sys
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

from app.database import Empresa, SessionLocal  # noqa: E402
from app.utils.company_activation import assign_company_key  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Crear clave de activacion por empresa")
    parser.add_argument("--empresa-id", type=int, required=True)
    parser.add_argument("--rotar", action="store_true", help="Invalida la clave anterior")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        empresa = db.query(Empresa).filter(Empresa.id == args.empresa_id).first()
        if not empresa:
            print("ERROR: empresa no encontrada")
            return 1
        if empresa.activation_key_hash and not args.rotar:
            print("ERROR: la empresa ya tiene una clave. Usa --rotar para reemplazarla.")
            return 1

        key = assign_company_key(db, empresa)
        db.commit()
        print(f"Empresa: {empresa.nombre} (id={empresa.id})")
        print("CLAVE DE ACTIVACION (entregar una sola vez):")
        print(key)
        print(f"Referencia guardada: {empresa.activation_key_hint}")
        return 0
    except Exception as exc:
        db.rollback()
        print(f"ERROR: no se pudo crear la clave: {exc}")
        return 1
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
