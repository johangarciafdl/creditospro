"""Asigna el logo de una empresa (se muestra en la pantalla de login).

Uso:
    python scripts/set_logo_empresa.py --empresa-id 1 --archivo "C:\\ruta\\logo.png"
"""
import argparse
import shutil
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))
load_dotenv(ROOT_DIR / ".env")

from app.database import Empresa, SessionLocal  # noqa: E402

EXTENSIONES_VALIDAS = {".png", ".jpg", ".jpeg", ".webp", ".svg"}


def main() -> int:
    parser = argparse.ArgumentParser(description="Asignar el logo de una empresa")
    parser.add_argument("--empresa-id", type=int, required=True)
    parser.add_argument("--archivo", required=True, help="Ruta local a la imagen del logo")
    args = parser.parse_args()

    origen = Path(args.archivo)
    if not origen.exists():
        print(f"ERROR: no existe el archivo {origen}")
        return 1
    ext = origen.suffix.lower()
    if ext not in EXTENSIONES_VALIDAS:
        print(f"ERROR: extension no soportada ({ext}). Usa: {', '.join(sorted(EXTENSIONES_VALIDAS))}")
        return 1

    db = SessionLocal()
    try:
        empresa = db.query(Empresa).filter(Empresa.id == args.empresa_id).first()
        if not empresa:
            print("ERROR: empresa no encontrada")
            return 1

        destino_dir = ROOT_DIR / "uploads" / "logos"
        destino_dir.mkdir(parents=True, exist_ok=True)
        nombre_archivo = f"empresa_{empresa.id}{ext}"
        destino = destino_dir / nombre_archivo
        shutil.copyfile(origen, destino)

        empresa.logo_path = nombre_archivo
        db.commit()
        print(f"Logo asignado a {empresa.nombre} (id={empresa.id}): {nombre_archivo}")
        print("Se vera en el login la proxima vez que alguien active/inicie sesion en esa empresa.")
        return 0
    except Exception as exc:
        db.rollback()
        print(f"ERROR: no se pudo asignar el logo: {exc}")
        return 1
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
