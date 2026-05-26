<<<<<<< HEAD
from fastapi import APIRouter, Request, Depends
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy import func
import datetime, json

from app.database import get_db, Cliente, Prestamo, Cuota, Cobro, Zona
from app.routers.auth import get_current_user
from app.utils.zone_permissions import get_allowed_zone_ids
=======
"""Dashboard v2.1 - multi-tenant, fix TemplateResponse"""
from fastapi import APIRouter, Request, Depends
from fastapi.templating import Jinja2Templates
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from sqlalchemy import func
import datetime

from app.database import get_db, Cliente, Prestamo, Cobro, Cuota, Zona
from app.routers.auth import get_current_user
>>>>>>> 7761f488b2aa6200974f069ea5072699c6dbd1e5

router = APIRouter()
templates = Jinja2Templates(directory="templates")


@router.get("/dashboard")
async def dashboard(request: Request, db: Session = Depends(get_db)):
<<<<<<< HEAD
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse("/auth/login", 302)

    eid = user.empresa_id
    allowed_zones = get_allowed_zone_ids(db, user)
    hoy = datetime.date.today()
    inicio_mes = hoy.replace(day=1)

    def zf(q):
        if allowed_zones is not None:
            ids = allowed_zones or [-1]
            if hasattr(q, 'filter'):
                try:
                    return q.filter(Cobro.zona_id.in_(ids))
                except Exception:
                    pass
        return q

    def zfp(q):
        if allowed_zones is not None:
            ids = allowed_zones or [-1]
            return q.filter(Prestamo.zona_id.in_(ids))
        return q

    def zfc(q):
        if allowed_zones is not None:
            ids = allowed_zones or [-1]
            return q.filter(Cliente.zona_id.in_(ids))
        return q

    # Single pass stats
    base_c = db.query(func.count(Cliente.id)).filter(Cliente.empresa_id==eid, Cliente.activo==True)
    base_p = db.query(func.count(Prestamo.id)).filter(Prestamo.empresa_id==eid)
    base_pa = db.query(func.count(Prestamo.id)).filter(Prestamo.empresa_id==eid, Prestamo.estado.in_(["Atrasado","atrasado"]))
    base_v = db.query(func.count(Cuota.id)).join(Prestamo, Cuota.prestamo_id == Prestamo.id).filter(
        Cuota.empresa_id==eid,
        Prestamo.empresa_id==eid,
        Cuota.estado=="Vencida",
    )
    base_hoy = db.query(func.sum(Cobro.valor_cobrado)).filter(Cobro.empresa_id==eid, Cobro.fecha==hoy)
    base_mes = db.query(func.sum(Cobro.valor_cobrado)).filter(Cobro.empresa_id==eid, Cobro.fecha>=inicio_mes)
    base_cap = db.query(func.sum(Prestamo.capital)).filter(Prestamo.empresa_id==eid, Prestamo.estado.in_(["Activo","activo","Atrasado","atrasado"]))

    if allowed_zones is not None:
        ids = allowed_zones or [-1]
        base_c = base_c.filter(Cliente.zona_id.in_(ids))
        base_p = base_p.filter(Prestamo.zona_id.in_(ids))
        base_pa = base_pa.filter(Prestamo.zona_id.in_(ids))
        base_v = base_v.filter(Prestamo.zona_id.in_(ids))
        base_hoy = base_hoy.filter(Cobro.zona_id.in_(ids))
        base_mes = base_mes.filter(Cobro.zona_id.in_(ids))
        base_cap = base_cap.filter(Prestamo.zona_id.in_(ids))

    total_clientes  = base_c.scalar() or 0
    total_prestamos = base_p.filter(Prestamo.estado.in_(["Activo","activo"])).scalar() or 0
    total_atrasados = base_pa.scalar() or 0
    total_vencidas  = base_v.scalar() or 0
    cobrado_hoy     = float(base_hoy.scalar() or 0)
    cobrado_mes     = float(base_mes.scalar() or 0)
    capital_activo  = float(base_cap.scalar() or 0)

    # Cobros recientes
    cobros_q = (db.query(Cobro, Cliente)
        .join(Cliente, Cobro.cliente_id==Cliente.id)
        .filter(Cobro.empresa_id==eid))
    if allowed_zones is not None:
        cobros_q = cobros_q.filter(Cobro.zona_id.in_(allowed_zones or [-1]))
    cobros_rec = cobros_q.order_by(Cobro.hora.desc()).limit(10).all()
    cobros_list = [{
        "cliente": cl.nombre, "valor": float(co.valor_cobrado or 0),
        "fecha": co.fecha.strftime("%d/%m") if co.fecha else "—",
        "metodo": co.metodo_pago or "Efectivo",
    } for co, cl in cobros_rec]

    # Chart 7 dias en una sola consulta
    inicio_chart = hoy - datetime.timedelta(days=6)
    chart_q = db.query(Cobro.fecha, func.sum(Cobro.valor_cobrado)).filter(
        Cobro.empresa_id == eid,
        Cobro.fecha >= inicio_chart,
        Cobro.fecha <= hoy,
    )
    if allowed_zones is not None:
        chart_q = chart_q.filter(Cobro.zona_id.in_(allowed_zones or [-1]))
    chart_map = {fecha: float(valor or 0) for fecha, valor in chart_q.group_by(Cobro.fecha).all()}
    chart_data = [
        {"dia": (hoy - datetime.timedelta(days=i)).strftime("%a")[:2],
         "valor": chart_map.get(hoy - datetime.timedelta(days=i), 0)}
        for i in range(6, -1, -1)
    ]

    # Zonas stats
    zonas = db.query(Zona).filter(Zona.empresa_id==eid, Zona.activa==True).all()
    max_cobro = 1
    zonas_stats = []
    for z in zonas:
        if allowed_zones is not None and z.id not in (allowed_zones or []):
            continue
        cob = float(db.query(func.sum(Cobro.valor_cobrado)).filter(
            Cobro.empresa_id==eid, Cobro.zona_id==z.id, Cobro.fecha>=inicio_mes).scalar() or 0)
        cli = db.query(func.count(Cliente.id)).filter(
            Cliente.empresa_id==eid, Cliente.zona_id==z.id, Cliente.activo==True).scalar() or 0
        pre = db.query(func.count(Prestamo.id)).filter(
            Prestamo.empresa_id==eid, Prestamo.zona_id==z.id,
            Prestamo.estado.in_(["Activo","activo","Atrasado","atrasado"])).scalar() or 0
        zonas_stats.append({"nombre": z.nombre, "cobrado": cob, "clientes": cli, "prestamos": pre})
        if cob > max_cobro: max_cobro = cob
    zonas_stats.sort(key=lambda x: x["cobrado"], reverse=True)

    return templates.TemplateResponse(request, "dashboard.html", {
        "page": "dashboard", "current_user": user,
        "cuotas_vencidas_nav": total_vencidas,
        "stats": {
            "clientes": total_clientes, "prestamos": total_prestamos,
            "atrasados": total_atrasados, "vencidas": total_vencidas,
            "cobrado_hoy": cobrado_hoy, "cobrado_mes": cobrado_mes,
            "capital_activo": capital_activo,
        },
        "cobros_recientes": cobros_list,
        "chart_data": json.dumps(chart_data),
        "zonas_stats": zonas_stats[:8],
        "max_cobro": max_cobro,
    })
=======
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
>>>>>>> 7761f488b2aa6200974f069ea5072699c6dbd1e5
