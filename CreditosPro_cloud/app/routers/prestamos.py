# -*- coding: utf-8 -*-
"""Prestamos router v2 - BUGS CORREGIDOS"""
from fastapi import APIRouter, Request, Depends, Form
from fastapi.responses import JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from pathlib import Path
import datetime

from app.database import get_db, Prestamo, Cliente, Cuota, Zona
from app.services.prestamo_service import calcular_cuotas
from app.auth import require_login, get_current_empresa

BASE_DIR = Path(__file__).parent.parent.parent
router = APIRouter()
templates = Jinja2Templates(directory="templates")


@router.get("/")
async def listar_prestamos(
    request: Request,
    estado: str = "",
    zona_id: int = None,
    db: Session = Depends(get_db),
    current_user=Depends(require_login),
    empresa_id: int = Depends(get_current_empresa),
):
    query = db.query(Prestamo).filter(Prestamo.empresa_id == empresa_id)
    if estado:
        query = query.filter(Prestamo.estado == estado)
    if zona_id:
        query = query.filter(Prestamo.zona_id == zona_id)
    prestamos = query.order_by(Prestamo.creado.desc()).all()

    data = []
    for p in prestamos:
        cliente = p.cliente
        zona = db.query(Zona).filter(Zona.id == p.zona_id).first()
        pagado = sum(c.valor_pagado or 0 for c in p.cuotas)
        saldo = max(0, p.total_pagar - pagado)
        vencidas = sum(1 for c in p.cuotas if c.estado == "Vencida")
        prox_cuota = next(
            (c for c in sorted(p.cuotas, key=lambda x: x.numero)
             if c.estado in ["Pendiente", "Vencida"]), None
        )
        data.append({
            "id": p.id, "cliente": cliente.nombre, "cedula": cliente.cedula,
            "capital": p.capital, "total": p.total_pagar, "saldo": saldo, "pagado": pagado,
            "num_cuotas": p.num_cuotas, "valor_cuota": p.valor_cuota,
            "cuota_actual": prox_cuota.numero if prox_cuota else "—",
            "vencidas": vencidas, "estado": p.estado,
            "zona": zona.nombre if zona else "—",
            "fecha_inicio": p.fecha_inicio.strftime("%d/%m/%Y") if p.fecha_inicio else "—",
            "fecha_fin": p.fecha_fin.strftime("%d/%m/%Y") if p.fecha_fin else "—",
            "tipo_cliente": cliente.tipo_cliente,
        })

    zonas = db.query(Zona).filter(Zona.empresa_id == empresa_id).all()
    return templates.TemplateResponse("prestamos.html", context={
        "request": request, "page": "prestamos",
        "prestamos": data, "zonas": zonas,
        "estado_sel": estado, "zona_id_sel": zona_id,
        "current_user": current_user,
    })


@router.get("/calcular")
async def calcular_preview(capital: float, tasa: float, cuotas: int, plazo: int = 30):
    """Preview de calculo — sin login para llamadas AJAX internas"""
    from datetime import date
    if capital <= 0 or cuotas <= 0 or tasa < 0:
        return JSONResponse({"error": "Parametros invalidos"}, status_code=400)
    calc = calcular_cuotas(capital, tasa, cuotas, date.today(), plazo)
    return {
        "interes_total": calc["interes_total"],
        "total_pagar": calc["total_pagar"],
        "valor_cuota": calc["valor_cuota"],
    }


@router.post("/nuevo")
async def crear_prestamo(
    cliente_id: int = Form(...),
    zona_id: int = Form(...),
    capital: float = Form(...),
    tasa_interes: float = Form(20.0),
    num_cuotas: int = Form(...),
    plazo_dias: int = Form(30),
    fecha_inicio: str = Form(...),
    cobrador: str = Form(""),
    observaciones: str = Form(""),
    db: Session = Depends(get_db),
    current_user=Depends(require_login),
    empresa_id: int = Depends(get_current_empresa),
):
    if capital <= 0:
        return JSONResponse({"error": "El capital debe ser mayor a 0"}, status_code=400)
    if num_cuotas <= 0 or num_cuotas > 365:
        return JSONResponse({"error": "Numero de cuotas invalido (1-365)"}, status_code=400)

    cliente = db.query(Cliente).filter(
        Cliente.id == cliente_id, Cliente.empresa_id == empresa_id
    ).first()
    if not cliente:
        return JSONResponse({"detail": "Cliente no encontrado"}, status_code=404)

    try:
        fecha = datetime.date.fromisoformat(fecha_inicio)
        calc = calcular_cuotas(capital, tasa_interes, num_cuotas, fecha, plazo_dias)

        prestamo = Prestamo(
            empresa_id=empresa_id,
            cliente_id=cliente_id, zona_id=zona_id,
            capital=capital, tasa_interes=tasa_interes,
            interes_total=calc["interes_total"], total_pagar=calc["total_pagar"],
            num_cuotas=num_cuotas, valor_cuota=calc["valor_cuota"],
            plazo_dias=plazo_dias, fecha_inicio=fecha, fecha_fin=calc["fecha_fin"],
            cobrador=cobrador or (current_user.nombre_completo if current_user else ""),
            observaciones=observaciones, estado="Activo",
        )
        db.add(prestamo)
        db.flush()

        for c in calc["cuotas"]:
            cuota = Cuota(
                empresa_id=empresa_id,
                prestamo_id=prestamo.id,
                numero=c["numero"], valor=c["valor"],
                fecha_vencimiento=c["fecha_vencimiento"], estado="Pendiente",
            )
            db.add(cuota)

        db.commit()
        return JSONResponse({"ok": True, "id": prestamo.id, "mensaje": "Prestamo registrado exitosamente"})
    except Exception as e:
        db.rollback()
        return JSONResponse({"detail": f"Error: {str(e)}"}, status_code=500)
