#!/usr/bin/env python3
"""
Script para activar licencia directamente en .env

Uso:
    python activar_licencia.py --key "CPRO-..."
    o
    set CREDITOSPRO_LICENSE_KEY=CPRO-...
    python activar_licencia.py
"""
import argparse
import os
import sys
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


def activar_licencia(license_key: str) -> None:
    """Activa la licencia en .env"""
    env_file = Path(__file__).parent / ".env"
    if not env_file.exists():
        env_file.write_text("", encoding="utf-8")

    try:
        content = env_file.read_text(encoding="utf-8")

        if "LICENSE_KEY=" in content:
            lines = content.split("\n")
            for i, line in enumerate(lines):
                if line.startswith("LICENSE_KEY="):
                    lines[i] = f"LICENSE_KEY={license_key}"
            content = "\n".join(lines)
        else:
            content += f"\n\n# Licencia activada\nLICENSE_KEY={license_key}\n"

        env_file.write_text(content, encoding="utf-8")

        print("\n" + "=" * 70)
        print("LICENCIA ACTIVADA EXITOSAMENTE")
        print("=" * 70)
        print(f"\nLicencia guardada en: {env_file}")
        print("\nReinicia el servidor para que surta efecto\n")

    except OSError as e:
        print(f"Error de E/S al actualizar .env: {e}")
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(description="Activa una licencia en el archivo .env")
    parser.add_argument(
        "--key",
        default=None,
        help="License key. Si no se pasa, se intenta leer de la variable CREDITOSPRO_LICENSE_KEY.",
    )
    args = parser.parse_args()

    license_key = (args.key or os.getenv("CREDITOSPRO_LICENSE_KEY", "")).strip()
    if not license_key:
        print("ERROR: No se proporciono license key.")
        print("Uso: python activar_licencia.py --key \"CPRO-...\"")
        print('  o: set CREDITOSPRO_LICENSE_KEY=CPRO-... y luego ejecuta el script')
        sys.exit(2)

    print("\n" + "=" * 70)
    print("SCRIPT: CreditosPro - Activar Licencia")
    print("=" * 70)
    activar_licencia(license_key)


if __name__ == "__main__":
    main()
