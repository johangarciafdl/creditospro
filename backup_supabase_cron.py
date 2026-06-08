#!/usr/bin/env python3
"""
Wrapper para backups periodicos de Supabase/PostgreSQL.

Uso:
    python backup_supabase_cron.py
    python backup_supabase_cron.py --retention-days 30

El script:
1. Crea un dump SQL/JSON de todas las tablas
2. Lo comprime con gzip
3. Lo sube opcionalmente a S3/R2 (configurable via env)
4. Borra backups con mas de N dias de antiguedad

Instalar como cron (Linux):
    # Todos los dias a las 3 AM, con 30 dias de retencion
    0 3 * * * /usr/bin/python3 /app/backup_supabase_cron.py --retention-days 30 >> /var/log/creditospro_backup.log 2>&1

Instalar como scheduled task (Windows):
    schtasks /create /tn "CreditosPro Backup" /tr "python C:\app\backup_supabase_cron.py --retention-days 30" /sc daily /st 03:00
"""
import argparse
import os
import subprocess
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description="Backup periodico de CreditosPro")
    parser.add_argument(
        "--retention-days", type=int, default=int(os.getenv("BACKUP_RETENTION_DAYS", "30")),
        help="Dias de retencion (default: 30)",
    )
    parser.add_argument(
        "--output-dir", default=os.getenv("BACKUP_DIR", "./backups"),
        help="Directorio de salida (default: ./backups)",
    )
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_lines = []

    def log(msg):
        line = f"[{datetime.now().isoformat(timespec='seconds')}] {msg}"
        print(line)
        log_lines.append(line)

    log(f"Iniciando backup (retencion={args.retention_days}d)")

    # 1) Backup via el script existente
    backup_dir = output_dir / f"backup_{timestamp}"
    cmd = [sys.executable, "backup_supabase.py", "--output-dir", str(backup_dir)]
    log(f"Ejecutando: {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        log(f"ERROR en backup_supabase.py: {result.stderr[:500]}")
        sys.exit(1)
    log("Backup generado OK")

    # 2) Comprimir
    archive = output_dir / f"backup_{timestamp}.tar.gz"
    subprocess.run(
        ["tar", "-czf", str(archive), "-C", str(output_dir), backup_dir.name],
        check=True,
    )
    log(f"Comprimido: {archive}")

    # 3) Subir a S3/R2 si esta configurado
    s3_bucket = os.getenv("BACKUP_S3_BUCKET")
    s3_endpoint = os.getenv("BACKUP_S3_ENDPOINT")
    if s3_bucket:
        try:
            import boto3
            client = boto3.client("s3", endpoint_url=s3_endpoint)
            client.upload_file(str(archive), s3_bucket, archive.name)
            log(f"Subido a s3://{s3_bucket}/{archive.name}")
        except Exception as e:
            log(f"WARN: fallo subiendo a S3: {e}")

    # 4) Limpiar backups antiguos
    cutoff = datetime.now() - timedelta(days=args.retention_days)
    removed = 0
    for f in output_dir.glob("backup_*.tar.gz"):
        try:
            # Extraer timestamp del nombre
            ts_str = f.stem.replace("backup_", "").replace(".tar", "")
            file_dt = datetime.strptime(ts_str, "%Y%m%d_%H%M%S")
            if file_dt < cutoff:
                f.unlink()
                # Tambien borrar carpeta descomprimida
                folder = output_dir / f.stem
                if folder.exists():
                    import shutil
                    shutil.rmtree(folder)
                removed += 1
        except (ValueError, OSError):
            continue
    log(f"Limpieza: {removed} backups antiguos eliminados")

    # 5) Limpiar carpeta del backup actual (ya esta en .tar.gz)
    if backup_dir.exists():
        import shutil
        shutil.rmtree(backup_dir)

    log(f"Backup completado en {time.time() - time.process_time():.1f}s")


if __name__ == "__main__":
    main()
