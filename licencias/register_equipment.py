#!/usr/bin/env python3
"""
CreditosPro Equipment Registration Tool
Registra y gestiona licencias para múltiples equipos por empresa.

Uso:
    python register_equipment.py register --empresa "ElRusso" --machine ABC123 --equipo "PC-OFICINA-02"
    python register_equipment.py list --empresa "ElRusso"
    python register_equipment.py status --empresa "ElRusso" --equipo "PC-OFICINA-02"
    python register_equipment.py delete --empresa "ElRusso" --equipo "PC-OFICINA-02"
"""
import os
import sys
import json
import argparse
import datetime
from pathlib import Path
from dotenv import load_dotenv


def _load_env():
    """Carga variables de .env"""
    env_path = Path(__file__).parent.parent / ".env"
    if env_path.exists():
        load_dotenv(env_path)
    return env_path


def get_equipment_registry_path():
    """Obtiene la ruta del archivo de registro de equipos"""
    path = Path(__file__).parent / "equipos_registro.json"
    return path


def load_equipment_registry() -> dict:
    """Carga el registro de equipos"""
    registry_path = get_equipment_registry_path()
    if registry_path.exists():
        return json.loads(registry_path.read_text(encoding="utf-8"))
    return {}


def save_equipment_registry(registry: dict):
    """Guarda el registro de equipos"""
    registry_path = get_equipment_registry_path()
    registry_path.write_text(json.dumps(registry, indent=2, ensure_ascii=False), encoding="utf-8")


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
    """Valida una licencia"""
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


def cmd_register(empresa: str, empresa_id: int, machine_id: str, equipo: str):
    """Registra un nuevo equipo"""
    print(f"\n📝 Registrando equipo: {equipo}")
    print(f"  Empresa: {empresa} (ID: {empresa_id})")
    print(f"  Machine ID: {machine_id}")
    
    # Generar licencia
    license_key = generate_license(machine_id, empresa_id, empresa, dias=365)
    
    # Validar licencia
    result = validate_license(license_key)
    if not result.get("valid"):
        print(f"❌ Error al generar licencia: {result.get('error')}")
        sys.exit(1)
    
    # Guardar en registro
    registry = load_equipment_registry()
    
    if empresa not in registry:
        registry[empresa] = {
            "empresa_id": empresa_id,
            "equipos": []
        }
    
    # Verificar que el equipo no existe
    for eq in registry[empresa]["equipos"]:
        if eq["nombre"].lower() == equipo.lower():
            print(f"⚠️  Equipo '{equipo}' ya existe. Reemplazando...")
            registry[empresa]["equipos"].remove(eq)
            break
    
    # Agregar equipo
    registry[empresa]["equipos"].append({
        "nombre": equipo,
        "machine_id": machine_id,
        "licencia": license_key,
        "vencimiento": result["expires"],
        "registrado": datetime.datetime.now().isoformat(),
        "activa": True
    })
    
    save_equipment_registry(registry)
    
    print("\n" + "=" * 70)
    print("✅ EQUIPO REGISTRADO EXITOSAMENTE")
    print("=" * 70)
    print(f"\n📋 Datos del equipo:")
    print(f"  Nombre: {equipo}")
    print(f"  Machine ID: {machine_id}")
    print(f"  Licencia válida hasta: {result['expires']}")
    print(f"\n🔑 LICENCIA (copia y envía al equipo):\n")
    print(license_key)
    print("\n" + "=" * 70)
    
    # Guardar licencia en archivo
    license_file = Path(__file__).parent / f"license_{equipo.replace(' ', '_')}.txt"
    license_file.write_text(license_key, encoding="utf-8")
    print(f"\nTambién guardada en: {license_file.absolute()}")


def cmd_list(empresa: str):
    """Lista todos los equipos de una empresa"""
    registry = load_equipment_registry()
    
    if empresa not in registry:
        print(f"❌ Empresa '{empresa}' no encontrada en el registro")
        return
    
    equipos = registry[empresa]["equipos"]
    
    if not equipos:
        print(f"\n📭 No hay equipos registrados para '{empresa}'")
        return
    
    print(f"\n📊 Equipos de {empresa}:")
    print("=" * 80)
    
    for eq in equipos:
        status = "✅ Activa" if eq.get("activa", True) else "❌ Inactiva"
        expires = eq.get("vencimiento", "N/A")
        print(f"\n  📱 {eq['nombre']}")
        print(f"     Machine ID: {eq['machine_id']}")
        print(f"     Vencimiento: {expires} {status}")
        print(f"     Registrado: {eq.get('registrado', 'N/A')[:10]}")


def cmd_status(empresa: str, equipo: str):
    """Muestra el estado de un equipo"""
    registry = load_equipment_registry()
    
    if empresa not in registry:
        print(f"❌ Empresa '{empresa}' no encontrada")
        return
    
    for eq in registry[empresa]["equipos"]:
        if eq["nombre"].lower() == equipo.lower():
            print(f"\n📊 Estado de {equipo}:")
            print("=" * 70)
            print(f"  Empresa: {empresa}")
            print(f"  Machine ID: {eq['machine_id']}")
            print(f"  Vencimiento: {eq.get('vencimiento', 'N/A')}")
            print(f"  Activa: {'✅ Sí' if eq.get('activa', True) else '❌ No'}")
            print(f"  Registrado: {eq.get('registrado', 'N/A')[:10]}")
            
            # Validar licencia
            result = validate_license(eq['licencia'])
            if result.get("valid"):
                print(f"  Validación: ✅ VÁLIDA")
                print(f"  Días restantes: {result['days_left']}")
            else:
                print(f"  Validación: ❌ INVÁLIDA ({result.get('error', 'Unknown')})")
            
            return
    
    print(f"❌ Equipo '{equipo}' no encontrado en '{empresa}'")


def cmd_delete(empresa: str, equipo: str):
    """Elimina un equipo del registro"""
    registry = load_equipment_registry()
    
    if empresa not in registry:
        print(f"❌ Empresa '{empresa}' no encontrada")
        return
    
    for i, eq in enumerate(registry[empresa]["equipos"]):
        if eq["nombre"].lower() == equipo.lower():
            confirmacion = input(f"\n⚠️  ¿Eliminar '{equipo}' de '{empresa}'? (s/n): ").strip().lower()
            if confirmacion == 's':
                registry[empresa]["equipos"].pop(i)
                save_equipment_registry(registry)
                print(f"✅ Equipo '{equipo}' eliminado.")
            else:
                print("❌ Cancelado.")
            return
    
    print(f"❌ Equipo '{equipo}' no encontrado")


def cmd_export(empresa: str, equipo: str = None):
    """Exporta las licencias de una empresa o equipo"""
    registry = load_equipment_registry()
    
    if empresa not in registry:
        print(f"❌ Empresa '{empresa}' no encontrada")
        return
    
    equipos = registry[empresa]["equipos"]
    
    if equipo:
        # Exportar solo un equipo
        for eq in equipos:
            if eq["nombre"].lower() == equipo.lower():
                print(f"\n🔑 Licencia de {equipo}:\n")
                print(eq['licencia'])
                return
        print(f"❌ Equipo '{equipo}' no encontrado")
    else:
        # Exportar CSV con todas las licencias
        print(f"\n📊 Licencias de {empresa}:")
        print("=" * 80)
        print(f"{'Equipo':<25} {'Machine ID':<35} {'Vencimiento':<15} {'Licencia (primeros 50 char)'}")
        print("-" * 80)
        
        for eq in equipos:
            licencia_short = eq['licencia'][:50] + "..." if len(eq['licencia']) > 50 else eq['licencia']
            print(f"{eq['nombre']:<25} {eq['machine_id']:<35} {eq.get('vencimiento', 'N/A'):<15} {licencia_short}")
        
        print("\n💾 Para exportar completo a archivo:")
        print(f"  python register_equipment.py export --empresa \"{empresa}\" > licencias_{empresa}.csv")


def cmd_import_from_env(empresa: str, empresa_id: int, equipo: str):
    """Importa la licencia del .env actual al registro"""
    print(f"\n📥 Importando licencia actual del .env...")
    
    license_key = os.getenv("CREDITOSPRO_LICENSE_KEY", "").strip()
    if not license_key:
        print("❌ CREDITOSPRO_LICENSE_KEY no encontrada en .env")
        return
    
    # Validar
    result = validate_license(license_key)
    if not result.get("valid"):
        print(f"❌ Licencia inválida: {result.get('error')}")
        return
    
    data = result["data"]
    machine_id = data["machine_id"]
    
    # Registrar
    registry = load_equipment_registry()
    
    if empresa not in registry:
        registry[empresa] = {
            "empresa_id": empresa_id,
            "equipos": []
        }
    
    # Verificar duplicados
    for eq in registry[empresa]["equipos"]:
        if eq["nombre"].lower() == equipo.lower():
            print(f"⚠️  Equipo '{equipo}' ya existe. Reemplazando...")
            registry[empresa]["equipos"].remove(eq)
            break
    
    # Agregar
    registry[empresa]["equipos"].append({
        "nombre": equipo,
        "machine_id": machine_id,
        "licencia": license_key,
        "vencimiento": result["expires"],
        "registrado": datetime.datetime.now().isoformat(),
        "activa": True
    })
    
    save_equipment_registry(registry)
    
    print(f"✅ Licencia importada:")
    print(f"  Empresa: {empresa}")
    print(f"  Equipo: {equipo}")
    print(f"  Machine ID: {machine_id}")
    print(f"  Expira: {result['expires']}")


def main():
    parser = argparse.ArgumentParser(
        description="Registra y gestiona equipos con licencias de CreditosPro",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Ejemplos:
  # Registrar un nuevo equipo
  python register_equipment.py register --empresa "ElRusso" --empresa-id 1 --machine ABC123DEF456 --equipo "PC-OFICINA-02"
  
  # Listar equipos de una empresa
  python register_equipment.py list --empresa "ElRusso"
  
  # Ver estado de un equipo
  python register_equipment.py status --empresa "ElRusso" --equipo "PC-OFICINA-02"
  
  # Importar licencia actual del .env
  python register_equipment.py import-env --empresa "ElRusso" --empresa-id 1 --equipo "PC-PRINCIPAL"
  
  # Exportar licencias
  python register_equipment.py export --empresa "ElRusso"
  
  # Eliminar un equipo
  python register_equipment.py delete --empresa "ElRusso" --equipo "PC-OFICINA-02"
        """
    )
    
    sub = parser.add_subparsers(dest="cmd", required=True)
    
    # Registrar
    reg = sub.add_parser("register")
    reg.add_argument("--empresa", required=True, help="Nombre de la empresa")
    reg.add_argument("--empresa-id", type=int, required=True, help="ID de la empresa")
    reg.add_argument("--machine", required=True, help="Machine ID del equipo")
    reg.add_argument("--equipo", required=True, help="Nombre del equipo (ej: PC-OFICINA-02)")
    
    # Listar
    lst = sub.add_parser("list")
    lst.add_argument("--empresa", required=True, help="Nombre de la empresa")
    
    # Estado
    sta = sub.add_parser("status")
    sta.add_argument("--empresa", required=True, help="Nombre de la empresa")
    sta.add_argument("--equipo", required=True, help="Nombre del equipo")
    
    # Eliminar
    dlt = sub.add_parser("delete")
    dlt.add_argument("--empresa", required=True, help="Nombre de la empresa")
    dlt.add_argument("--equipo", required=True, help="Nombre del equipo")
    
    # Exportar
    exp = sub.add_parser("export")
    exp.add_argument("--empresa", required=True, help="Nombre de la empresa")
    exp.add_argument("--equipo", help="Nombre del equipo (opcional)")
    
    # Importar desde .env
    imp = sub.add_parser("import-env")
    imp.add_argument("--empresa", required=True, help="Nombre de la empresa")
    imp.add_argument("--empresa-id", type=int, required=True, help="ID de la empresa")
    imp.add_argument("--equipo", required=True, help="Nombre del equipo")
    
    args = parser.parse_args()
    _load_env()
    
    if args.cmd == "register":
        cmd_register(args.empresa, args.empresa_id, args.machine, args.equipo)
    elif args.cmd == "list":
        cmd_list(args.empresa)
    elif args.cmd == "status":
        cmd_status(args.empresa, args.equipo)
    elif args.cmd == "delete":
        cmd_delete(args.empresa, args.equipo)
    elif args.cmd == "export":
        cmd_export(args.empresa, args.equipo)
    elif args.cmd == "import-env":
        cmd_import_from_env(args.empresa, args.empresa_id, args.equipo)


if __name__ == "__main__":
    main()
