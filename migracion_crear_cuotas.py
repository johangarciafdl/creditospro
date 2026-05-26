"""
Migración: Crear cuotas faltantes para prestamos existentes
============================================================
Crea las cuotas que debieron crearse cuando se registró cada préstamo.
OPTIMIZADO: Agrupa inserciones en lotes para mejor performance.
"""
import datetime
from app.database import SessionLocal, Prestamo, Cuota
from app.services.prestamo_service import calcular_cuotas

def migrar():
    db = SessionLocal()
    print("\n" + "="*70)
    print("MIGRACIÓN: CREAR CUOTAS FALTANTES (OPTIMIZADO)")
    print("="*70)
    
    # Obtener préstamos sin cuotas
    prestamos_sin_cuotas = db.query(Prestamo).outerjoin(Cuota).filter(
        Cuota.id == None
    ).all()
    
    total = len(prestamos_sin_cuotas)
    print(f"\nPréstamos sin cuotas encontrados: {total}")
    
    if total == 0:
        print("✅ No hay préstamos sin cuotas. Todo está en orden.")
        db.close()
        return
    
    creadas = 0
    errores = 0
    lote = []
    LOTE_SIZE = 500  # Insertar de 500 en 500
    
    for i, prestamo in enumerate(prestamos_sin_cuotas, 1):
        try:
            # Validar datos mínimos
            if not prestamo.capital or not prestamo.num_cuotas or not prestamo.fecha_inicio:
                continue
            
            # Calcular cuotas
            calc = calcular_cuotas(
                prestamo.capital,
                prestamo.tasa_interes or 20.0,
                prestamo.num_cuotas,
                prestamo.fecha_inicio,
                prestamo.plazo_dias or 30
            )
            
            # Agregar cuotas al lote
            for c in calc.get("cuotas", []):
                cuota = Cuota(
                    empresa_id=prestamo.empresa_id,
                    prestamo_id=prestamo.id,
                    numero=int(c["numero"]),
                    valor=float(c.get("valor", 0)),
                    fecha_vencimiento=c["fecha_vencimiento"],
                    estado="Pendiente",
                )
                lote.append(cuota)
                creadas += 1
            
            # Si el lote alcanza el tamaño, guardar
            if len(lote) >= LOTE_SIZE:
                db.add_all(lote)
                db.commit()
                lote = []
                print(f"✅ [{i}/{total}] {creadas} cuotas creadas hasta ahora...")
        
        except Exception as e:
            errores += 1
            print(f"⚠️  Préstamo #{prestamo.id}: {str(e)}")
    
    # Guardar lote final
    if lote:
        db.add_all(lote)
        db.commit()
    
    print(f"\n" + "="*70)
    print(f"✅ MIGRACIÓN COMPLETADA:")
    print(f"  • Préstamos procesados: {total}")
    print(f"  • Cuotas creadas: {creadas}")
    print(f"  • Errores: {errores}")
    print(f"="*70 + "\n")
    
    db.close()

if __name__ == "__main__":
    migrar()
