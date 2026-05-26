#!/usr/bin/env python3
"""
Script para eliminar todas las empresas excepto 'ElRuso' de Supabase
y limpiar sus datos relacionados (usuarios, zonas, clientes, etc.)
"""
import os
import sys
from pathlib import Path

# Cargar variables de entorno desde .env
from dotenv import load_dotenv
load_dotenv()

# Agregar el directorio del proyecto al path
sys.path.insert(0, str(Path(__file__).parent))

from app.database import engine, SessionLocal, Empresa
from sqlalchemy import text

def confirmar_eliminacion():
    """Pide confirmación antes de eliminar datos"""
    print("\n" + "="*70)
    print("⚠️  ADVERTENCIA: Vas a eliminar TODAS las empresas excepto 'ElRuso'")
    print("="*70)
    print("\nEsto eliminará:")
    print("  • Todas las empresas excepto 'ElRuso'")
    print("  • Todos los usuarios de esas empresas")
    print("  • Todas las zonas de esas empresas")
    print("  • Todos los clientes de esas empresas")
    print("  • Todos los préstamos de esas empresas")
    print("  • Todos los cobros de esas empresas")
    print("  • Todas las cuotas de esas empresas")
    print("  • Todas las notificaciones de esas empresas")
    print("\n" + "="*70)
    
    respuesta = input("\n¿Deseas continuar? Escribe 'CONFIRMAR' para proceder: ")
    if respuesta.upper() != "CONFIRMAR":
        print("❌ Operación cancelada")
        sys.exit(0)
    
    return True

def limpiar_empresas():
    """Elimina todas las empresas excepto 'ElRuso'"""
    session = SessionLocal()
    
    try:
        # 1. Encontrar la empresa 'ElRuso'
        empresa_elruso = session.query(Empresa).filter(
            Empresa.nombre.ilike('%ElRuso%')
        ).first()
        
        if not empresa_elruso:
            print("❌ No se encontró la empresa 'ElRuso'")
            print("\nEmpresas disponibles:")
            empresas = session.query(Empresa).all()
            for emp in empresas:
                print(f"  • {emp.id}: {emp.nombre}")
            session.close()
            sys.exit(1)
        
        print(f"\n✅ Empresa 'ElRuso' encontrada (ID: {empresa_elruso.id})")
        
        # 2. Obtener todas las otras empresas
        otras_empresas = session.query(Empresa).filter(
            Empresa.id != empresa_elruso.id
        ).all()
        
        if not otras_empresas:
            print("✅ No hay otras empresas para eliminar")
            session.close()
            return
        
        print(f"\n🔍 Se encontraron {len(otras_empresas)} otras empresa(s):")
        for emp in otras_empresas:
            print(f"  • {emp.id}: {emp.nombre}")
        
        # 3. Eliminar las otras empresas (SQLAlchemy eliminará en cascada)
        print(f"\n🗑️  Eliminando {len(otras_empresas)} empresa(s)...")
        for emp in otras_empresas:
            print(f"   ⤳ Eliminando: {emp.nombre} (ID: {emp.id})...")
            session.delete(emp)
        
        session.commit()
        print("✅ Todas las empresas excepto 'ElRuso' fueron eliminadas correctamente")
        
        # 4. Mostrar estado final
        empresas_finales = session.query(Empresa).all()
        print(f"\n📊 Estado final de empresas en la BD: {len(empresas_finales)}")
        for emp in empresas_finales:
            usuarios_count = len(emp.usuarios)
            zonas_count = len(emp.zonas)
            clientes_count = len(emp.clientes)
            print(f"  • {emp.nombre}: {usuarios_count} usuarios, {zonas_count} zonas, {clientes_count} clientes")
        
    except Exception as e:
        print(f"❌ Error durante la limpieza: {e}")
        session.rollback()
        sys.exit(1)
    finally:
        session.close()

if __name__ == "__main__":
    print("\n" + "="*70)
    print("SCRIPT DE LIMPIEZA: CreditosPro - Eliminar Empresas Excepto ElRuso")
    print("="*70)
    
    # Verificar que DATABASE_URL está configurado
    if not os.getenv("DATABASE_URL"):
        print("❌ Error: DATABASE_URL no está configurada en .env")
        sys.exit(1)
    
    # Pedir confirmación
    if confirmar_eliminacion():
        # Ejecutar limpieza
        limpiar_empresas()
        print("\n✅ Script completado exitosamente\n")
