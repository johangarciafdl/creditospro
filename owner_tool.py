r"""
CreditosPro OWNER TOOL - Solo para el dueno del software
Guarda este archivo FUERA del repositorio publico (ej: C:\Users\johan\MisTool\)

Requiere la variable de entorno LICENSE_MASTER_KEY con la clave maestra.
"""
import os
import sys
import argparse
import hashlib
import json
import base64
import datetime
import uuid
import socket
from pathlib import Path


def _get_master_secret() -> str:
    key = os.getenv("LICENSE_MASTER_KEY", "").strip()
    if not key:
        print("ERROR: La variable de entorno LICENSE_MASTER_KEY no esta definida.")
        print('Configurala antes de ejecutar el script. Ejemplo:')
        print('  set LICENSE_MASTER_KEY=tu-clave-secreta')
        sys.exit(2)
    return key


def _derive_key(secret: str) -> bytes:
    from cryptography.fernet import Fernet  # noqa: F401  (import diferido)
    key_bytes = hashlib.sha256(secret.encode()).digest()
    return base64.urlsafe_b64encode(key_bytes)


def generate_license(machine_id, empresa_id, empresa_nombre, dias=365):
    from cryptography.fernet import Fernet
    f = Fernet(_derive_key(_get_master_secret()))
    payload = json.dumps({
        "machine_id": machine_id,
        "empresa_id": empresa_id,
        "empresa_nombre": empresa_nombre,
        "issued_at": datetime.datetime.now().isoformat(),
        "expires_at": (datetime.datetime.now() + datetime.timedelta(days=dias)).isoformat(),
        "version": "3.0",
    }).encode()
    token = f.encrypt(payload)
    return "CPRO-" + base64.urlsafe_b64encode(token).decode()


def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="cmd")

    gen = sub.add_parser("generate")
    gen.add_argument("--machine", required=True)
    gen.add_argument("--empresa-id", type=int, required=True)
    gen.add_argument("--empresa", required=True)
    gen.add_argument("--dias", type=int, default=365)

    sub.add_parser("myid")

    args = parser.parse_args()

    if args.cmd == "generate":
        key = generate_license(args.machine, args.empresa_id, args.empresa, args.dias)
        print("\n" + "=" * 60)
        print(f"  Empresa : {args.empresa} (ID: {args.empresa_id})")
        print(f"  Maquina : {args.machine}")
        print(f"  Validez : {args.dias} dias")
        print("=" * 60)
        print("\nLICENSE KEY (copia todo):\n")
        print(key)
        print("\n" + "=" * 60)

        out = Path(f"license_{args.empresa.replace(' ', '_')}.txt")
        out.write_text(key, encoding="utf-8")
        print(f"\nTambien guardada en: {out.absolute()}")

    elif args.cmd == "myid":
        import platform
        parts = [str(uuid.getnode()), socket.gethostname(),
                 platform.processor(), platform.machine(), platform.system()]
        fp = hashlib.sha256("|".join(parts).encode()).hexdigest()[:32].upper()
        print(f"\nMachine ID de este equipo:\n\n  {fp}\n")
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
