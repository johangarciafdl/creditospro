"""
CreditosPro - Crear instalacion para empresa
Uso: python crear_empresa.py --fuente "C:\\ruta\\al\\proyecto" --empresa "Mi Empresa" --id 3
"""
import argparse, shutil, os, secrets
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--fuente", required=True,
                        help="Ruta completa a la carpeta CreditosPro_v2")
    parser.add_argument("--empresa", required=True, help="Nombre de la empresa")
    parser.add_argument("--id", type=int, required=True, help="empresa_id en la base de datos")
    parser.add_argument("--destino", default=".", help="Donde crear la carpeta (default: aqui)")
    parser.add_argument("--database-url", default=None,
                        help="DATABASE_URL para el cliente. Si no se da, se toma de la variable de entorno DATABASE_URL_TEMPLATE.")
    args = parser.parse_args()

    fuente = Path(args.fuente)
    if not fuente.exists():
        print(f"ERROR: No existe la carpeta fuente: {fuente}")
        return

    database_url = args.database_url or os.getenv("DATABASE_URL_TEMPLATE", "").strip()
    if not database_url:
        print("ERROR: Debes pasar --database-url o definir la variable de entorno DATABASE_URL_TEMPLATE.")
        print("Ejemplo: set DATABASE_URL_TEMPLATE=postgresql://user:pass@host:5432/db")
        return

    nombre = f"CreditosPro_{args.empresa.replace(' ', '_')}"
    dest = Path(args.destino) / nombre

    if dest.exists():
        print(f"ERROR: Ya existe: {dest}")
        return

    print(f"Creando: {dest}")
    shutil.copytree(str(fuente), str(dest), ignore=shutil.ignore_patterns(
        '.venv', '__pycache__', '*.pyc', '.git', 'license.key', '.lic_data',
        'creditospro_dev.db', 'backups', '*.zip', '.env'
    ))

    secret_key = secrets.token_urlsafe(48)
    session_key = secrets.token_urlsafe(48)

    env = f"""# CreditosPro - {args.empresa}
DATABASE_URL={database_url}
SECRET_KEY={secret_key}
SESSION_SECRET_KEY={session_key}
PORT=8000
EMPRESA_ID={args.id}
EMPRESA_NOMBRE={args.empresa}
ENVIRONMENT=production
LICENSE_MASTER_KEY=
"""
    (dest / ".env").write_text(env, encoding="utf-8")
    print(f"\nListo: {dest.absolute()}")
    print("\nPasos:")
    print(f"  1. Entrega la carpeta '{nombre}' al cliente")
    print(f"  2. Edita el .env y coloca LICENSE_MASTER_KEY antes de entregar")
    print(f"  3. Cliente instala: pip install -r requirements.txt")
    print(f"  4. Cliente corre: python run.py")
    print(f"  5. Cliente te envia su Machine ID")
    print(f"  6. Tu corres: python owner_tool.py generate --machine XXXX --empresa-id {args.id} --empresa \"{args.empresa}\"")
    print(f"  7. Das la key al cliente -> pega en pantalla de activacion -> listo")


if __name__ == "__main__":
    main()
