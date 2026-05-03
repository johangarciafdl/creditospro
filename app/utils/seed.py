"""
Seed v2.1 - Multi-tenant demo
Crea empresa demo + admin + datos si no existen
"""
import datetime
from app.database import SessionLocal, Empresa, Zona, Cliente, Prestamo, Cuota, ConfiguracionApp, Usuario
from app.utils.security import get_password_hash
from app.services.prestamo_service import calcular_cuotas


def seed_data_demo():
    db = SessionLocal()
    try:
        empresa = db.query(Empresa).filter(Empresa.nombre == "Demo CreditosPro").first()
        if not empresa:
            empresa = Empresa(nombre="Demo CreditosPro", nit="900123456-1",
                              ciudad="Medellín", pais="Colombia", plan="pro")
            db.add(empresa)
            db.flush()

            config = ConfiguracionApp(
                empresa_id=empresa.id,
                empresa_nombre="Demo CreditosPro",
                pais="Colombia", moneda="COP",
                tasa_default=20.0, cuotas_default=30,
            )
            db.add(config)

            admin = Usuario(
                empresa_id=empresa.id,
                username="admin", nombre="Administrador",
                hashed_password=get_password_hash("admin123"),
                rol="admin", activo=True,
            )
            db.add(admin)

            zona = Zona(empresa_id=empresa.id, codigo="Z001",
                        nombre="Zona Norte", ciudad="Medellín",
                        cobrador_nombre="Carlos López", cobrador_tel="3001234567")
            db.add(zona)
            db.flush()

            cobrador = Usuario(
                empresa_id=empresa.id, username="cobrador1",
                nombre="Carlos López",
                hashed_password=get_password_hash("cobrador123"),
                rol="cobrador", zona_id=zona.id,
            )
            db.add(cobrador)

            hoy = datetime.date.today()
            clientes_demo = [
                ("1020304050", "María González Restrepo", "3101234567", "Regular"),
                ("1020304051", "Juan Pérez Montoya", "3152345678", "Bueno"),
                ("1020304052", "Ana Torres Zapata", "3163456789", "Riesgo"),
            ]
            for ced, nom, tel, tipo in clientes_demo:
                c = Cliente(empresa_id=empresa.id, cedula=ced, nombre=nom,
                            telefono=tel, whatsapp=tel, zona_id=zona.id,
                            tipo_cliente=tipo, barrio="Centro")
                db.add(c)
                db.flush()
                calc = calcular_cuotas(500_000, 20.0, 10, hoy, 30)
                p = Prestamo(
                    empresa_id=empresa.id, cliente_id=c.id, zona_id=zona.id,
                    capital=500_000, tasa_interes=20.0,
                    interes_total=calc["interes_total"],
                    total_pagar=calc["total_pagar"],
                    num_cuotas=10, valor_cuota=calc["valor_cuota"],
                    plazo_dias=30, fecha_inicio=hoy,
                    fecha_fin=calc["fecha_fin"], estado="Activo",
                )
                db.add(p)
                db.flush()
                for cu in calc["cuotas"]:
                    db.add(Cuota(
                        empresa_id=empresa.id, prestamo_id=p.id,
                        numero=cu["numero"], valor=cu["valor"],
                        fecha_vencimiento=cu["fecha_vencimiento"],
                        estado="Pendiente", valor_pagado=0.0,
                    ))

            db.commit()
            print("✅ Empresa demo + admin/admin123 + datos creados")
        else:
            print("✓ Datos demo ya existen")
    except Exception as e:
        print(f"Seed error: {e}")
        import traceback; traceback.print_exc()
        db.rollback()
    finally:
        db.close()
