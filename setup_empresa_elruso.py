"""
CreditosPro — Setup Empresa ElRuso
Configura usuarios: Johan, Julian (gerente), Marcos (cobrador)
Uso: python setup_empresa_elruso.py
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

from app.database import SessionLocal, Empresa, Usuario, ConfiguracionApp, Zona
from app.utils.security import get_password_hash


def setup_elruso():
    """Configura la empresa ElRuso con usuarios: Johan, Julian (gerente), Marcos (cobrador)"""
    db = SessionLocal()
    
    try:
        print("\n" + "="*80)
        print("CreditosPro — Setup Empresa ElRuso")
        print("="*80)
        
        # 1. Obtener o crear la empresa ElRuso
        empresa = db.query(Empresa).filter(Empresa.nombre == "ElRuso").first()
        
        if empresa:
            print(f"\n✓ Empresa 'ElRuso' encontrada (ID: {empresa.id})")
        else:
            print("\n⚠ Empresa 'ElRuso' no existe, creando...")
            empresa = Empresa(
                nombre="ElRuso",
                ciudad="Medellin",
                pais="Colombia",
                moneda="COP",
                activa=True,
                plan="premium"
            )
            db.add(empresa)
            db.flush()
            print(f"✓ Empresa creada con ID: {empresa.id}")
        
        # 2. Asegurar que hay una zona principal
        zona = db.query(Zona).filter(Zona.empresa_id == empresa.id).first()
        if not zona:
            print("\n⚠ No hay zonas, creando 'Zona Principal'...")
            zona = Zona(
                empresa_id=empresa.id,
                codigo="Z001",
                nombre="Zona Principal",
                ciudad="Medellin",
                activa=True,
            )
            db.add(zona)
            db.flush()
            print(f"✓ Zona creada (ID: {zona.id})")
        else:
            print(f"✓ Zona 'Zona Principal' encontrada (ID: {zona.id})")
        
        # 3. Asegurar ConfiguracionApp
        config = db.query(ConfiguracionApp).filter(
            ConfiguracionApp.empresa_id == empresa.id
        ).first()
        
        if not config:
            print("\n⚠ No hay configuración, creando...")
            config = ConfiguracionApp(
                empresa_id=empresa.id,
                empresa_nombre="ElRuso",
                pais="Colombia",
                moneda="COP",
            )
            db.add(config)
            db.flush()
            print(f"✓ Configuración creada")
        
        # 4. Crear/actualizar usuarios con roles específicos
        usuarios_config = [
            {
                "username": "johan",
                "nombre": "Johan",
                "contraseña": "Jo681192",
                "rol": "admin",
                "descripcion": "Admin/Owner"
            },
            {
                "username": "julian",
                "nombre": "Julian",
                "contraseña": "197991",
                "rol": "gerente",
                "descripcion": "Gerente"
            },
            {
                "username": "marcos",
                "nombre": "Marcos Baena",
                "contraseña": "Marcos123",
                "rol": "cobrador",
                "descripcion": "Cobrador"
            },
        ]
        
        print("\n⚙️  Configurando usuarios:")
        for user_cfg in usuarios_config:
            # Buscar usuario GLOBAL (username es unique globalmente en la BD)
            usuario = db.query(Usuario).filter(
                Usuario.username == user_cfg["username"]
            ).first()
            
            if usuario:
                # Si existe, lo movemos a ElRuso y actualizamos datos
                print(f"  ! {user_cfg['descripcion']:20} ({user_cfg['username']:10}) — encontrado, actualizando en ElRuso...")
                usuario.empresa_id = empresa.id
                usuario.password_hash = get_password_hash(user_cfg["contraseña"])
                usuario.nombre = user_cfg["nombre"]
                usuario.rol = user_cfg["rol"]
                usuario.activo = True
            else:
                print(f"  + {user_cfg['descripcion']:20} ({user_cfg['username']:10}) — creando...")
                usuario = Usuario(
                    empresa_id=empresa.id,
                    username=user_cfg["username"],
                    nombre=user_cfg["nombre"],
                    password_hash=get_password_hash(user_cfg["contraseña"]),
                    rol=user_cfg["rol"],
                    activo=True,
                )
                db.add(usuario)
                db.flush()
        
        # 5. Desactivar usuario "admin" antiguo si existe
        usuario_admin_viejo = db.query(Usuario).filter(
            Usuario.empresa_id == empresa.id,
            Usuario.username == "admin",
            Usuario.username != "johan"
        ).first()
        
        if usuario_admin_viejo:
            print(f"\n⚠ Usuario 'admin' antiguo encontrado, desactivando...")
            usuario_admin_viejo.activo = False
            print(f"✓ Usuario 'admin' desactivado")
        
        # 6. Desactivar empresas extras
        print("\n⚠ Buscando empresas extras...")
        empresas_extra = db.query(Empresa).filter(
            Empresa.id != empresa.id,
            Empresa.nombre.in_(["creditos", "Creditos", "CREDITOS"])
        ).all()
        
        if empresas_extra:
            for emp_extra in empresas_extra:
                print(f"  → Desactivando empresa '{emp_extra.nombre}' (ID: {emp_extra.id})")
                emp_extra.activa = False
        else:
            print(f"  → No hay empresas extras (OK)")
        
        # Commit de todos los cambios
        db.commit()
        
        print("\n" + "="*80)
        print("✅ SETUP COMPLETADO EXITOSAMENTE")
        print("="*80)
        print(f"""
DATOS DE ACCESO PARA TODOS LOS USUARIOS:

📋 ADMIN/OWNER:
   Usuario:     johan
   Contraseña:  Jo681192
   Rol:         admin (acceso total)

👔 GERENTE:
   Usuario:     julian
   Contraseña:  197991
   Rol:         gerente (todas las funciones)

🚗 COBRADOR:
   Usuario:     marcos
   Contraseña:  Marcos123
   Rol:         cobrador (registrar cobros)

EMPRESA:         ElRuso
EMPRESA ID:      {empresa.id}

PRÓXIMOS PASOS:
  1. Ejecuta: python run.py
  2. Accede con cualquiera de los usuarios arriba
  3. ¡Listo para usar!
        """)
        
        return True
        
    except Exception as e:
        db.rollback()
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False
        
    finally:
        db.close()


if __name__ == "__main__":
    success = setup_elruso()
    sys.exit(0 if success else 1)
