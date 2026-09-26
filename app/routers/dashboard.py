from fastapi import APIRouter, Request, Depends
from fastapi.responses import RedirectResponse
from app.templates import templates
from sqlalchemy.orm import Session
from sqlalchemy import func, literal_column, select, text
import datetime, json

from app.database import (
    get_db, Cliente, NotificacionWP, Prestamo, Cuota, Cobro, Usuario, Zona,
    hoy_local,
)
from app.routers.auth import get_current_user
from app.utils.estado_sistema import VERSION
from app.utils.interfaz import redirigir_a_vista_simple
from app.utils.permisos_rol import es_admin
from app.utils.zone_permissions import get_allowed_zone_ids

router = APIRouter()


@router.get("/dashboard")
async def dashboard(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse("/auth/login", 302)

    # Si la empresa trabaja con la interfaz simple, el cobrador no tiene
    # dashboard: su pantalla es la ruta del dia. Al admin no le afecta.
    simple = redirigir_a_vista_simple(db, user)
    if simple:
        return simple

    eid = user.empresa_id
    allowed_zones = get_allowed_zone_ids(db, user)
    hoy = hoy_local()
    inicio_mes = hoy.replace(day=1)

    zone_filter = None
    if allowed_zones is not None:
        zone_filter = allowed_zones or [-1]

    def _apply_zone(q, col):
        if zone_filter is not None:
            return q.filter(col.in_(zone_filter))
        return q

    # ── Todas las cifras de cabecera en UNA sola consulta ───────────────────
    # Eran cuatro consultas independientes. Cada una es rapidisima dentro de
    # Postgres (decimas de milisegundo) pero cada una paga el viaje de ida y
    # vuelta hasta la base de datos, que es lo que domina el tiempo de la
    # pantalla. Como subconsultas escalares van todas en el mismo viaje.
    q_clientes = (
        select(func.count(Cliente.id))
        .where(Cliente.empresa_id == eid, Cliente.activo.is_(True))
    )
    q_prestamos_activos = (
        select(func.count(Prestamo.id))
        .where(Prestamo.empresa_id == eid, Prestamo.estado.in_(["Activo", "activo"]))
    )
    q_prestamos_atrasados = (
        select(func.count(Prestamo.id))
        .where(Prestamo.empresa_id == eid, Prestamo.estado.in_(["Atrasado", "atrasado"]))
    )
    q_capital = (
        select(func.coalesce(func.sum(Prestamo.capital), 0))
        .where(
            Prestamo.empresa_id == eid,
            Prestamo.estado.in_(["Activo", "activo", "Atrasado", "atrasado"]),
        )
    )
    q_vencidas = (
        select(func.count(Cuota.id))
        .select_from(Cuota)
        .join(Prestamo, Cuota.prestamo_id == Prestamo.id)
        .where(Cuota.empresa_id == eid, Prestamo.empresa_id == eid, Cuota.estado == "Vencida")
    )
    q_cobrado_hoy = (
        select(func.coalesce(func.sum(Cobro.valor_cobrado), 0))
        .where(Cobro.empresa_id == eid, Cobro.fecha == hoy)
    )
    q_cobrado_mes = (
        select(func.coalesce(func.sum(Cobro.valor_cobrado), 0))
        .where(Cobro.empresa_id == eid, Cobro.fecha >= inicio_mes)
    )
    if zone_filter is not None:
        q_vencidas = q_vencidas.where(Prestamo.zona_id.in_(zone_filter))
        q_cobrado_hoy = q_cobrado_hoy.where(Cobro.zona_id.in_(zone_filter))
        q_cobrado_mes = q_cobrado_mes.where(Cobro.zona_id.in_(zone_filter))

    fila = db.execute(
        select(
            q_clientes.scalar_subquery(),
            q_prestamos_activos.scalar_subquery(),
            q_prestamos_atrasados.scalar_subquery(),
            q_capital.scalar_subquery(),
            q_vencidas.scalar_subquery(),
            q_cobrado_hoy.scalar_subquery(),
            q_cobrado_mes.scalar_subquery(),
        )
    ).first()

    total_clientes = fila[0] or 0
    total_prestamos = fila[1] or 0
    total_atrasados = fila[2] or 0
    capital_activo = float(fila[3] or 0)
    total_vencidas = fila[4] or 0
    cobrado_hoy = float(fila[5] or 0)
    cobrado_mes = float(fila[6] or 0)

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
            # Las tres cifras por zona (cobrado, clientes, prestamos) salian de
            # tres consultas con GROUP BY: tres viajes a la base de datos para
            # rellenar la misma tabla. Un UNION ALL las trae en un solo viaje y
            # el reparto se hace aqui, que no cuesta nada.
            u_cobro = (
                select(literal_column("'cobro'").label("clase"),
                       Cobro.zona_id.label("zona_id"),
                       func.coalesce(func.sum(Cobro.valor_cobrado), 0).label("valor"))
                .where(Cobro.empresa_id == eid, Cobro.zona_id.in_(zona_ids),
                       Cobro.fecha >= inicio_mes)
                .group_by(Cobro.zona_id)
            )
            u_cli = (
                select(literal_column("'cliente'"), Cliente.zona_id,
                       func.count(Cliente.id))
                .where(Cliente.empresa_id == eid, Cliente.zona_id.in_(zona_ids),
                       Cliente.activo.is_(True))
                .group_by(Cliente.zona_id)
            )
            u_pre = (
                select(literal_column("'prestamo'"), Prestamo.zona_id,
                       func.count(Prestamo.id))
                .where(Prestamo.empresa_id == eid, Prestamo.zona_id.in_(zona_ids),
                       Prestamo.estado.in_(["Activo", "activo", "Atrasado", "atrasado"]))
                .group_by(Prestamo.zona_id)
            )
            cobro_map, cli_map, pre_map = {}, {}, {}
            for clase, zona_id, valor in db.execute(u_cobro.union_all(u_cli, u_pre)).all():
                if clase == "cobro":
                    cobro_map[zona_id] = float(valor or 0)
                elif clase == "cliente":
                    cli_map[zona_id] = int(valor or 0)
                else:
                    pre_map[zona_id] = int(valor or 0)

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

    # El capital en cartera -- lo que la empresa tiene prestado y aun no ha
    # recuperado -- es una cifra de negocio, no una herramienta de trabajo. El
    # cobrador necesita saber a quien le cobra hoy y cuanto le debe ESE
    # cliente; el total de lo que falta por cobrar no le hace falta para
    # trabajar y si es algo que puede acabar fuera. No se le oculta en la
    # plantilla: no se le manda.
    ve_la_cartera = es_admin(user)

    return templates.TemplateResponse(request, "dashboard.html", {
        "page": "dashboard", "current_user": user,
        "cuotas_vencidas_nav": total_vencidas,
        "ve_la_cartera": ve_la_cartera,
        "stats": {
            "clientes": total_clientes, "prestamos": total_prestamos,
            "atrasados": total_atrasados, "vencidas": total_vencidas,
            "cobrado_hoy": cobrado_hoy, "cobrado_mes": cobrado_mes,
            "capital_activo": capital_activo if ve_la_cartera else None,
        },
        "cobros_recientes": cobros_list,
        "chart_data": json.dumps(chart_data),
        "zonas_stats": zonas_stats[:8],
        "max_cobro": max_cobro,
    })


def _como_fecha(valor):
    """Cobro.fecha es un Date, pero segun el motor puede llegar como
    datetime. Normalizar evita el AttributeError de llamar .date() sobre un
    date, que es lo que tumbaba esta pantalla con un 500."""
    if valor is None:
        return None
    return valor.date() if hasattr(valor, "date") else valor


@router.get("/estado")
async def estado_operacion(request: Request, db: Session = Depends(get_db)):
    """Estado de la operacion de la empresa, para su administrador.

    Es el equivalente "de negocio" del panel tecnico del superadmin:
    responde si el sistema esta funcionando PARA ELLOS. Hasta ahora, si un
    cobrador dejaba de registrar cobros o los recordatorios de WhatsApp
    fallaban, no habia ninguna pantalla donde se notara -- habia que
    descubrirlo por la queja de un cliente.
    """
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse("/auth/login", 302)
    if user.rol not in ("admin", "superadmin"):
        return RedirectResponse("/dashboard", 302)

    hoy = hoy_local()
    hace_7d = hoy - datetime.timedelta(days=7)

    # Cobradores y cuando registraron su ultimo cobro. Un cobrador activo
    # que lleva dias sin registrar nada es la señal mas temprana de que algo
    # va mal (aplicacion rota, celular sin sincronizar, o alguien que dejo
    # de trabajar sin avisar).
    cobradores = []
    ultimo_por_usuario = dict(
        db.query(Cobro.usuario_id, func.max(Cobro.fecha))
        .filter(Cobro.empresa_id == user.empresa_id)
        .group_by(Cobro.usuario_id).all()
    )
    hoy_por_usuario = dict(
        db.query(Cobro.usuario_id, func.count(Cobro.id))
        .filter(Cobro.empresa_id == user.empresa_id, func.date(Cobro.fecha) == hoy)
        .group_by(Cobro.usuario_id).all()
    )
    for u in (
        db.query(Usuario)
        .filter(
            Usuario.empresa_id == user.empresa_id,
            Usuario.activo.is_(True),
            Usuario.rol.in_(("cobrador", "supervisor", "admin")),
        )
        .order_by(Usuario.nombre)
        .all()
    ):
        ultimo = _como_fecha(ultimo_por_usuario.get(u.id))
        cobradores.append({
            "nombre": u.nombre or u.username,
            "rol": u.rol,
            "cobros_hoy": hoy_por_usuario.get(u.id, 0),
            "ultimo": ultimo.strftime("%d/%m/%Y") if ultimo else "nunca",
            "dias_sin_registrar": (hoy - ultimo).days if ultimo else None,
        })

    # Recordatorios de WhatsApp: lo que se envio y lo que fallo.
    wp = {"enviados": 0, "fallidos": 0, "pendientes": 0}
    for estado, n in (
        db.query(NotificacionWP.estado, func.count(NotificacionWP.id))
        .filter(
            NotificacionWP.empresa_id == user.empresa_id,
            NotificacionWP.creado >= datetime.datetime.combine(hace_7d, datetime.time.min),
        )
        .group_by(NotificacionWP.estado).all()
    ):
        clave = (estado or "").lower()
        if clave.startswith("enviad"):
            wp["enviados"] += n
        elif clave.startswith("pendien"):
            wp["pendientes"] += n
        else:
            wp["fallidos"] += n

    # Cartera en riesgo: cuotas vencidas sin cubrir.
    vencidas = (
        db.query(func.count(Cuota.id), func.coalesce(func.sum(Cuota.valor - Cuota.valor_pagado), 0))
        .join(Prestamo, Cuota.prestamo_id == Prestamo.id)
        .filter(
            Cuota.empresa_id == user.empresa_id,
            Cuota.estado.in_(("Pendiente", "Vencida", "Parcial")),
            Cuota.fecha_vencimiento < hoy,
        )
        .first()
    )

    return templates.TemplateResponse(request, "estado_operacion.html", {
        "page": "estado",
        "current_user": user,
        "cobradores": cobradores,
        "whatsapp": wp,
        "vencidas_num": int(vencidas[0] or 0),
        "vencidas_monto": float(vencidas[1] or 0),
        "version": VERSION,
        "cobros_hoy": sum(hoy_por_usuario.values()),
    })
