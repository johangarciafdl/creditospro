from fastapi import APIRouter, Request, Depends
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy import func
import datetime

from app.database import get_db, Cliente, Prestamo, Cobro, Cuota, Zona
from app.auth import require_login

router = APIRouter()
templates = Jinja2Templates(directory="templates")


@router.get("/dashboard")
async def dashboard(request: Request, db: Session = Depends(get_db), current_user=Depends(require_login)):
    hoy = datetime.date.today()

    total_prestamos = db.query(func.sum(Prestamo.capital)).scalar() or 0
    total_intereses = db.query(func.sum(Prestamo.interes_total)).scalar() or 0
    cuotas_vencidas = db.query(Cuota).filter(Cuota.estado == "Vencida").count()
    clientes_activos = db.query(Cliente).filter(Cliente.activo == True).count()
    cobros_hoy = db.query(func.sum(Cobro.valor_cobrado)).filter(Cobro.fecha == hoy).scalar() or 0
    prestamos_activos = db.query(Prestamo).filter(Prestamo.estado == "Activo").count()

    zonas = db.query(Zona).all()
    resumen_zonas = []
    for z in zonas:
        cobrado_zona = db.query(func.sum(Cobro.valor_cobrado)).filter(
            Cobro.zona_id == z.id, Cobro.fecha == hoy
        ).scalar() or 0
        resumen_zonas.append({
            "nombre": z.nombre, "cobrador": z.cobrador_nombre or "—",
            "cobrado": cobrado_zona, "activa": z.activa,
        })

    atrasados = (db.query(Prestamo, Cliente).join(Cliente)
        .filter(Prestamo.estado.in_(["Atrasado", "Mora", "Activo"])).limit(10).all())

    atrasados_list = []
    for p, c in atrasados:
        pagado = sum(cu.valor_pagado or 0 for cu in p.cuotas)
        saldo = max(0, p.total_pagar - pagado)
        cuota_actual = next(
            (cu for cu in sorted(p.cuotas, key=lambda x: x.numero) if cu.estado in ["Pendiente", "Vencida"]), None)
        zona = db.query(Zona).filter(Zona.id == p.zona_id).first()
        atrasados_list.append({
            "cliente": c.nombre, "cedula": c.cedula,
            "capital": p.capital, "interes": p.interes_total,
            "cuota_valor": p.valor_cuota,
            "zona": zona.nombre if zona else "—",
            "cuota_num": cuota_actual.numero if cuota_actual else "—",
            "total_cuotas": p.num_cuotas,
            "estado": cuota_actual.estado if cuota_actual else "OK",
            "saldo": saldo, "tipo_cliente": c.tipo_cliente,
        })

    return templates.TemplateResponse("dashboard.html", {
        "request": request, "page": "dashboard",
        "total_prestamos": total_prestamos,
        "total_intereses": total_intereses,
        "cuotas_vencidas": cuotas_vencidas,
        "clientes_activos": clientes_activos,
        "cobros_hoy": cobros_hoy,
        "prestamos_activos": prestamos_activos,
        "resumen_zonas": resumen_zonas,
        "atrasados": atrasados_list,
        "fecha_hoy": hoy.strftime("%d/%m/%Y"),
        "current_user": current_user,
        "cuotas_vencidas_nav": cuotas_vencidas,
    })


@router.get("/api/stats")
async def get_stats(db: Session = Depends(get_db), current_user=Depends(require_login)):
    hoy = datetime.date.today()
    return {
        "capital_total": db.query(func.sum(Prestamo.capital)).scalar() or 0,
        "intereses_total": db.query(func.sum(Prestamo.interes_total)).scalar() or 0,
        "cuotas_vencidas": db.query(Cuota).filter(Cuota.estado == "Vencida").count(),
        "clientes_activos": db.query(Cliente).filter(Cliente.activo == True).count(),
        "cobros_hoy": db.query(func.sum(Cobro.valor_cobrado)).filter(Cobro.fecha == hoy).scalar() or 0,
        "prestamos_activos": db.query(Prestamo).filter(Prestamo.estado == "Activo").count(),
    }
