"""Dashboard v2.1 - multi-tenant, fix TemplateResponse"""
from fastapi import APIRouter, Request, Depends
from fastapi.templating import Jinja2Templates
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from sqlalchemy import func
import datetime

from app.database import get_db, Cliente, Prestamo, Cobro, Cuota, Zona
from app.routers.auth import get_current_user

router = APIRouter()
templates = Jinja2Templates(directory="templates")


@router.get("/dashboard")
async def dashboard(request: Request, db: Session = Depends(get_db)):
    current_user = get_current_user(request, db)
    if not current_user:
        return RedirectResponse(url="/auth/login", status_code=302)

    eid = current_user.empresa_id
    hoy = datetime.date.today()

    total_prestamos = db.query(func.sum(Prestamo.capital)).filter(Prestamo.empresa_id == eid).scalar() or 0
    total_intereses = db.query(func.sum(Prestamo.interes_total)).filter(Prestamo.empresa_id == eid).scalar() or 0
    cuotas_vencidas = db.query(Cuota).filter(Cuota.empresa_id == eid, Cuota.estado == "Vencida").count()
    clientes_activos = db.query(Cliente).filter(Cliente.empresa_id == eid, Cliente.activo == True).count()
    cobros_hoy = db.query(func.sum(Cobro.valor_cobrado)).filter(Cobro.empresa_id == eid, Cobro.fecha == hoy).scalar() or 0
    prestamos_activos = db.query(Prestamo).filter(Prestamo.empresa_id == eid, Prestamo.estado == "Activo").count()

    zonas = db.query(Zona).filter(Zona.empresa_id == eid).all()
    resumen_zonas = []
    for z in zonas:
        cobrado = db.query(func.sum(Cobro.valor_cobrado)).filter(
            Cobro.empresa_id == eid, Cobro.zona_id == z.id, Cobro.fecha == hoy
        ).scalar() or 0
        resumen_zonas.append({
            "nombre": z.nombre, "cobrador": z.cobrador_nombre or "—",
            "cobrado": cobrado, "activa": z.activa,
        })

    atrasados = (
        db.query(Prestamo, Cliente).join(Cliente)
        .filter(Prestamo.empresa_id == eid, Prestamo.estado.in_(("Atrasado", "Mora", "Activo")))
        .limit(10).all()
    )
    atrasados_list = []
    for p, c in atrasados:
        pagado = sum(cu.valor_pagado for cu in p.cuotas)
        saldo = max(0.0, (p.total_pagar or 0) - pagado)
        cuota_actual = next(
            (cu for cu in sorted(p.cuotas, key=lambda x: x.numero)
             if cu.estado in ("Pendiente", "Vencida")), None
        )
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

    return templates.TemplateResponse(request, "dashboard.html", {
        "page": "dashboard", "current_user": current_user,
        "cuotas_vencidas_nav": cuotas_vencidas,
        "total_prestamos": total_prestamos,
        "total_intereses": total_intereses,
        "cuotas_vencidas": cuotas_vencidas,
        "clientes_activos": clientes_activos,
        "cobros_hoy": cobros_hoy,
        "prestamos_activos": prestamos_activos,
        "resumen_zonas": resumen_zonas,
        "atrasados": atrasados_list,
        "fecha_hoy": hoy.strftime("%d/%m/%Y"),
    })


@router.get("/api/stats")
async def get_stats(request: Request, db: Session = Depends(get_db)):
    current_user = get_current_user(request, db)
    if not current_user:
        from fastapi import HTTPException
        raise HTTPException(status_code=401)
    eid = current_user.empresa_id
    hoy = datetime.date.today()
    return {
        "capital_total": db.query(func.sum(Prestamo.capital)).filter(Prestamo.empresa_id == eid).scalar() or 0,
        "cuotas_vencidas": db.query(Cuota).filter(Cuota.empresa_id == eid, Cuota.estado == "Vencida").count(),
        "clientes_activos": db.query(Cliente).filter(Cliente.empresa_id == eid, Cliente.activo == True).count(),
        "cobros_hoy": db.query(func.sum(Cobro.valor_cobrado)).filter(Cobro.empresa_id == eid, Cobro.fecha == hoy).scalar() or 0,
        "prestamos_activos": db.query(Prestamo).filter(Prestamo.empresa_id == eid, Prestamo.estado == "Activo").count(),
    }
