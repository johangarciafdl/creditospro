"""Cobros router - FIXED"""
from fastapi import APIRouter, Request, Depends, Form
from fastapi.responses import JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy import func
import datetime

from app.database import get_db, Cobro, Cuota, Prestamo, Cliente, Zona
from app.auth import require_login, get_current_empresa

router = APIRouter()
templates = Jinja2Templates(directory="templates")


@router.get("/")
async def listar_cobros(
    request: Request,
    zona_id: int = None,
    fecha: str = None,
    db: Session = Depends(get_db),
    current_user=Depends(require_login),
    empresa_id: int = Depends(get_current_empresa)
):
    hoy = datetime.date.today()
    fecha_sel = datetime.date.fromisoformat(fecha) if fecha else hoy

    query = db.query(Cuota, Prestamo, Cliente).join(
        Prestamo, Cuota.prestamo_id == Prestamo.id
    ).join(Cliente, Prestamo.cliente_id == Cliente.id).filter(
        Cuota.estado.in_(["Pendiente", "Vencida"]),
        Prestamo.empresa_id == empresa_id
    )
    if zona_id:
        query = query.filter(Prestamo.zona_id == zona_id)

    pendientes = query.order_by(Cuota.fecha_vencimiento).limit(200).all()

    data = []
    for cuota, prestamo, cliente in pendientes:
        zona = db.query(Zona).filter(Zona.id == prestamo.zona_id).first()
        cobro_hecho = db.query(Cobro).filter(
            Cobro.cuota_id == cuota.id,
            Cobro.fecha == fecha_sel
        ).first()
        data.append({
            "cuota_id": cuota.id,
            "prestamo_id": prestamo.id,
            "cliente_id": cliente.id,
            "cliente": cliente.nombre,
            "cedula": cliente.cedula,
            "zona": zona.nombre if zona else "—",
            "zona_id": prestamo.zona_id,
            "num_cuota": cuota.numero,
            "total_cuotas": prestamo.num_cuotas,
            "valor": cuota.valor,
            "vencimiento": cuota.fecha_vencimiento.strftime("%d/%m/%Y"),
            "dias_diff": (fecha_sel - cuota.fecha_vencimiento).days,
            "estado": cuota.estado,
            "cobrado": cobro_hecho is not None,
            "valor_cobrado": cobro_hecho.valor_cobrado if cobro_hecho else 0,
        })

    total_cobrado = db.query(func.sum(Cobro.valor_cobrado)).filter(
        Cobro.fecha == fecha_sel,
        Cobro.empresa_id == empresa_id
    ).scalar() or 0
    total_pendiente = sum(d["valor"] for d in data if not d["cobrado"])

    zonas = db.query(Zona).filter(Zona.empresa_id == empresa_id).all()
    return templates.TemplateResponse("cobros.html", {
        "request": request, "page": "cobros",
        "pendientes": data, "zonas": zonas,
        "total_cobrado": total_cobrado,
        "total_pendiente": total_pendiente,
        "fecha_sel": fecha_sel.strftime("%Y-%m-%d"),
        "zona_id_sel": zona_id,
        "current_user": current_user,
    })


@router.post("/registrar")
async def registrar_cobro(
    cuota_id: int = Form(...),
    valor_cobrado: float = Form(...),
    metodo_pago: str = Form("Efectivo"),
    cobrador: str = Form(""),
    observaciones: str = Form(""),
    lat: str = Form(""),
    lng: str = Form(""),
    db: Session = Depends(get_db),
    current_user=Depends(require_login),
    empresa_id: int = Depends(get_current_empresa)
):
    if valor_cobrado <= 0:
        return JSONResponse({"ok": False, "detail": "El valor debe ser mayor a 0"}, status_code=400)

    cuota = db.query(Cuota).filter(Cuota.id == cuota_id).first()
    if not cuota:
        return JSONResponse({"ok": False, "detail": "Cuota no encontrada"}, status_code=404)
    if cuota.estado == "Pagada":
        return JSONResponse({"ok": False, "detail": "Esta cuota ya fue pagada"}, status_code=400)

    prestamo = db.query(Prestamo).filter(Prestamo.id == cuota.prestamo_id).first()
    if not prestamo:
        return JSONResponse({"ok": False, "detail": "Prestamo no encontrado"}, status_code=404)

    try:
        cobro = Cobro(
            empresa_id=empresa_id,
            cuota_id=cuota_id,
            prestamo_id=prestamo.id,
            cliente_id=prestamo.cliente_id,
            zona_id=prestamo.zona_id,
            valor_cobrado=valor_cobrado,
            metodo_pago=metodo_pago,
            cobrador=cobrador or (current_user.nombre_completo if current_user else ""),
            observaciones=observaciones or None,
            lat_cobro=float(lat) if lat and lat.strip() else None,
            lng_cobro=float(lng) if lng and lng.strip() else None,
            fecha=datetime.date.today(),
            usuario_id=current_user.id if current_user else None,
        )
        db.add(cobro)

        cuota.valor_pagado = (cuota.valor_pagado or 0) + valor_cobrado
        if cuota.valor_pagado >= cuota.valor:
            cuota.estado = "Pagada"
            cuota.fecha_pago = datetime.date.today()
        else:
            cuota.estado = "Parcial"

        cuotas_pendientes = [c for c in prestamo.cuotas if c.estado not in ["Pagada"]]
        if not cuotas_pendientes:
            prestamo.estado = "Cancelado"

        db.commit()
        return JSONResponse({"ok": True, "mensaje": f"Cobro de ${valor_cobrado:,.0f} registrado"})
    except Exception as e:
        db.rollback()
        return JSONResponse({"ok": False, "detail": str(e)}, status_code=500)
