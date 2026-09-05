"""
Backup logico de CreditosPro para Supabase/PostgreSQL.

Genera una carpeta local con:
- JSON por tabla, util para restauraciones controladas.
- CSV por tabla, util para revisar datos en Excel.
- manifest.json con conteos y fecha del respaldo.

Uso:
    python backup_supabase.py
"""
from __future__ import annotations

import csv
import datetime as dt
import argparse
import hashlib
import json
import os
from decimal import Decimal
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from sqlalchemy import create_engine, inspect, text


BASE_DIR = Path(__file__).resolve().parent
BACKUP_DIR = BASE_DIR / "backups"
TABLES = [
    "empresas",
    "usuarios",
    "zonas",
    "usuario_zonas",
    "clientes",
    "prestamos",
    "cuotas",
    "cobros",
    "configuracion",
    "notificaciones_wp",
    "audit_log",
    "licencias_activadas",
]


def json_default(value: Any) -> Any:
    if isinstance(value, (dt.datetime, dt.date, dt.time)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    return str(value)


def get_database_url() -> str:
    load_dotenv(BASE_DIR / ".env")
    url = os.getenv("DATABASE_URL")
    if not url:
        raise RuntimeError("No se encontro DATABASE_URL en el entorno ni en .env")
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)
    return url


def get_primary_key_order(inspector, table_name: str) -> str:
    pk = inspector.get_pk_constraint(table_name).get("constrained_columns") or []
    if pk:
        cols = ", ".join(f'"{col}"' for col in pk)
        return f" ORDER BY {cols}"
    return ""


def write_json(path: Path, rows: list[dict[str, Any]]) -> None:
    path.write_text(
        json.dumps(rows, ensure_ascii=False, indent=2, default=json_default),
        encoding="utf-8",
    )


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    fieldnames = list(rows[0].keys()) if rows else []
    with path.open("w", newline="", encoding="utf-8-sig") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: json_default(value) if value is not None else "" for key, value in row.items()})


def main() -> None:
    parser = argparse.ArgumentParser(description="Backup logico verificado de CreditosPro")
    parser.add_argument("--output-dir", default=None, help="Directorio exacto del backup")
    args = parser.parse_args()
    stamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = Path(args.output_dir) if args.output_dir else BACKUP_DIR / f"backup_{stamp}"
    json_dir = output_dir / "json"
    csv_dir = output_dir / "csv"
    json_dir.mkdir(parents=True, exist_ok=True)
    csv_dir.mkdir(parents=True, exist_ok=True)

    engine = create_engine(get_database_url(), pool_pre_ping=True)
    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names(schema="public"))
    manifest: dict[str, Any] = {
        "created_at": dt.datetime.now().isoformat(timespec="seconds"),
        "database": "Supabase/PostgreSQL",
        "status": "started",
        "tables": {},
        "files": {},
    }

    with engine.connect() as conn:
        for table_name in TABLES:
            if table_name not in existing_tables:
                manifest["tables"][table_name] = {"status": "missing", "rows": 0}
                print(f"[SKIP] {table_name}: no existe")
                continue

            order_by = get_primary_key_order(inspector, table_name)
            result = conn.execute(text(f'SELECT * FROM public."{table_name}"{order_by}'))
            rows = [dict(row._mapping) for row in result]

            write_json(json_dir / f"{table_name}.json", rows)
            write_csv(csv_dir / f"{table_name}.csv", rows)

            manifest["tables"][table_name] = {"status": "ok", "rows": len(rows)}
            print(f"[OK] {table_name}: {len(rows)} filas")

    for path in sorted(output_dir.rglob("*")):
        if path.is_file() and path.name != "manifest.json":
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            manifest["files"][str(path.relative_to(output_dir))] = {
                "bytes": path.stat().st_size,
                "sha256": digest,
            }
    manifest["status"] = "verified"
    write_json(output_dir / "manifest.json", [manifest])
    print()
    print(f"Backup creado en: {output_dir}")


if __name__ == "__main__":
    main()
