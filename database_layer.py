#!/usr/bin/env python3
"""
CreditosPro Database Layer
Capa de abstracción para trabajar con Supabase o MySQL indistintamente.

Uso:
    from database_layer import EquipoManager, LicenciaManager
    
    manager = EquipoManager()
    manager.registrar("ElRusso", 1, "ABC123", "PC-01")
    equipos = manager.listar("ElRusso")
"""
import json
import os
from pathlib import Path
from typing import List, Dict, Optional
from datetime import datetime

# ============================================================
# CONFIGURACIÓN
# ============================================================

# Tipos de almacenamiento
STORAGE_TYPE = os.getenv("STORAGE_TYPE", "json")  # "json" o "mysql"
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_USER = os.getenv("DB_USER", "root")
DB_PASSWORD = os.getenv("DB_PASSWORD", "")
DB_NAME = os.getenv("DB_NAME", "creditospro")

JSON_REGISTRY_PATH = Path(__file__).parent.parent / "licencias" / "equipos_registro.json"


# ============================================================
# INTERFAZ BASE (Abstracción)
# ============================================================

class IEquipoStorage:
    """Interfaz para almacenamiento de equipos"""
    
    def crear_empresa(self, empresa_id: int, empresa_nombre: str) -> bool:
        """Crea una empresa"""
        raise NotImplementedError
    
    def registrar_equipo(self, empresa_nombre: str, empresa_id: int, 
                        machine_id: str, nombre_equipo: str, 
                        licencia: str, vencimiento: str) -> bool:
        """Registra un nuevo equipo"""
        raise NotImplementedError
    
    def listar_equipos(self, empresa_nombre: str) -> List[Dict]:
        """Lista equipos de una empresa"""
        raise NotImplementedError
    
    def obtener_equipo(self, empresa_nombre: str, nombre_equipo: str) -> Optional[Dict]:
        """Obtiene datos de un equipo específico"""
        raise NotImplementedError
    
    def eliminar_equipo(self, empresa_nombre: str, nombre_equipo: str) -> bool:
        """Elimina un equipo"""
        raise NotImplementedError
    
    def actualizar_licencia(self, empresa_nombre: str, nombre_equipo: str, 
                           licencia: str, vencimiento: str) -> bool:
        """Actualiza la licencia de un equipo"""
        raise NotImplementedError


# ============================================================
# IMPLEMENTACIÓN: JSON
# ============================================================

class JsonEquipoStorage(IEquipoStorage):
    """Almacenamiento usando JSON local"""
    
    def __init__(self, path: Path = JSON_REGISTRY_PATH):
        self.path = path
        self.path.parent.mkdir(exist_ok=True)
        if not self.path.exists():
            self.path.write_text("{}", encoding="utf-8")
    
    def _load(self) -> dict:
        """Carga el registro JSON"""
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except:
            return {}
    
    def _save(self, data: dict):
        """Guarda el registro JSON"""
        self.path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    
    def crear_empresa(self, empresa_id: int, empresa_nombre: str) -> bool:
        data = self._load()
        if empresa_nombre not in data:
            data[empresa_nombre] = {
                "empresa_id": empresa_id,
                "equipos": []
            }
            self._save(data)
            return True
        return False
    
    def registrar_equipo(self, empresa_nombre: str, empresa_id: int,
                        machine_id: str, nombre_equipo: str,
                        licencia: str, vencimiento: str) -> bool:
        data = self._load()
        
        if empresa_nombre not in data:
            self.crear_empresa(empresa_id, empresa_nombre)
            data = self._load()
        
        # Eliminar si existe
        data[empresa_nombre]["equipos"] = [
            e for e in data[empresa_nombre]["equipos"]
            if e["nombre"].lower() != nombre_equipo.lower()
        ]
        
        # Agregar nuevo
        data[empresa_nombre]["equipos"].append({
            "nombre": nombre_equipo,
            "machine_id": machine_id,
            "licencia": licencia,
            "vencimiento": vencimiento,
            "registrado": datetime.now().isoformat(),
            "activa": True
        })
        
        self._save(data)
        return True
    
    def listar_equipos(self, empresa_nombre: str) -> List[Dict]:
        data = self._load()
        if empresa_nombre in data:
            return data[empresa_nombre].get("equipos", [])
        return []
    
    def obtener_equipo(self, empresa_nombre: str, nombre_equipo: str) -> Optional[Dict]:
        equipos = self.listar_equipos(empresa_nombre)
        for eq in equipos:
            if eq["nombre"].lower() == nombre_equipo.lower():
                return eq
        return None
    
    def eliminar_equipo(self, empresa_nombre: str, nombre_equipo: str) -> bool:
        data = self._load()
        if empresa_nombre not in data:
            return False
        
        before = len(data[empresa_nombre]["equipos"])
        data[empresa_nombre]["equipos"] = [
            e for e in data[empresa_nombre]["equipos"]
            if e["nombre"].lower() != nombre_equipo.lower()
        ]
        after = len(data[empresa_nombre]["equipos"])
        
        if before > after:
            self._save(data)
            return True
        return False
    
    def actualizar_licencia(self, empresa_nombre: str, nombre_equipo: str,
                           licencia: str, vencimiento: str) -> bool:
        data = self._load()
        if empresa_nombre not in data:
            return False
        
        for eq in data[empresa_nombre]["equipos"]:
            if eq["nombre"].lower() == nombre_equipo.lower():
                eq["licencia"] = licencia
                eq["vencimiento"] = vencimiento
                self._save(data)
                return True
        return False


# ============================================================
# IMPLEMENTACIÓN: MySQL (Opcional)
# ============================================================

class MysqlEquipoStorage(IEquipoStorage):
    """Almacenamiento usando MySQL (requerida instalación previa)"""
    
    def __init__(self):
        try:
            from sqlalchemy import create_engine, Column, Integer, String, DateTime, Boolean
            from sqlalchemy.ext.declarative import declarative_base
            from sqlalchemy.orm import sessionmaker
            
            # Configurar conexión
            connection_string = f"mysql+pymysql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}/{DB_NAME}"
            self.engine = create_engine(connection_string, echo=False)
            Session = sessionmaker(bind=self.engine)
            self.session = Session()
            
            # Definir modelo
            Base = declarative_base()
            
            class Equipo(Base):
                __tablename__ = 'equipos'
                id = Column(Integer, primary_key=True)
                empresa_nombre = Column(String(255))
                empresa_id = Column(Integer)
                nombre = Column(String(255))
                machine_id = Column(String(255))
                licencia = Column(String(2000))
                vencimiento = Column(String(50))
                registrado = Column(DateTime, default=datetime.now)
                activa = Column(Boolean, default=True)
            
            self.Equipo = Equipo
            Base.metadata.create_all(self.engine)
            
        except Exception as e:
            raise RuntimeError(f"No se pudo conectar a MySQL: {e}. ¿Está instalado y corriendo?")
    
    def crear_empresa(self, empresa_id: int, empresa_nombre: str) -> bool:
        # En MySQL, no hay necesidad de crear empresa explícitamente
        return True
    
    def registrar_equipo(self, empresa_nombre: str, empresa_id: int,
                        machine_id: str, nombre_equipo: str,
                        licencia: str, vencimiento: str) -> bool:
        try:
            # Eliminar si existe
            self.session.query(self.Equipo).filter(
                self.Equipo.empresa_nombre == empresa_nombre,
                self.Equipo.nombre == nombre_equipo
            ).delete()
            
            # Agregar nuevo
            equipo = self.Equipo(
                empresa_nombre=empresa_nombre,
                empresa_id=empresa_id,
                nombre=nombre_equipo,
                machine_id=machine_id,
                licencia=licencia,
                vencimiento=vencimiento,
                activa=True
            )
            self.session.add(equipo)
            self.session.commit()
            return True
        except Exception as e:
            self.session.rollback()
            print(f"Error registrando equipo: {e}")
            return False
    
    def listar_equipos(self, empresa_nombre: str) -> List[Dict]:
        try:
            equipos = self.session.query(self.Equipo).filter(
                self.Equipo.empresa_nombre == empresa_nombre
            ).all()
            
            return [
                {
                    "nombre": e.nombre,
                    "machine_id": e.machine_id,
                    "licencia": e.licencia,
                    "vencimiento": e.vencimiento,
                    "registrado": e.registrado.isoformat() if e.registrado else "",
                    "activa": e.activa
                }
                for e in equipos
            ]
        except Exception as e:
            print(f"Error listando equipos: {e}")
            return []
    
    def obtener_equipo(self, empresa_nombre: str, nombre_equipo: str) -> Optional[Dict]:
        try:
            equipo = self.session.query(self.Equipo).filter(
                self.Equipo.empresa_nombre == empresa_nombre,
                self.Equipo.nombre == nombre_equipo
            ).first()
            
            if equipo:
                return {
                    "nombre": equipo.nombre,
                    "machine_id": equipo.machine_id,
                    "licencia": equipo.licencia,
                    "vencimiento": equipo.vencimiento,
                    "registrado": equipo.registrado.isoformat() if equipo.registrado else "",
                    "activa": equipo.activa
                }
        except Exception as e:
            print(f"Error obteniendo equipo: {e}")
        
        return None
    
    def eliminar_equipo(self, empresa_nombre: str, nombre_equipo: str) -> bool:
        try:
            count = self.session.query(self.Equipo).filter(
                self.Equipo.empresa_nombre == empresa_nombre,
                self.Equipo.nombre == nombre_equipo
            ).delete()
            self.session.commit()
            return count > 0
        except Exception as e:
            self.session.rollback()
            print(f"Error eliminando equipo: {e}")
            return False
    
    def actualizar_licencia(self, empresa_nombre: str, nombre_equipo: str,
                           licencia: str, vencimiento: str) -> bool:
        try:
            self.session.query(self.Equipo).filter(
                self.Equipo.empresa_nombre == empresa_nombre,
                self.Equipo.nombre == nombre_equipo
            ).update({
                self.Equipo.licencia: licencia,
                self.Equipo.vencimiento: vencimiento
            })
            self.session.commit()
            return True
        except Exception as e:
            self.session.rollback()
            print(f"Error actualizando licencia: {e}")
            return False


# ============================================================
# FACTORY (Crea la instancia correcta)
# ============================================================

def get_storage() -> IEquipoStorage:
    """Retorna la implementación correcta según configuración"""
    if STORAGE_TYPE.lower() == "mysql":
        print("📊 Usando almacenamiento: MySQL")
        return MysqlEquipoStorage()
    else:
        print("📊 Usando almacenamiento: JSON")
        return JsonEquipoStorage()


# ============================================================
# MANAGERS (Interfaz simplificada)
# ============================================================

class EquipoManager:
    """Manager simplificado para equipos"""
    
    def __init__(self):
        self.storage = get_storage()
    
    def registrar(self, empresa: str, empresa_id: int, machine_id: str,
                 nombre_equipo: str, licencia: str, vencimiento: str) -> bool:
        """Registra un nuevo equipo"""
        return self.storage.registrar_equipo(
            empresa, empresa_id, machine_id, nombre_equipo, licencia, vencimiento
        )
    
    def listar(self, empresa: str) -> List[Dict]:
        """Lista equipos de una empresa"""
        return self.storage.listar_equipos(empresa)
    
    def obtener(self, empresa: str, nombre_equipo: str) -> Optional[Dict]:
        """Obtiene un equipo específico"""
        return self.storage.obtener_equipo(empresa, nombre_equipo)
    
    def eliminar(self, empresa: str, nombre_equipo: str) -> bool:
        """Elimina un equipo"""
        return self.storage.eliminar_equipo(empresa, nombre_equipo)
    
    def renovar(self, empresa: str, nombre_equipo: str, licencia: str, vencimiento: str) -> bool:
        """Renueva la licencia de un equipo"""
        return self.storage.actualizar_licencia(empresa, nombre_equipo, licencia, vencimiento)


# ============================================================
# EJEMPLO DE USO
# ============================================================

if __name__ == "__main__":
    # Uso con JSON (por defecto)
    manager = EquipoManager()
    
    # Registrar
    manager.registrar("ElRusso", 1, "ABC123", "PC-TEST", "CPRO-...", "2027-08-16")
    
    # Listar
    equipos = manager.listar("ElRusso")
    print(f"Equipos: {len(equipos)}")
    
    # Obtener
    equipo = manager.obtener("ElRusso", "PC-TEST")
    print(f"Equipo: {equipo}")
    
    # Renovar
    manager.renovar("ElRusso", "PC-TEST", "CPRO-NUEVO", "2028-08-16")
    
    print("✅ Database layer funcionando")
