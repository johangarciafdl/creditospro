"""PWA router - Sync endpoints para offline support"""
from fastapi import APIRouter, Request, Depends
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from app.database import get_db, Cliente, Prestamo, Cuota, Cobro
from app.routers.auth import get_current_user

router = APIRouter()

@router.get("/sync/clientes")
async def sync_clientes(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "No autorizado"}, status_code=401)
    clientes = db.query(Cliente).filter(
        Cliente.empresa_id == user.empresa_id, Cliente.activo == True
    ).limit(500).all()
    return JSONResponse([{
        "id": c.id, "cedula": c.cedula, "nombre": c.nombre,
        "telefono": c.telefono or "", "zona_id": c.zona_id,
        "tipo_cliente": c.tipo_cliente or "Regular",
        "creado": c.creado.isoformat() if c.creado else None,
    } for c in clientes])

@router.get("/sync/prestamos")
async def sync_prestamos(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "No autorizado"}, status_code=401)
    prestamos = db.query(Prestamo).filter(
        Prestamo.empresa_id == user.empresa_id,
        Prestamo.estado.in_(["Activo", "activo", "Atrasado"])
    ).limit(500).all()
    return JSONResponse([{
        "id": p.id, "cliente_id": p.cliente_id,
        "capital": float(p.capital or 0),
        "total_pagar": float(p.total_pagar or p.capital or 0),
        "num_cuotas": p.num_cuotas or 0,
        "valor_cuota": float(p.valor_cuota or 0),
        "estado": p.estado or "Activo",
        "fecha_inicio": p.fecha_inicio.isoformat() if p.fecha_inicio else None,
    } for p in prestamos])

@router.get("/sync/cuotas")
async def sync_cuotas(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "No autorizado"}, status_code=401)
    cuotas = db.query(Cuota).filter(
        Cuota.empresa_id == user.empresa_id,
        Cuota.estado == "Pendiente"
    ).limit(1000).all()
    return JSONResponse([{
        "id": c.id, "prestamo_id": c.prestamo_id,
        "numero": c.numero,
        "valor": float(c.valor or 0),
        "fecha_vencimiento": c.fecha_vencimiento.isoformat() if c.fecha_vencimiento else None,
        "estado": c.estado or "Pendiente",
    } for c in cuotas])