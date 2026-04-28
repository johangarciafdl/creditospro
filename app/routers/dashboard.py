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

    zonas = db.query(Zona).filter(Zona.empresa_id == current_user.empresa_id).all()
    zonas_dict = {z.id: z for z in zonas}

    # Cobros de hoy por zona en un solo query
    cobros_por_zona = dict(
        db.query(Cobro.zona_id, func.sum(Cobro.valor_cobrado))
        .filter(Cobro.fecha == hoy, Cobro.empresa_id == current_user.empresa_id)
        .group_by(Cobro.zona_id).all()
    )
    resumen_zonas = [{
        "nombre": z.nombre, "cobrador": z.cobrador_nombre or "—",
        "cobrado": cobros_por_zona.get(z.id, 0), "activa": z.activa,
    } for z in zonas]

    # Últimos préstamos activos (sin cargar cuotas)
    atrasados = (db.query(Prestamo, Cliente).join(Cliente)
        .filter(Prestamo.empresa_id == current_user.empresa_id,
                Prestamo.estado.in_(["atrasado", "activo", "Atrasado", "Activo", "Mora"]))
        .limit(10).all())

    atrasados_list = []
    for p, c in atrasados:
        zona_obj = zonas_dict.get(p.zona_id)
        atrasados_list.append({
            "cliente": c.nombre, "cedula": c.cedula,
            "capital": p.capital, "interes": p.interes_total or 0,
            "cuota_valor": p.valor_cuota or 0,
            "zona": zona_obj.nombre if zona_obj else "—",
            "cuota_num": "—", "total_cuotas": p.num_cuotas,
            "estado": p.estado, "saldo": p.total_pagar or p.capital,
            "tipo_cliente": c.tipo_cliente,
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