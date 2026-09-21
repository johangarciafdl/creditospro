"""Traslada a Supabase Storage las imagenes que aun tienen los bytes en la base.

Las imagenes vivieron un tiempo en la columna `archivos.datos`. Este script
sube cada una al bucket privado, apunta la fila a su nueva ruta y solo
entonces vacia la columna, de modo que una interrupcion a medias nunca deja
una fila sin bytes en ningun sitio: en el peor caso queda el objeto subido y
la fila todavia apuntando a la base, y la siguiente pasada lo resuelve.

Uso, desde la raiz del repositorio:

    python scripts/mover_imagenes_a_storage.py            # muestra que haria
    python scripts/mover_imagenes_a_storage.py --aplicar  # lo hace

Necesita SUPABASE_URL y SUPABASE_SERVICE_KEY en el entorno o en .env.
"""
import argparse
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
load_dotenv(RAIZ / ".env")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--aplicar", action="store_true",
                        help="hace el traslado; sin esto solo informa")
    parser.add_argument("--limite", type=int, default=0,
                        help="procesar como mucho N imagenes (0 = todas)")
    args = parser.parse_args()

    from app.database import Archivo, SessionLocal
    from app.utils import supabase_storage
    from app.utils.almacen_imagenes import _ruta_en_bucket

    if not supabase_storage.disponible():
        print("Faltan SUPABASE_URL o SUPABASE_SERVICE_KEY; no hay a donde subir.")
        return 1
    print(f"Bucket: {supabase_storage.BUCKET} en {supabase_storage.SUPABASE_URL}")

    db = SessionLocal()
    try:
        consulta = (db.query(Archivo)
                    .filter(Archivo.almacen == "bd", Archivo.datos.isnot(None))
                    .order_by(Archivo.id))
        if args.limite:
            consulta = consulta.limit(args.limite)
        pendientes = consulta.all()

        if not pendientes:
            print("No queda ninguna imagen con los bytes en la base.")
            return 0

        total = sum(a.tamano or 0 for a in pendientes)
        print(f"{len(pendientes)} imagenes, {total/1024:.0f} KB en total")
        if not args.aplicar:
            for a in pendientes[:20]:
                print(f"  empresa {a.empresa_id}  {a.tipo:<8} {a.nombre}  "
                      f"{(a.tamano or 0)/1024:.0f} KB")
            if len(pendientes) > 20:
                print(f"  ... y {len(pendientes) - 20} mas")
            print("\nEjecuta con --aplicar para trasladarlas.")
            return 0

        movidas = fallidas = 0
        for a in pendientes:
            ruta = _ruta_en_bucket(a.empresa_id, a.tipo, a.nombre)
            try:
                supabase_storage.subir(ruta, bytes(a.datos), a.mime)
            except supabase_storage.ErrorStorage as e:
                print(f"  FALLO {a.nombre}: {e}")
                fallidas += 1
                continue
            # Primero apuntar a la ruta nueva, y solo despues soltar los bytes.
            a.almacen = "supabase"
            a.ruta = ruta
            a.datos = None
            db.commit()
            movidas += 1
            print(f"  ok {a.nombre} -> {ruta}")

        print(f"\nTrasladadas {movidas}; fallidas {fallidas}.")
        return 1 if fallidas else 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
