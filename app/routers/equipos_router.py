"""
CreditosPro - Equipment Management Router
Endpoints para gestión web de equipos y licencias.

Usa la capa de abstracción database_layer para funcionar con JSON o MySQL.

Endpoints:
  GET  /equipos/empresas                    - Listar empresas
  GET  /equipos/{empresa}                   - Listar equipos de empresa
  GET  /equipos/{empresa}/{equipo}          - Ver estado de equipo
  POST /equipos/{empresa}                   - Registrar equipo
  PUT  /equipos/{empresa}/{equipo}/renovar - Renovar licencia
  DELETE /equipos/{empresa}/{equipo}        - Eliminar equipo
  POST /equipos/exportar/{empresa}          - Exportar licencias
"""
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel
from typing import List, Dict, Optional
import json
import csv
import io
from pathlib import Path
from sqlalchemy.orm import Session

from app.database import get_db
from app.routers.auth import get_current_user

# Importar la capa de base de datos
try:
    from database_layer import EquipoManager, get_storage
    DB_AVAILABLE = True
except ImportError:
    DB_AVAILABLE = False
    print("⚠️  database_layer no disponible, algunos endpoints estarán limitados")


def require_equipment_admin(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user or user.rol != "superadmin":
        raise HTTPException(status_code=403, detail="Solo superadmin puede gestionar equipos y licencias")
    return user


router = APIRouter(
    tags=["equipos"],
    dependencies=[Depends(require_equipment_admin)],
)


# ============================================================
# MODELOS PYDANTIC
# ============================================================

class EquipoRequest(BaseModel):
    """Datos para registrar un equipo"""
    empresa_id: int
    machine_id: str
    nombre_equipo: str
    licencia: str
    vencimiento: str


class RenovarLicenciaRequest(BaseModel):
    """Datos para renovar una licencia"""
    licencia: str
    vencimiento: str


class EmpresaInfo(BaseModel):
    """Información de una empresa"""
    empresa_id: int
    nombre: str
    cantidad_equipos: int


class EquipoInfo(BaseModel):
    """Información de un equipo"""
    nombre: str
    machine_id: str
    vencimiento: str
    licencia_preview: str  # Solo primeros 50 chars
    registrado: str
    activa: bool
    dias_restantes: Optional[int] = None


# ============================================================
# UTILIDADES
# ============================================================

def calcular_dias_restantes(vencimiento: str) -> int:
    """Calcula los días restantes hasta vencimiento"""
    from datetime import datetime
    try:
        fecha_vencimiento = datetime.fromisoformat(vencimiento)
        dias = (fecha_vencimiento - datetime.now()).days
        return max(0, dias)
    except:
        return 0


# ============================================================
# ENDPOINTS
# ============================================================

@router.get("/", tags=["Health"])
async def health_equipos():
    """Health check del módulo de equipos"""
    return {
        "status": "ok",
        "modulo": "equipos",
        "storage": "mysql" if DB_AVAILABLE else "json",
        "endpoints": [
            "GET /equipos/empresas",
            "GET /equipos/{empresa}",
            "GET /equipos/{empresa}/{equipo}",
            "POST /equipos/{empresa}",
            "PUT /equipos/{empresa}/{equipo}/renovar",
            "DELETE /equipos/{empresa}/{equipo}",
            "POST /equipos/exportar/{empresa}"
        ]
    }


@router.get("/empresas", response_model=List[Dict])
async def listar_empresas():
    """Lista todas las empresas registradas"""
    if not DB_AVAILABLE:
        # Fallback a JSON local
        registry_path = Path(__file__).parent.parent / "licencias" / "equipos_registro.json"
        if registry_path.exists():
            data = json.loads(registry_path.read_text(encoding="utf-8"))
            empresas = []
            for nombre, info in data.items():
                empresas.append({
                    "nombre": nombre,
                    "empresa_id": info.get("empresa_id"),
                    "cantidad_equipos": len(info.get("equipos", []))
                })
            return empresas
        return []
    
    # Con base de datos
    try:
        storage = get_storage()
        # Obtener empresas únicas (simplificado)
        registry_path = Path(__file__).parent.parent / "licencias" / "equipos_registro.json"
        if registry_path.exists():
            data = json.loads(registry_path.read_text(encoding="utf-8"))
            empresas = []
            for nombre, info in data.items():
                empresas.append({
                    "nombre": nombre,
                    "empresa_id": info.get("empresa_id"),
                    "cantidad_equipos": len(info.get("equipos", []))
                })
            return empresas
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")
    
    return []


@router.get("/{empresa}", response_model=List[Dict])
async def listar_equipos(empresa: str):
    """Lista equipos de una empresa"""
    if not DB_AVAILABLE:
        registry_path = Path(__file__).parent.parent / "licencias" / "equipos_registro.json"
        if registry_path.exists():
            data = json.loads(registry_path.read_text(encoding="utf-8"))
            if empresa in data:
                equipos = []
                for eq in data[empresa].get("equipos", []):
                    eq_info = eq.copy()
                    eq_info["dias_restantes"] = calcular_dias_restantes(eq.get("vencimiento", ""))
                    eq_info["licencia_preview"] = eq.get("licencia", "")[:50] + "..."
                    equipos.append(eq_info)
                return equipos
        raise HTTPException(status_code=404, detail=f"Empresa '{empresa}' no encontrada")
    
    try:
        manager = EquipoManager()
        equipos = manager.listar(empresa)
        
        for eq in equipos:
            eq["dias_restantes"] = calcular_dias_restantes(eq.get("vencimiento", ""))
            eq["licencia_preview"] = eq.get("licencia", "")[:50] + "..."
        
        return equipos
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")


@router.get("/{empresa}/{equipo}", response_model=Dict)
async def obtener_equipo(empresa: str, equipo: str):
    """Obtiene información detallada de un equipo"""
    if not DB_AVAILABLE:
        registry_path = Path(__file__).parent.parent / "licencias" / "equipos_registro.json"
        if registry_path.exists():
            data = json.loads(registry_path.read_text(encoding="utf-8"))
            if empresa in data:
                for eq in data[empresa].get("equipos", []):
                    if eq["nombre"].lower() == equipo.lower():
                        eq["dias_restantes"] = calcular_dias_restantes(eq.get("vencimiento", ""))
                        return eq
        raise HTTPException(status_code=404, detail=f"Equipo '{equipo}' no encontrado")
    
    try:
        manager = EquipoManager()
        eq = manager.obtener(empresa, equipo)
        
        if not eq:
            raise HTTPException(status_code=404, detail=f"Equipo '{equipo}' no encontrado")
        
        eq["dias_restantes"] = calcular_dias_restantes(eq.get("vencimiento", ""))
        return eq
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")


@router.post("/{empresa}")
async def registrar_equipo(empresa: str, datos: EquipoRequest):
    """Registra un nuevo equipo"""
    if not DB_AVAILABLE:
        raise HTTPException(status_code=503, detail="Base de datos no disponible")
    
    try:
        manager = EquipoManager()
        success = manager.registrar(
            empresa,
            datos.empresa_id,
            datos.machine_id,
            datos.nombre_equipo,
            datos.licencia,
            datos.vencimiento
        )
        
        if success:
            return {
                "status": "success",
                "mensaje": f"Equipo '{datos.nombre_equipo}' registrado",
                "equipo": {
                    "nombre": datos.nombre_equipo,
                    "machine_id": datos.machine_id,
                    "vencimiento": datos.vencimiento,
                    "dias_restantes": calcular_dias_restantes(datos.vencimiento)
                }
            }
        else:
            raise HTTPException(status_code=400, detail="Error al registrar equipo")
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")


@router.put("/{empresa}/{equipo}/renovar")
async def renovar_licencia(empresa: str, equipo: str, datos: RenovarLicenciaRequest):
    """Renueva la licencia de un equipo"""
    if not DB_AVAILABLE:
        raise HTTPException(status_code=503, detail="Base de datos no disponible")
    
    try:
        manager = EquipoManager()
        success = manager.renovar(empresa, equipo, datos.licencia, datos.vencimiento)
        
        if success:
            return {
                "status": "success",
                "mensaje": f"Licencia de '{equipo}' renovada",
                "datos": {
                    "vencimiento": datos.vencimiento,
                    "dias_restantes": calcular_dias_restantes(datos.vencimiento)
                }
            }
        else:
            raise HTTPException(status_code=404, detail=f"Equipo '{equipo}' no encontrado")
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")


@router.delete("/{empresa}/{equipo}")
async def eliminar_equipo(empresa: str, equipo: str):
    """Elimina un equipo del registro"""
    if not DB_AVAILABLE:
        raise HTTPException(status_code=503, detail="Base de datos no disponible")
    
    try:
        manager = EquipoManager()
        success = manager.eliminar(empresa, equipo)
        
        if success:
            return {"status": "success", "mensaje": f"Equipo '{equipo}' eliminado"}
        else:
            raise HTTPException(status_code=404, detail=f"Equipo '{equipo}' no encontrado")
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")


@router.post("/exportar/{empresa}")
async def exportar_licencias(empresa: str, formato: str = Query("json", regex="^(json|csv)$")):
    """Exporta las licencias de una empresa"""
    try:
        manager = EquipoManager()
        equipos = manager.listar(empresa)
        
        if formato == "csv":
            output = io.StringIO(newline="")
            writer = csv.writer(output)
            writer.writerow(["Equipo", "Machine ID", "Vencimiento", "Licencia (primeros 50 chars)"])
            for eq in equipos:
                licencia_short = eq.get("licencia", "")[:50]
                writer.writerow(
                    [eq["nombre"], eq["machine_id"], eq["vencimiento"], licencia_short]
                )
            
            return {
                "formato": "csv",
                "contenido": output.getvalue(),
                "cantidad": len(equipos)
            }
        
        else:
            # Formato JSON
            return {
                "formato": "json",
                "empresa": empresa,
                "equipos": equipos,
                "cantidad": len(equipos)
            }
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")


# ============================================================
# ESTADÍSTICAS
# ============================================================

@router.get("/stats/resumen", response_model=Dict)
async def resumen_estadisticas():
    """Resumen general del sistema de equipos"""
    try:
        registry_path = Path(__file__).parent.parent / "licencias" / "equipos_registro.json"
        
        total_equipos = 0
        total_empresas = 0
        proximos_a_vencer = []
        
        if registry_path.exists():
            data = json.loads(registry_path.read_text(encoding="utf-8"))
            
            for empresa, info in data.items():
                total_empresas += 1
                equipos = info.get("equipos", [])
                total_equipos += len(equipos)
                
                for eq in equipos:
                    dias_restantes = calcular_dias_restantes(eq.get("vencimiento", ""))
                    if 0 <= dias_restantes <= 30:  # Próximos 30 días
                        proximos_a_vencer.append({
                            "empresa": empresa,
                            "equipo": eq["nombre"],
                            "dias_restantes": dias_restantes,
                            "vencimiento": eq.get("vencimiento")
                        })
        
        return {
            "total_equipos": total_equipos,
            "total_empresas": total_empresas,
            "proximos_a_vencer": sorted(proximos_a_vencer, key=lambda x: x["dias_restantes"]),
            "advertencia": "Renovar licencias con ≤30 días de vencimiento"
        }
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")
