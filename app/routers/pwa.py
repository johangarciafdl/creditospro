"""PWA router - Sync endpoints para offline support"""
from fastapi import APIRouter, Request, Depends
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from app.database import get_db, Cliente, Prestamo, Cuota, Cobro
from app.routers.auth import get_current_user
from app.utils.zone_permissions import get_allowed_zone_ids

router = APIRouter()

@router.get("/sync/clientes")
async def sync_clientes(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "No autorizado"}, status_code=401)
    allowed = get_allowed_zone_ids(db, user)
    clientes = db.query(Cliente).filter(
        Cliente.empresa_id == user.empresa_id, Cliente.activo == True
    ).limit(500).all()
    if allowed is not None:
        clientes = db.query(Cliente).filter(
            Cliente.empresa_id == user.empresa_id,
            Cliente.activo == True,
            Cliente.zona_id.in_(allowed or [-1]),
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
    allowed = get_allowed_zone_ids(db, user)
    prestamos = db.query(Prestamo).filter(
        Prestamo.empresa_id == user.empresa_id,
        Prestamo.estado.in_(["Activo", "activo", "Atrasado"])
    )
    if allowed is not None:
        prestamos = prestamos.filter(Prestamo.zona_id.in_(allowed or [-1]))
    prestamos = prestamos.limit(500).all()
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
    allowed = get_allowed_zone_ids(db, user)
    cuotas = db.query(Cuota).join(Prestamo, Cuota.prestamo_id == Prestamo.id).filter(
        Cuota.empresa_id == user.empresa_id,
        Prestamo.empresa_id == user.empresa_id,
        Cuota.estado == "Pendiente"
    )
    if allowed is not None:
        cuotas = cuotas.filter(Prestamo.zona_id.in_(allowed or [-1]))
    cuotas = cuotas.limit(1000).all()
    return JSONResponse([{
        "id": c.id, "prestamo_id": c.prestamo_id,
        "numero": c.numero,
        "valor": float(c.valor or 0),
        "fecha_vencimiento": c.fecha_vencimiento.isoformat() if c.fecha_vencimiento else None,
        "estado": c.estado or "Pendiente",
    } for c in cuotas])