#!/usr/bin/env python3
"""
CreditosPro License Renewal Tool
Renueva licencias anuales de forma automatizada.

Modo automático (recomendado):
    python renewal_license.py --auto
    
Modo manual:
    python renewal_license.py --machine <ID> --empresa-id <ID> --empresa <nombre> --dias 365

Requisitos:
    - LICENSE_MASTER_KEY configurada en .env
    - CREDITOSPRO_LICENSE_KEY configurada en .env (para modo --auto)
"""
import os
import sys
import argparse
import json
import datetime
from pathlib import Path
from dotenv import load_dotenv


def _load_env():
    """Carga variables de .env"""
    env_path = Path(__file__).parent / ".env"
    if env_path.exists():
        load_dotenv(env_path)
    else:
        print("⚠️  Archivo .env no encontrado en la raiz del proyecto.")
        sys.exit(1)


def generate_license(machine_id, empresa_id, empresa_nombre, dias=365):
    """Genera una licencia firmada con la clave maestra"""
    import hashlib
    import base64
    from cryptography.fernet import Fernet
    
    master_key = os.getenv("LICENSE_MASTER_KEY", "").strip()
    if not master_key:
        print("❌ ERROR: LICENSE_MASTER_KEY no está configurada en .env")
        sys.exit(1)
    
    key_bytes = hashlib.sha256(master_key.encode()).digest()
    f = Fernet(base64.urlsafe_b64encode(key_bytes))
    
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


def validate_license(license_key: str) -> dict:
    """Valida una licencia y extrae sus datos"""
    import hashlib
    import base64
    from cryptography.fernet import Fernet
    
    try:
        master_key = os.getenv("LICENSE_MASTER_KEY", "").strip()
        if not master_key:
            return {"valid": False, "error": "LICENSE_MASTER_KEY no configurada"}
        
        key_bytes = hashlib.sha256(master_key.encode()).digest()
        f = Fernet(base64.urlsafe_b64encode(key_bytes))
        
        key_clean = license_key.strip()
        raw = key_clean[5:] if key_clean.startswith("CPRO-") else key_clean
        pad = len(raw) % 4
        if pad:
            raw += "=" * (4 - pad)
        
        token = base64.urlsafe_b64decode(raw.encode())
        payload = json.loads(f.decrypt(token).decode())
        
        expires = datetime.datetime.fromisoformat(payload["expires_at"])
        days_left = (expires - datetime.datetime.now()).days
        
        return {
            "valid": True,
            "data": payload,
            "days_left": days_left,
            "expires": expires.strftime("%Y-%m-%d")
        }
    except Exception as e:
        return {"valid": False, "error": str(e)}


def get_fingerprint() -> str:
    """Obtiene el Machine ID del equipo actual"""
    import platform
    import socket
    import uuid
    import hashlib
    
    override = os.getenv("CREDITOSPRO_MACHINE_ID", "").strip()
    if override:
        return override.upper()
    
    parts = [str(uuid.getnode()), socket.gethostname(),
             platform.processor(), platform.machine(), platform.system()]
    return hashlib.sha256("|".join(parts).encode()).hexdigest()[:32].upper()


def save_to_env(license_key: str) -> bool:
    """Guarda la licencia en .env"""
    env_path = Path(__file__).parent / ".env"
    if not env_path.exists():
        print(f"❌ No se encontró {env_path}")
        return False
    
    content = env_path.read_text(encoding="utf-8")
    
    # Reemplazar o agregar CREDITOSPRO_LICENSE_KEY
    if "CREDITOSPRO_LICENSE_KEY=" in content:
        lines = content.split("\n")
        new_lines = []
        for line in lines:
            if line.startswith("CREDITOSPRO_LICENSE_KEY="):
                new_lines.append(f"CREDITOSPRO_LICENSE_KEY={license_key}")
            else:
                new_lines.append(line)
        content = "\n".join(new_lines)
    else:
        content += f"\n\nCREDITOSPRO_LICENSE_KEY={license_key}\n"
    
    env_path.write_text(content, encoding="utf-8")
    return True


def save_to_registry(machine_id: str, empresa_id: int, empresa_nombre: str, license_key: str) -> bool:
    """Guarda la licencia en licencias/empresas.json"""
    registro_path = Path(__file__).parent / "licencias" / "empresas.json"
    
    if not registro_path.parent.exists():
        registro_path.parent.mkdir(exist_ok=True)
    
    if registro_path.exists():
        registros = json.loads(registro_path.read_text(encoding="utf-8"))
    else:
        registros = {}
    
    empresa_key = f"empresa_{empresa_id}"
    registros[empresa_key] = {
        "empresa_id": empresa_id,
        "empresa_nombre": empresa_nombre,
        "machine_id": machine_id,
        "license_key": license_key,
        "renewed_at": datetime.datetime.now().isoformat(),
    }
    
    registro_path.write_text(json.dumps(registros, indent=2, ensure_ascii=False), encoding="utf-8")
    return True


def auto_renew():
    """Renueva automáticamente la licencia actual"""
    print("\n🔄 Modo automático: Renovando licencia actual...")
    
    # Obtener licencia actual
    current_key = os.getenv("CREDITOSPRO_LICENSE_KEY", "").strip()
    if not current_key:
        print("❌ CREDITOSPRO_LICENSE_KEY no está configurada en .env")
        sys.exit(1)
    
    # Validar y extraer datos
    result = validate_license(current_key)
    if not result.get("valid"):
        print(f"❌ Licencia actual inválida: {result.get('error')}")
        sys.exit(1)
    
    data = result["data"]
    machine_id = data["machine_id"]
    empresa_id = data["empresa_id"]
    empresa_nombre = data["empresa_nombre"]
    
    print(f"  Empresa: {empresa_nombre} (ID: {empresa_id})")
    print(f"  Máquina: {machine_id}")
    print(f"  Licencia anterior expiraba: {result['expires']}")
    
    # Generar nueva licencia
    new_key = generate_license(machine_id, empresa_id, empresa_nombre, dias=365)
    
    # Validar nueva licencia
    new_result = validate_license(new_key)
    if not new_result.get("valid"):
        print(f"❌ Error al generar nueva licencia: {new_result.get('error')}")
        sys.exit(1)
    
    # Guardar
    if not save_to_env(new_key):
        print("❌ Error guardando en .env")
        sys.exit(1)
    
    if not save_to_registry(machine_id, empresa_id, empresa_nombre, new_key):
        print("⚠️  Advertencia: No se pudo guardar en licencias/empresas.json")
    
    print("\n✅ Licencia renovada exitosamente:")
    print(f"  Nueva expiración: {new_result['expires']}")
    print(f"  Validez: 365 días")
    print("\n📝 Cambios guardados en:")
    print(f"  • .env (CREDITOSPRO_LICENSE_KEY)")
    print(f"  • licencias/empresas.json")


def manual_generate(machine_id: str, empresa_id: int, empresa_nombre: str, dias: int):
    """Genera una licencia manualmente"""
    print(f"\n🔑 Generando licencia manualmente...")
    print(f"  Empresa: {empresa_nombre} (ID: {empresa_id})")
    print(f"  Máquina: {machine_id}")
    print(f"  Validez: {dias} días")
    
    # Generar
    license_key = generate_license(machine_id, empresa_id, empresa_nombre, dias)
    
    # Validar
    result = validate_license(license_key)
    if not result.get("valid"):
        print(f"❌ Error al generar: {result.get('error')}")
        sys.exit(1)
    
    print("\n" + "=" * 70)
    print("LICENSE KEY (copia todo para usar):")
    print("=" * 70)
    print(license_key)
    print("=" * 70)
    
    # Preguntar si guardar
    save_choice = input("\n¿Guardar en .env? (s/n): ").strip().lower()
    if save_choice == 's':
        if save_to_env(license_key):
            print("✅ Guardado en .env")
        else:
            print("❌ Error al guardar en .env")
    
    save_registry = input("¿Guardar en licencias/empresas.json? (s/n): ").strip().lower()
    if save_registry == 's':
        if save_to_registry(machine_id, empresa_id, empresa_nombre, license_key):
            print("✅ Guardado en licencias/empresas.json")
        else:
            print("❌ Error al guardar en licencias/empresas.json")


def main():
    parser = argparse.ArgumentParser(
        description="Renueva licencias anuales de CreditosPro",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Ejemplos:
  python renewal_license.py --auto
      Renueva la licencia actual automáticamente
  
  python renewal_license.py --machine ABC123 --empresa-id 1 --empresa "ElRusso"
      Genera una nueva licencia manualmente
  
  python renewal_license.py --validate CPRO-...
      Valida una licencia existente
        """
    )
    
    parser.add_argument("--auto", action="store_true",
                       help="Modo automático: renueva la licencia actual")
    parser.add_argument("--machine", type=str,
                       help="Machine ID (si no lo das, se usa el de este equipo)")
    parser.add_argument("--empresa-id", type=int,
                       help="ID de la empresa")
    parser.add_argument("--empresa", type=str,
                       help="Nombre de la empresa")
    parser.add_argument("--dias", type=int, default=365,
                       help="Días de validez (default: 365)")
    parser.add_argument("--validate", type=str,
                       help="Valida una licencia existente")
    parser.add_argument("--myid", action="store_true",
                       help="Muestra el Machine ID de este equipo")
    
    args = parser.parse_args()
    
    _load_env()
    
    if args.myid:
        machine_id = get_fingerprint()
        print(f"\n🖥️  Machine ID de este equipo:\n\n  {machine_id}\n")
        return
    
    if args.validate:
        result = validate_license(args.validate)
        if result.get("valid"):
            data = result["data"]
            print(f"\n✅ Licencia VÁLIDA:")
            print(f"  Empresa: {data['empresa_nombre']} (ID: {data['empresa_id']})")
            print(f"  Máquina: {data['machine_id']}")
            print(f"  Expira: {result['expires']}")
            print(f"  Días restantes: {result['days_left']}")
        else:
            print(f"\n❌ Licencia INVÁLIDA: {result.get('error')}")
        return
    
    if args.auto:
        auto_renew()
    else:
        # Modo manual
        machine_id = args.machine or get_fingerprint()
        
        if not args.empresa_id or not args.empresa:
            parser.error("--empresa-id y --empresa son requeridos en modo manual")
        
        manual_generate(machine_id, args.empresa_id, args.empresa, args.dias)


if __name__ == "__main__":
    main()
