"""
CreditosPro — Crear instalacion para empresa
Uso: python crear_empresa.py --fuente "C:\ruta\al\proyecto" --empresa "Mi Empresa" --id 3
"""
import argparse, shutil
from pathlib import Path

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--fuente", required=True,
                        help="Ruta completa a la carpeta CreditosPro_v2 (ej: C:\\Users\\johan\\Downloads\\CreditosPro_v3_final\\CreditosPro_v2_seguro_base\\CreditosPro_v2)")
    parser.add_argument("--empresa", required=True, help="Nombre de la empresa")
    parser.add_argument("--id", type=int, required=True, help="empresa_id en Supabase")
    parser.add_argument("--destino", default=".", help="Donde crear la carpeta (default: aqui)")
    args = parser.parse_args()

    fuente = Path(args.fuente)
    if not fuente.exists():
        print(f"ERROR: No existe la carpeta fuente: {fuente}")
        print("Especifica la ruta completa con --fuente")
        return

    nombre = f"CreditosPro_{args.empresa.replace(' ','_')}"
    dest = Path(args.destino) / nombre

    if dest.exists():
        print(f"ERROR: Ya existe: {dest}")
        return

    print(f"Creando: {dest}")
    shutil.copytree(str(fuente), str(dest), ignore=shutil.ignore_patterns(
        '.venv', '__pycache__', '*.pyc', '.git', 'license.key', '.lic_data',
        'creditospro_dev.db', 'backups', '*.zip'
    ))

    env = f"""# CreditosPro — {args.empresa}
DATABASE_URL=postgresql://postgres.kfwlrjrysapcgkdvicss:Jo681192*creditos@aws-1-us-east-1.pooler.supabase.com:5432/postgres
SECRET_KEY=creditospro-super-secreto-2024
SESSION_SECRET_KEY=creditospro-session-2024
PORT=8000
EMPRESA_ID={args.id}
EMPRESA_NOMBRE={args.empresa}
ENVIRONMENT=production
"""
    (dest / ".env").write_text(env, encoding="utf-8")
    print(f"\n✅ Listo: {dest.absolute()}")
    print(f"\nPasos:")
    print(f"  1. Entrega la carpeta '{nombre}' al cliente")
    print(f"  2. Cliente instala: pip install -r requirements.txt")
    print(f"  3. Cliente corre: python run.py")
    print(f"  4. Cliente te envia su Machine ID")
    print(f"  5. Tu corres: python owner_tool.py generate --machine XXXX --empresa-id {args.id} --empresa \"{args.empresa}\"")
    print(f"  6. Das la key al cliente → pega en pantalla de activacion → listo")

if __name__ == "__main__":
    main()
