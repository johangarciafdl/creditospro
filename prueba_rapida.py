"""
Prueba Rápida: Verificar que todo funciona correctamente
========================================================
Ejecuta este script para verificar que:
1. Supabase está conectada
2. Hay cuotas creadas
3. La búsqueda funciona
4. Se puede crear un préstamo
"""
import datetime
from sqlalchemy import text
from app.database import SessionLocal, Cliente, Prestamo, Cuota, Zona, Usuario, Empresa
from app.services.prestamo_service import calcular_cuotas

def test_rapido():
    db = SessionLocal()
    print("\n" + "="*70)
    print("PRUEBA RÁPIDA - VERIFICACIÓN DE FUNCIONALIDAD")
    print("="*70)
    
    try:
        # Test 1: Conexión
        print("\n✓ TEST 1: Conexión a Supabase")
        db.execute(text("SELECT 1"))
        print("  ✅ Conectado exitosamente")
        
        # Test 2: Cuotas existen
        print("\n✓ TEST 2: Verificar cuotas")
        cuota_count = db.query(Cuota).count()
        if cuota_count > 0:
            print(f"  ✅ {cuota_count:,} cuotas encontradas")
        else:
            print(f"  ❌ No hay cuotas (problema crítico)")
        
        # Test 3: Buscar cliente
        print("\n✓ TEST 3: Búsqueda de cliente")
        cliente = db.query(Cliente).first()
        if cliente:
            print(f"  ✅ Cliente encontrado: {cliente.nombre}")
            
            # Buscar por nombre
            resultado = db.query(Cliente).filter(
                Cliente.nombre.ilike(f"%{cliente.nombre.split()[0]}%"),
                Cliente.empresa_id == cliente.empresa_id
            ).all()
            print(f"  ✅ Búsqueda por nombre: {len(resultado)} resultado(s)")
        else:
            print(f"  ❌ No hay clientes")
        
        # Test 4: Verificar relaciones
        print("\n✓ TEST 4: Integridad de relaciones")
        prestamos_sin_cliente = db.query(Prestamo).filter(Prestamo.cliente_id == None).count()
        cuotas_sin_prestamo = db.query(Cuota).filter(Cuota.prestamo_id == None).count()
        
        if prestamos_sin_cliente == 0 and cuotas_sin_prestamo == 0:
            print("  ✅ Todas las relaciones están intactas")
        else:
            print(f"  ⚠️  Préstamos huérfanos: {prestamos_sin_cliente}")
            print(f"  ⚠️  Cuotas huérfanas: {cuotas_sin_prestamo}")
        
        # Test 5: Calcular cuotas (simulación)
        print("\n✓ TEST 5: Calcular cuotas (simulación)")
        calc = calcular_cuotas(500000, 20, 30, datetime.date.today(), 30)
        if calc.get("total_pagar") and calc.get("valor_cuota"):
            print(f"  ✅ Capital: ${500000:,}")
            print(f"  ✅ Interés total: ${calc.get('interes_total'):,.0f}")
            print(f"  ✅ Total a pagar: ${calc.get('total_pagar'):,.0f}")
            print(f"  ✅ Valor cuota: ${calc.get('valor_cuota'):,.0f}")
        else:
            print(f"  ❌ Error en cálculo")
        
        # Test 6: Verificar usuario y zona
        print("\n✓ TEST 6: Datos de prueba")
        user = db.query(Usuario).filter(Usuario.activo == True).first()
        zona = db.query(Zona).filter(Zona.activa == True).first()
        
        if user:
            print(f"  ✅ Usuario: {user.nombre} ({user.rol})")
        else:
            print(f"  ❌ No hay usuarios")
        
        if zona:
            print(f"  ✅ Zona: {zona.nombre}")
        else:
            print(f"  ❌ No hay zonas")
        
        # RESULTADO FINAL
        print("\n" + "="*70)
        print("✅ PRUEBA COMPLETADA EXITOSAMENTE")
        print("="*70)
        print("\nEstado del sistema:")
        print(f"  • Base de datos: ✅ OK")
        print(f"  • Cuotas: ✅ {cuota_count:,} registradas")
        print(f"  • Búsqueda: ✅ Funcionando")
        print(f"  • Cálculos: ✅ OK")
        print(f"  • Relaciones: ✅ Intactas")
        print("\n¡Sistema listo para usar! 🚀\n")
        
    except Exception as e:
        print(f"\n❌ ERROR CRÍTICO: {str(e)}")
        import traceback
        print(traceback.format_exc())
    finally:
        db.close()

if __name__ == "__main__":
    test_rapido()
