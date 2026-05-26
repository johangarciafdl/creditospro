"""
Diagnóstico de Problemas con Supabase
======================================
Script para verificar la conexión y la integridad de datos en Supabase
"""
import os
from app.database import SessionLocal, Cliente, Prestamo, Usuario, Empresa, Zona, Cuota
from sqlalchemy import inspect, text

def diagnosticar():
    db = SessionLocal()
    print("\n" + "="*70)
    print("DIAGNÓSTICO DE CONEXIÓN A SUPABASE")
    print("="*70)
    
    try:
        # 1. Verificar conexión
        print("\n✓ 1. CONEXIÓN A SUPABASE")
        db.execute(text("SELECT 1"))
        print("   ✅ Conexión exitosa")
    except Exception as e:
        print(f"   ❌ Error de conexión: {str(e)}")
        return
    
    try:
        # 2. Verificar tablas
        print("\n✓ 2. VERIFICACIÓN DE TABLAS")
        inspector = inspect(db.bind)
        tablas_esperadas = [
            'empresas', 'usuarios', 'zonas', 'clientes', 
            'prestamos', 'cuotas', 'cobros', 'notificaciones_wp'
        ]
        tablas_existentes = inspector.get_table_names()
        
        for tabla in tablas_esperadas:
            if tabla in tablas_existentes:
                print(f"   ✅ {tabla}")
            else:
                print(f"   ❌ {tabla} - NO EXISTE")
    except Exception as e:
        print(f"   ❌ Error al verificar tablas: {str(e)}")
    
    try:
        # 3. Contar registros
        print("\n✓ 3. CONTEO DE REGISTROS")
        emp_count = db.query(Empresa).count()
        user_count = db.query(Usuario).count()
        zona_count = db.query(Zona).count()
        cli_count = db.query(Cliente).count()
        pres_count = db.query(Prestamo).count()
        cuota_count = db.query(Cuota).count()
        
        print(f"   • Empresas: {emp_count}")
        print(f"   • Usuarios: {user_count}")
        print(f"   • Zonas: {zona_count}")
        print(f"   • Clientes: {cli_count}")
        print(f"   • Préstamos: {pres_count}")
        print(f"   • Cuotas: {cuota_count}")
    except Exception as e:
        print(f"   ❌ Error al contar registros: {str(e)}")
    
    try:
        # 4. Verificar relaciones
        print("\n✓ 4. VERIFICACIÓN DE RELACIONES")
        
        # Clientes sin empresa
        cli_sin_emp = db.query(Cliente).filter(Cliente.empresa_id == None).count()
        if cli_sin_emp > 0:
            print(f"   ⚠️  {cli_sin_emp} clientes sin empresa_id asignado")
        else:
            print(f"   ✅ Todos los clientes tienen empresa_id")
        
        # Préstamos sin cliente
        pres_sin_cli = db.query(Prestamo).filter(Prestamo.cliente_id == None).count()
        if pres_sin_cli > 0:
            print(f"   ⚠️  {pres_sin_cli} préstamos sin cliente_id")
        else:
            print(f"   ✅ Todos los préstamos tienen cliente_id")
        
        # Cuotas sin préstamo
        cuota_sin_pres = db.query(Cuota).filter(Cuota.prestamo_id == None).count()
        if cuota_sin_pres > 0:
            print(f"   ⚠️  {cuota_sin_pres} cuotas sin préstamo_id")
        else:
            print(f"   ✅ Todas las cuotas tienen préstamo_id")
            
    except Exception as e:
        print(f"   ❌ Error al verificar relaciones: {str(e)}")
    
    try:
        # 5. Test de búsqueda de cliente
        print("\n✓ 5. TEST DE BÚSQUEDA DE CLIENTE")
        
        if cli_count > 0:
            primer_cliente = db.query(Cliente).first()
            print(f"   Primer cliente: {primer_cliente.nombre} (ID: {primer_cliente.id})")
            
            # Buscar por nombre
            resultado = db.query(Cliente).filter(
                Cliente.nombre.ilike(f"%{primer_cliente.nombre.split()[0]}%")
            ).all()
            print(f"   ✅ Búsqueda por nombre: {len(resultado)} resultado(s)")
            
            # Buscar por cédula
            if primer_cliente.cedula:
                resultado = db.query(Cliente).filter(
                    Cliente.cedula.ilike(f"%{primer_cliente.cedula}%")
                ).all()
                print(f"   ✅ Búsqueda por cédula: {len(resultado)} resultado(s)")
        else:
            print(f"   ⚠️  No hay clientes para probar búsqueda")
            
    except Exception as e:
        print(f"   ❌ Error en búsqueda: {str(e)}")
    
    try:
        # 6. Test de creación de préstamo
        print("\n✓ 6. SIMULACIÓN DE CREACIÓN DE PRÉSTAMO")
        
        # Buscar empresa, zona y cliente válidos
        emp = db.query(Empresa).filter(Empresa.activa == True).first()
        if emp:
            print(f"   • Empresa encontrada: {emp.nombre} (ID: {emp.id})")
            
            zona = db.query(Zona).filter(Zona.empresa_id == emp.id).first()
            if zona:
                print(f"   • Zona encontrada: {zona.nombre} (ID: {zona.id})")
            else:
                print(f"   ❌ No hay zonas para la empresa")
            
            cliente = db.query(Cliente).filter(Cliente.empresa_id == emp.id).first()
            if cliente:
                print(f"   • Cliente encontrado: {cliente.nombre} (ID: {cliente.id})")
            else:
                print(f"   ❌ No hay clientes para la empresa")
        else:
            print(f"   ❌ No hay empresas activas")
            
    except Exception as e:
        print(f"   ❌ Error en simulación: {str(e)}")
    
    print("\n" + "="*70)
    print("FIN DEL DIAGNÓSTICO")
    print("="*70 + "\n")
    
    db.close()

if __name__ == "__main__":
    diagnosticar()
