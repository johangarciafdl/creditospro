"""
CreditosPro — Limpiar Duplicado de ElRuso
Elimina la empresa ElRuso duplicada (ID 20) y mantiene la original (ID 1)
Uso: python limpiar_elruso_duplicado.py
"""
import sys
import os
from pathlib import Path

# ── CARGAR .env PRIMERO ─────────────────────────────────────────────────────
from dotenv import load_dotenv
env_file = Path(__file__).parent / ".env"
if env_file.exists():
    load_dotenv(env_file)
    print(f"[✓] Variables cargadas desde: {env_file}")
else:
    print(f"[ERROR] No existe {env_file}")
    sys.exit(1)

# Agregar el directorio actual al path
sys.path.insert(0, str(Path(__file__).parent))

from app.database import SessionLocal, Empresa, Usuario
from sqlalchemy import text

def limpiar_elruso_duplicado():
    """Elimina empresas ElRuso duplicadas, manteniendo solo la ID 1"""
    db = SessionLocal()
    
    try:
        print("\n" + "="*80)
        print("CreditosPro — Limpiar Duplicado de ElRuso")
        print("="*80)
        
        # 1. Buscar todas las empresas ElRuso
        empresas_elruso = db.query(Empresa).filter(
            Empresa.nombre == "ElRuso"
        ).order_by(Empresa.id).all()
        
        print(f"\n📊 Empresas 'ElRuso' encontradas: {len(empresas_elruso)}")
        for emp in empresas_elruso:
            usuarios_count = db.query(Usuario).filter(
                Usuario.empresa_id == emp.id
            ).count()
            print(f"  • ID {emp.id}: {emp.nombre} (activa: {emp.activa}, usuarios: {usuarios_count})")
        
        if len(empresas_elruso) <= 1:
            print("\n✓ No hay duplicados, todo OK!")
            return
        
        # 2. Mantener ID 1, eliminar resto
        print(f"\n⚠️  Se eliminarán {len(empresas_elruso) - 1} empresa(s) duplicada(s)...")
        print(f"✓ Se mantendrá la empresa ID 1\n")
        
        for emp in empresas_elruso[1:]:  # Saltar la primera (ID 1)
            print(f"  🗑️  Eliminando empresa ID {emp.id}...")
            
            # Contar datos a eliminar
            usuarios = db.query(Usuario).filter(
                Usuario.empresa_id == emp.id
            ).all()
            
            print(f"     - {len(usuarios)} usuario(s)")
            
            # Eliminar cascada (automaticamente elimina usuarios, clientes, etc.)
            db.delete(emp)
            db.flush()
            print(f"     ✓ Eliminada")
        
        # 3. Confirmar cambios
        db.commit()
        
        print(f"\n✅ LIMPIEZA COMPLETADA EXITOSAMENTE")
        print(f"\n📊 Estado final:")
        
        empresas_finales = db.query(Empresa).filter(
            Empresa.nombre == "ElRuso"
        ).all()
        
        for emp in empresas_finales:
            usuarios_count = db.query(Usuario).filter(
                Usuario.empresa_id == emp.id
            ).count()
            
            usuarios_list = db.query(Usuario).filter(
                Usuario.empresa_id == emp.id
            ).all()
            
            print(f"\n  Empresa ID {emp.id}: {emp.nombre}")
            print(f"  • Activa: {emp.activa}")
            print(f"  • Usuarios ({len(usuarios_list)}):")
            for u in usuarios_list:
                print(f"    - {u.username} ({u.rol})")
        
        print("\n" + "="*80)
        print("Próximo paso: python run.py")
        print("="*80 + "\n")
        
    except Exception as e:
        db.rollback()
        print(f"\n❌ ERROR: {str(e)}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        db.close()

if __name__ == "__main__":
    # Confirmar antes de ejecutar
    print("\n⚠️  ADVERTENCIA: Este script eliminará las empresas ElRuso duplicadas")
    print("Se mantendrá solo la empresa ID 1 con todos sus datos.\n")
    
    respuesta = input("¿Deseas continuar? (s/n): ").lower().strip()
    if respuesta != "s":
        print("Cancelado.")
        sys.exit(0)
    
    limpiar_elruso_duplicado()
