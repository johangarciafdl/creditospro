from fastapi import APIRouter, Request, Depends
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy import func, case, text
import datetime, json

from app.database import get_db, Cliente, Prestamo, Cuota, Cobro, Zona
from app.routers.auth import get_current_user
from app.utils.zone_permissions import get_allowed_zone_ids

router = APIRouter()
templates = Jinja2Templates(directory="templates")


@router.get("/dashboard")
async def dashboard(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse("/auth/login", 302)

    eid = user.empresa_id
    allowed_zones = get_allowed_zone_ids(db, user)
    hoy = datetime.date.today()
    inicio_mes = hoy.replace(day=1)

    zone_filter = None
    if allowed_zones is not None:
        zone_filter = allowed_zones or [-1]

    def _apply_zone(q, col):
        if zone_filter is not None:
            return q.filter(col.in_(zone_filter))
        return q

    # ── Stats en 2 queries (antes eran 7+) ──
    stats_row = db.query(
        func.count(Cliente.id).filter(Cliente.empresa_id == eid, Cliente.activo == True),
    ).scalar()

    pre_row = db.query(
        func.count(case((Prestamo.estado.in_(["Activo", "activo"]), Prestamo.id))),
        func.count(case((Prestamo.estado.in_(["Atrasado", "atrasado"]), Prestamo.id))),
        func.sum(case((Prestamo.estado.in_(["Activo", "activo", "Atrasado", "atrasado"]), Prestamo.capital))),
    ).filter(Prestamo.empresa_id == eid).first()

    total_clientes = stats_row or 0
    total_prestamos = (pre_row[0] or 0) if pre_row else 0
    total_atrasados = (pre_row[1] or 0) if pre_row else 0
    capital_activo = float((pre_row[2] or 0) if pre_row else 0)

    vencidas_row = db.query(func.count(Cuota.id)).join(
        Prestamo, Cuota.prestamo_id == Prestamo.id
    ).filter(
        Cuota.empresa_id == eid, Prestamo.empresa_id == eid, Cuota.estado == "Vencida",
    )
    if zone_filter is not None:
        vencidas_row = vencidas_row.filter(Prestamo.zona_id.in_(zone_filter))
    total_vencidas = vencidas_row.scalar() or 0

    cobros_row = db.query(
        func.sum(case((Cobro.fecha == hoy, Cobro.valor_cobrado))),
        func.sum(case((Cobro.fecha >= inicio_mes, Cobro.valor_cobrado))),
    ).filter(Cobro.empresa_id == eid).first()
    if zone_filter is not None:
        cobros_row = db.query(
            func.sum(case((Cobro.fecha == hoy, Cobro.valor_cobrado))),
            func.sum(case((Cobro.fecha >= inicio_mes, Cobro.valor_cobrado))),
        ).filter(Cobro.empresa_id == eid, Cobro.zona_id.in_(zone_filter)).first()
    cobrado_hoy = float((cobros_row[0] or 0) if cobros_row else 0)
    cobrado_mes = float((cobros_row[1] or 0) if cobros_row else 0)

    # ── Cobros recientes (1 query) ──
    cobros_q = (db.query(Cobro, Cliente)
        .join(Cliente, Cobro.cliente_id == Cliente.id)
        .filter(Cobro.empresa_id == eid))
    if zone_filter is not None:
        cobros_q = cobros_q.filter(Cobro.zona_id.in_(zone_filter))
    cobros_rec = cobros_q.order_by(Cobro.hora.desc()).limit(10).all()
    cobros_list = [{
        "cliente": cl.nombre, "valor": float(co.valor_cobrado or 0),
        "fecha": co.fecha.strftime("%d/%m") if co.fecha else "--",
        "metodo": co.metodo_pago or "Efectivo",
    } for co, cl in cobros_rec]

    # ── Chart 7 dias (1 query) ──
    inicio_chart = hoy - datetime.timedelta(days=6)
    chart_q = db.query(Cobro.fecha, func.sum(Cobro.valor_cobrado)).filter(
        Cobro.empresa_id == eid, Cobro.fecha >= inicio_chart, Cobro.fecha <= hoy,
    )
    if zone_filter is not None:
        chart_q = chart_q.filter(Cobro.zona_id.in_(zone_filter))
    chart_map = {f: float(v or 0) for f, v in chart_q.group_by(Cobro.fecha).all()}
    chart_data = [
        {"dia": (hoy - datetime.timedelta(days=i)).strftime("%a")[:2],
         "valor": chart_map.get(hoy - datetime.timedelta(days=i), 0),
         "fecha": (hoy - datetime.timedelta(days=i)).strftime("%d/%m")}
        for i in range(6, -1, -1)
    ]

    # ── Zonas stats (1 query con GROUP BY, no N+1) ──
    zonas_base = db.query(Zona).filter(Zona.empresa_id == eid, Zona.activa == True).all()

    zonas_stats = []
    if zonas_base:
        zona_ids = [z.id for z in zonas_base]
        if zone_filter is not None:
            zona_ids = [z for z in zona_ids if z in zone_filter]

        if zona_ids:
            zonas_cobro = db.query(
                Cobro.zona_id,
                func.sum(Cobro.valor_cobrado).label("cobrado"),
            ).filter(
                Cobro.empresa_id == eid, Cobro.zona_id.in_(zona_ids), Cobro.fecha >= inicio_mes
            ).group_by(Cobro.zona_id).all()
            cobro_map = {r.zona_id: float(r.cobrado or 0) for r in zonas_cobro}

            zonas_cli = db.query(
                Cliente.zona_id, func.count(Cliente.id).label("clientes")
            ).filter(
                Cliente.empresa_id == eid, Cliente.zona_id.in_(zona_ids), Cliente.activo == True
            ).group_by(Cliente.zona_id).all()
            cli_map = {r.zona_id: r.clientes for r in zonas_cli}

            zonas_pre = db.query(
                Prestamo.zona_id, func.count(Prestamo.id).label("prestamos")
            ).filter(
                Prestamo.empresa_id == eid, Prestamo.zona_id.in_(zona_ids),
                Prestamo.estado.in_(["Activo", "activo", "Atrasado", "atrasado"])
            ).group_by(Prestamo.zona_id).all()
            pre_map = {r.zona_id: r.prestamos for r in zonas_pre}

            max_cobro = 1
            for z in zonas_base:
                if z.id not in zona_ids:
                    continue
                cob = cobro_map.get(z.id, 0)
                cli = cli_map.get(z.id, 0)
                pre = pre_map.get(z.id, 0)
                zonas_stats.append({"nombre": z.nombre, "cobrado": cob, "clientes": cli, "prestamos": pre})
                if cob > max_cobro:
                    max_cobro = cob
            zonas_stats.sort(key=lambda x: x["cobrado"], reverse=True)
        else:
            max_cobro = 1
    else:
        max_cobro = 1

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
