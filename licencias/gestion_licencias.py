#!/usr/bin/env python3
"""Gestión de licencias por empresa y equipo.

Ejemplos:
  python licencias\gestion_licencias.py myid
  python licencias\gestion_licencias.py generar --empresa "ElRusso" --equipo "PC-OFICINA-01" --empresa-id 1 --dias 365
  python licencias\gestion_licencias.py validar --empresa "ElRusso" --equipo "PC-OFICINA-01"
  python licencias\gestion_licencias.py registrar --empresa "ElRusso" --equipo "PC-OFICINA-01" --machine-id "ABC123" --licencia "CPRO-..." --vencimiento "2027-08-16"
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

try:
    from dotenv import load_dotenv
    load_dotenv(ROOT_DIR / ".env")
except Exception:
    pass

LICENCIAS_DIR = ROOT_DIR / "licencias"


def slugify(value: str) -> str:
    value = (value or "sin-nombre").strip()
    value = re.sub(r"[^A-Za-z0-9._-]+", "_", value)
    value = value.strip("._ ")
    return value or "sin-nombre"


def empresa_dir(empresa: str) -> Path:
    path = LICENCIAS_DIR / slugify(empresa)
    path.mkdir(parents=True, exist_ok=True)
    return path


def equipo_dir(empresa: str, equipo: str) -> Path:
    path = empresa_dir(empresa) / slugify(equipo)
    path.mkdir(parents=True, exist_ok=True)
    return path


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content.strip() + "\n", encoding="utf-8")


def open_or_create_machine_id(empresa: str, equipo: str, machine_id: str) -> None:
    write_text(equipo_dir(empresa, equipo) / "machine_id.txt", machine_id)


def generate_license_for_equipo(empresa: str, equipo: str, empresa_id: int, dias: int = 365, machine_id: str | None = None) -> dict:
    if machine_id is None:
        from license_manager import get_fingerprint
        machine_id = get_fingerprint()

    from owner_tool import generate_license

    key = generate_license(machine_id=machine_id, empresa_id=empresa_id, empresa_nombre=empresa, dias=dias)
    vencimiento = (datetime.now() + timedelta(days=dias)).date().isoformat()

    base_dir = equipo_dir(empresa, equipo)
    write_text(base_dir / "machine_id.txt", machine_id)
    write_text(base_dir / "licencia.txt", key)
    write_text(base_dir / "vencimiento.txt", vencimiento)

    metadata = {
        "empresa": empresa,
        "empresa_id": empresa_id,
        "equipo": equipo,
        "machine_id": machine_id,
        "licencia": key,
        "vencimiento": vencimiento,
        "dias": dias,
        "created_at": datetime.now().isoformat(timespec="seconds"),
    }
    (base_dir / "metadata.json").write_text(json.dumps(metadata, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    return metadata


def registrar_licencia(empresa: str, equipo: str, machine_id: str, licencia: str, vencimiento: str) -> dict:
    base_dir = equipo_dir(empresa, equipo)
    write_text(base_dir / "machine_id.txt", machine_id)
    write_text(base_dir / "licencia.txt", licencia)
    write_text(base_dir / "vencimiento.txt", vencimiento)

    metadata = {
        "empresa": empresa,
        "equipo": equipo,
        "machine_id": machine_id,
        "licencia": licencia,
        "vencimiento": vencimiento,
        "created_at": datetime.now().isoformat(timespec="seconds"),
    }
    (base_dir / "metadata.json").write_text(json.dumps(metadata, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return metadata


def listar_licencias() -> list[dict]:
    items = []
    if not LICENCIAS_DIR.exists():
        return items
    for empresa_dir_path in sorted(LICENCIAS_DIR.iterdir()):
        if not empresa_dir_path.is_dir():
            continue
        for equipo_dir_path in sorted(empresa_dir_path.iterdir()):
            if not equipo_dir_path.is_dir():
                continue
            metadata_path = equipo_dir_path / "metadata.json"
            if metadata_path.exists():
                try:
                    data = json.loads(metadata_path.read_text(encoding="utf-8"))
                    items.append(data)
                except Exception:
                    pass
    return items


def validar_equipo(empresa: str, equipo: str) -> dict:
    base_dir = equipo_dir(empresa, equipo)
    licencia_path = base_dir / "licencia.txt"
    if not licencia_path.exists():
        return {"valid": False, "error": f"No existe licencia para {empresa} / {equipo}"}

    from license_manager import validate_license

    licencia = licencia_path.read_text(encoding="utf-8").strip()
    return validate_license(licencia)


def cmd_myid() -> None:
    from license_manager import get_fingerprint
    print(get_fingerprint())


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Administración de licencias por empresa y equipo.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("myid", help="Muestra el Machine ID del equipo actual")

    gen = subparsers.add_parser("generar", help="Genera y guarda una licencia para una empresa y equipo")
    gen.add_argument("--empresa", required=True)
    gen.add_argument("--equipo", required=True)
    gen.add_argument("--empresa-id", required=True, type=int)
    gen.add_argument("--machine-id", default=None)
    gen.add_argument("--dias", default=365, type=int)

    reg = subparsers.add_parser("registrar", help="Registra una licencia ya creada por empresa y equipo")
    reg.add_argument("--empresa", required=True)
    reg.add_argument("--equipo", required=True)
    reg.add_argument("--machine-id", required=True)
    reg.add_argument("--licencia", required=True)
    reg.add_argument("--vencimiento", required=True)

    val = subparsers.add_parser("validar", help="Valida la licencia registrada para un equipo")
    val.add_argument("--empresa", required=True)
    val.add_argument("--equipo", required=True)

    lst = subparsers.add_parser("listar", help="Lista las licencias registradas")
    _ = lst

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    if args.command == "myid":
        cmd_myid()
        return 0

    if args.command == "generar":
        if not ROOT_DIR.joinpath(".env").exists():
            print("No existe .env en la raíz del proyecto. Configúralo antes de generar licencias.")
            return 2
        metadata = generate_license_for_equipo(
            empresa=args.empresa,
            equipo=args.equipo,
            empresa_id=args.empresa_id,
            dias=args.dias,
            machine_id=args.machine_id,
        )
        print(json.dumps(metadata, indent=2, ensure_ascii=False))
        return 0

    if args.command == "registrar":
        metadata = registrar_licencia(
            empresa=args.empresa,
            equipo=args.equipo,
            machine_id=args.machine_id,
            licencia=args.licencia,
            vencimiento=args.vencimiento,
        )
        print(json.dumps(metadata, indent=2, ensure_ascii=False))
        return 0

    if args.command == "validar":
        result = validar_equipo(args.empresa, args.equipo)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result.get("valid") else 1

    if args.command == "listar":
        for item in listar_licencias():
            print(json.dumps(item, ensure_ascii=False, indent=2))
        return 0

    parser.print_help()
    return 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:  # pragma: no cover - CLI friendly error
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
