"""Cobros router v2.1 - multi-tenant, fix TemplateResponse, fix None valor_pagado"""
from fastapi import APIRouter, Request, Depends, Form, HTTPException
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func
import datetime

from app.database import get_db, Cobro, Cuota, Prestamo, Cliente, Zona
from app.routers.auth import get_current_user

router = APIRouter()
templates = Jinja2Templates(directory="templates")


@router.get("")
@router.get("/")
async def listar_cobros(
    request: Request, zona_id: int = None, fecha: str = None,
    db: Session = Depends(get_db)
):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url="/auth/login?next=/cobros", status_code=302)

    eid = user.empresa_id
    hoy = datetime.date.today()
    try:
        fecha_sel = datetime.date.fromisoformat(fecha) if fecha else hoy
    except ValueError:
        fecha_sel = hoy

    query = db.query(Cuota, Prestamo, Cliente).join(
        Prestamo, Cuota.prestamo_id == Prestamo.id
    ).join(Cliente, Prestamo.cliente_id == Cliente.id).filter(
        Cuota.empresa_id == eid,
        Cuota.estado.in_(("Pendiente", "Vencida", "Parcial"))
    )
    if zona_id:
        query = query.filter(Prestamo.zona_id == zona_id)
    elif user.rol == "cobrador" and user.zona_id:
        query = query.filter(Prestamo.zona_id == user.zona_id)

    pendientes = query.order_by(Cuota.fecha_vencimiento).limit(200).all()
    zonas_map = {z.id: z for z in db.query(Zona).filter(Zona.empresa_id == eid).all()}

    cobros_hoy_map = {}
    for cobro in db.query(Cobro).filter(Cobro.empresa_id == eid, Cobro.fecha == fecha_sel).all():
        cobros_hoy_map[cobro.cuota_id] = cobro

    data = []
    for cuota, prestamo, cliente in pendientes:
        zona = zonas_map.get(prestamo.zona_id)
        cobro = cobros_hoy_map.get(cuota.id)
        data.append({
            "cuota_id": cuota.id, "prestamo_id": prestamo.id,
            "cliente_id": cliente.id, "cliente": cliente.nombre,
            "cedula": cliente.cedula,
            "zona": zona.nombre if zona else "—", "zona_id": prestamo.zona_id,
            "num_cuota": cuota.numero, "total_cuotas": prestamo.num_cuotas,
            "valor": cuota.valor,
            "vencimiento": cuota.fecha_vencimiento.strftime("%d/%m/%Y"),
            "dias_diff": (fecha_sel - cuota.fecha_vencimiento).days,
            "estado": cuota.estado,
            "cobrado": cobro is not None,
            "valor_cobrado": cobro.valor_cobrado if cobro else 0,
        })

    total_cobrado = db.query(func.sum(Cobro.valor_cobrado)).filter(
        Cobro.empresa_id == eid, Cobro.fecha == fecha_sel
    ).scalar() or 0
    total_pendiente = sum(d["valor"] for d in data if not d["cobrado"])

    return templates.TemplateResponse(request, "cobros.html", {
        "page": "cobros", "pendientes": data,
        "zonas": list(zonas_map.values()),
        "total_cobrado": total_cobrado,
        "total_pendiente": total_pendiente,
        "fecha_sel": fecha_sel.strftime("%Y-%m-%d"),
        "zona_id_sel": zona_id,
        "current_user": user,
    })


@router.post("/registrar")
async def registrar_cobro(
    request: Request,
    cuota_id: int = Form(...),
    valor_cobrado: float = Form(...),
    metodo_pago: str = Form("Efectivo"),
    cobrador: str = Form(""),
    observaciones: str = Form(""),
    lat: float = Form(None),
    lng: float = Form(None),
    db: Session = Depends(get_db)
):
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "No autenticado"}, status_code=401)

    cuota = db.query(Cuota).filter(
        Cuota.id == cuota_id, Cuota.empresa_id == user.empresa_id
    ).first()
    if not cuota:
        return JSONResponse({"error": "Cuota no encontrada"}, status_code=404)
    if cuota.estado == "Pagada":
        return JSONResponse({"error": "Cuota ya pagada"}, status_code=400)
    if valor_cobrado <= 0:
        return JSONResponse({"error": "Valor inválido"}, status_code=400)

    prestamo = db.query(Prestamo).filter(Prestamo.id == cuota.prestamo_id).first()

    cobro = Cobro(
        empresa_id=user.empresa_id,
        cuota_id=cuota_id, prestamo_id=prestamo.id,
        cliente_id=prestamo.cliente_id, zona_id=prestamo.zona_id,
        valor_cobrado=valor_cobrado, metodo_pago=metodo_pago,
        cobrador=cobrador or user.nombre,
        observaciones=observaciones,
        lat_cobro=lat, lng_cobro=lng,
        fecha=datetime.date.today(),
        usuario_id=user.id,
    )
    db.add(cobro)

    cuota.valor_pagado = cuota.valor_pagado + valor_cobrado
    if cuota.valor_pagado >= cuota.valor:
        cuota.estado = "Pagada"
        cuota.fecha_pago = datetime.date.today()
    else:
        cuota.estado = "Parcial"

    db.flush()
    # Cerrar préstamo si todas las cuotas están pagadas
    todas_pagadas = all(c.estado == "Pagada" for c in prestamo.cuotas)
    if todas_pagadas:
        prestamo.estado = "Cancelado"

    db.commit()
    return JSONResponse({
        "ok": True,
        "mensaje": f"Cobro de ${valor_cobrado:,.0f} registrado",
        "nuevo_estado": cuota.estado,
        "valor_pagado": cuota.valor_pagado,
    })


@router.get("/api/cuota/{cuota_id}")
async def info_cuota(request: Request, cuota_id: int, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        raise HTTPException(status_code=401)
    cuota = db.query(Cuota).filter(
        Cuota.id == cuota_id, Cuota.empresa_id == user.empresa_id
    ).first()
    if not cuota:
        raise HTTPException(status_code=404)
    prestamo = db.query(Prestamo).filter(Prestamo.id == cuota.prestamo_id).first()
    cliente = db.query(Cliente).filter(Cliente.id == prestamo.cliente_id).first()
    return {
        "cuota_id": cuota.id, "numero": cuota.numero,
        "valor": cuota.valor, "valor_pagado": cuota.valor_pagado,
        "pendiente": max(0.0, cuota.valor - cuota.valor_pagado),
        "estado": cuota.estado, "cliente": cliente.nombre,
        "telefono": cliente.whatsapp or cliente.telefono,
    }
