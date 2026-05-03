"""Prestamos router v2.1 - multi-tenant, fix N+1, fix TemplateResponse"""
from fastapi import APIRouter, Request, Depends, Form, HTTPException
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session, joinedload
import datetime

from app.database import get_db, Prestamo, Cliente, Cuota, Zona
from app.routers.auth import get_current_user
from app.services.prestamo_service import calcular_cuotas

router = APIRouter()
templates = Jinja2Templates(directory="templates")


@router.get("")
@router.get("/")
async def listar_prestamos(
    request: Request,
    estado: str = "",
    zona_id: int = None,
    db: Session = Depends(get_db)
):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url="/auth/login?next=/prestamos", status_code=302)

    # FIX N+1: eager load cliente y cuotas en una sola query
    query = db.query(Prestamo).options(
        joinedload(Prestamo.cliente),
        joinedload(Prestamo.cuotas)
    ).filter(Prestamo.empresa_id == user.empresa_id)

    if estado:
        query = query.filter(Prestamo.estado == estado)
    if zona_id:
        query = query.filter(Prestamo.zona_id == zona_id)
    elif user.rol == "cobrador" and user.zona_id:
        query = query.filter(Prestamo.zona_id == user.zona_id)

    prestamos = query.order_by(Prestamo.creado.desc()).all()

    # Cargar zonas una vez
    zonas_map = {z.id: z for z in db.query(Zona).filter(Zona.empresa_id == user.empresa_id).all()}

    data = []
    for p in prestamos:
        cliente = p.cliente
        zona = zonas_map.get(p.zona_id)
        # FIX: valor_pagado nunca None (default 0.0 en DB)
        pagado = sum(c.valor_pagado for c in p.cuotas)
        saldo = max(0.0, (p.total_pagar or 0) - pagado)
        vencidas = sum(1 for c in p.cuotas if c.estado == "Vencida")
        prox = next((c for c in sorted(p.cuotas, key=lambda x: x.numero)
                     if c.estado in ("Pendiente", "Vencida")), None)
        data.append({
            "id": p.id,
            "cliente": cliente.nombre if cliente else "—",
            "cedula": cliente.cedula if cliente else "—",
            "capital": p.capital, "total": p.total_pagar,
            "saldo": saldo, "pagado": pagado,
            "num_cuotas": p.num_cuotas, "valor_cuota": p.valor_cuota,
            "cuota_actual": prox.numero if prox else "—",
            "vencidas": vencidas, "estado": p.estado,
            "zona": zona.nombre if zona else "—",
            "fecha_inicio": p.fecha_inicio.strftime("%d/%m/%Y") if p.fecha_inicio else "—",
            "fecha_fin": p.fecha_fin.strftime("%d/%m/%Y") if p.fecha_fin else "—",
            "tipo_cliente": cliente.tipo_cliente if cliente else "—",
        })

    return templates.TemplateResponse(request, "prestamos.html", {
        "page": "prestamos",
        "prestamos": data,
        "zonas": list(zonas_map.values()),
        "estado_sel": estado,
        "zona_id_sel": zona_id,
        "current_user": user,
    })


@router.post("/nuevo")
async def crear_prestamo(
    request: Request,
    cliente_id: int = Form(...),
    zona_id: int = Form(...),
    capital: float = Form(...),
    tasa_interes: float = Form(20.0),
    num_cuotas: int = Form(...),
    plazo_dias: int = Form(30),
    fecha_inicio: str = Form(""),
    cobrador: str = Form(""),
    observaciones: str = Form(""),
    db: Session = Depends(get_db)
):
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "No autenticado"}, status_code=401)

    cliente = db.query(Cliente).filter(
        Cliente.id == cliente_id,
        Cliente.empresa_id == user.empresa_id
    ).first()
    if not cliente:
        return JSONResponse({"error": "Cliente no encontrado"}, status_code=404)

    if capital <= 0:
        return JSONResponse({"error": "Capital inválido"}, status_code=400)
    if num_cuotas <= 0:
        return JSONResponse({"error": "Número de cuotas inválido"}, status_code=400)

    fecha = datetime.date.fromisoformat(fecha_inicio) if fecha_inicio else datetime.date.today()
    calc = calcular_cuotas(capital, tasa_interes, num_cuotas, fecha, plazo_dias)

    prestamo = Prestamo(
        empresa_id=user.empresa_id,
        cliente_id=cliente_id, zona_id=zona_id,
        capital=capital, tasa_interes=tasa_interes,
        interes_total=calc["interes_total"], total_pagar=calc["total_pagar"],
        num_cuotas=num_cuotas, valor_cuota=calc["valor_cuota"],
        plazo_dias=plazo_dias, fecha_inicio=fecha, fecha_fin=calc["fecha_fin"],
        cobrador=cobrador or user.nombre, observaciones=observaciones,
        estado="Activo",
    )
    db.add(prestamo)
    db.flush()

    for c in calc["cuotas"]:
        db.add(Cuota(
            empresa_id=user.empresa_id,
            prestamo_id=prestamo.id,
            numero=c["numero"], valor=c["valor"],
            fecha_vencimiento=c["fecha_vencimiento"],
            estado="Pendiente", valor_pagado=0.0,
        ))

    db.commit()
    return JSONResponse({"ok": True, "id": prestamo.id, "mensaje": "Préstamo registrado"})


@router.get("/calcular")
async def calcular_preview(capital: float, tasa: float, cuotas: int, plazo: int = 30):
    calc = calcular_cuotas(capital, tasa, cuotas, datetime.date.today(), plazo)
    return {
        "interes_total": calc["interes_total"],
        "total_pagar": calc["total_pagar"],
        "valor_cuota": calc["valor_cuota"],
    }
