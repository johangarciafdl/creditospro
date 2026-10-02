"""La mora de la cartera: cuanta plata esta en riesgo y hacia donde va.

Usa el mismo semaforo que ve el cobrador en su ruta (app/routers/ruta.py):
una cuota esta atrasada si ya vencio y le falta algo por pagar; un cliente con
1 a 3 cuotas atrasadas es amarillo y con 4 o mas, rojo. Si el panel del
administrador y la ruta contaran distinto, cada uno defenderia su numero.

Ademas de la foto de hoy, el estado de hace una semana: asi se ve quien PASO a
rojo esta semana (y hay que ir a buscarlo antes de que se pierda) y quien
salio. Lo pagado hasta una fecha se reconstruye restando del pagado actual los
cobros hechos desde esa fecha: no hace falta guardar historicos.
"""
from __future__ import annotations

import datetime
from decimal import Decimal

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import Cliente, Cobro, Cuota, Prestamo, Usuario, Zona
from app.utils.money import money

ESTADOS_PENDIENTES = ("Pendiente", "Vencida", "Parcial")
ROJO_DESDE = 4
CERO = Decimal("0")


def _color(atrasadas: int) -> str:
    if atrasadas >= ROJO_DESDE:
        return "rojo"
    return "amarillo" if atrasadas >= 1 else "verde"


def panel(db: Session, empresa_id: int, hoy: datetime.date, semanas: int = 8) -> dict:
    hace7 = hoy - datetime.timedelta(days=7)

    # Cuotas que hoy deben algo, mas las que se terminaron de pagar en la
    # ultima semana (hace 7 dias aun debian: cuentan para "como estaba").
    pagadas_recien = {cid for (cid,) in db.query(Cobro.cuota_id).filter(
        Cobro.empresa_id == empresa_id, Cobro.fecha >= hace7).distinct()}
    q = (db.query(Cuota.id, Cuota.valor, Cuota.valor_pagado, Cuota.fecha_vencimiento,
                  Cuota.estado, Prestamo.id, Prestamo.cliente_id, Prestamo.zona_id)
         .join(Prestamo, Cuota.prestamo_id == Prestamo.id)
         .filter(Cuota.empresa_id == empresa_id))
    filas = [r for r in q.filter(Cuota.estado.in_(ESTADOS_PENDIENTES)).all()]
    if pagadas_recien:
        filas += q.filter(Cuota.id.in_(pagadas_recien),
                          Cuota.estado.notin_(ESTADOS_PENDIENTES)).all()

    # Cobros desde hace7, por cuota: lo que se pago "despues" de esa fecha.
    desde_hace7 = {cid: money(v or 0) for cid, v in db.query(
        Cobro.cuota_id, func.sum(Cobro.valor_cobrado))
        .filter(Cobro.empresa_id == empresa_id, Cobro.fecha >= hace7)
        .group_by(Cobro.cuota_id)}

    atr_hoy: dict[int, int] = {}
    atr_antes: dict[int, int] = {}
    saldo_cliente: dict[int, Decimal] = {}
    zona_cliente: dict[int, int] = {}
    for (cid, valor, pagado, vence, estado, pid, cliente, zona) in filas:
        valor = money(valor or 0)
        pagado = money(pagado or 0)
        zona_cliente.setdefault(cliente, zona)
        falta = valor - pagado
        if estado in ESTADOS_PENDIENTES and falta > 0:
            saldo_cliente[cliente] = saldo_cliente.get(cliente, CERO) + falta
            if vence and vence < hoy:
                atr_hoy[cliente] = atr_hoy.get(cliente, 0) + 1
        falta_antes = valor - (pagado - desde_hace7.get(cid, CERO))
        if vence and vence < hace7 and falta_antes > 0:
            atr_antes[cliente] = atr_antes.get(cliente, 0) + 1

    zonas = {z.id: z.nombre for z in db.query(Zona.id, Zona.nombre)
             .filter(Zona.empresa_id == empresa_id)}
    nombres = {c.id: c.nombre for c in db.query(Cliente.id, Cliente.nombre)
               .filter(Cliente.empresa_id == empresa_id, Cliente.id.in_((set(saldo_cliente) | set(atr_antes)) or {-1}))}

    por_zona: dict[int, dict] = {}
    tot = {"clientes": 0, "verde": 0, "amarillo": 0, "rojo": 0,
           "cartera": CERO, "en_riesgo": CERO}
    pasaron, salieron = [], []
    for cliente in set(saldo_cliente) | set(atr_antes):
        saldo = saldo_cliente.get(cliente, CERO)
        color = _color(atr_hoy.get(cliente, 0))
        antes = _color(atr_antes.get(cliente, 0))
        z = zona_cliente.get(cliente)
        if saldo <= 0:
            # Ya no debe nada: no esta en la cartera, pero si estaba en rojo
            # hace una semana, salio (pagando todo).
            if antes == "rojo":
                salieron.append({"cliente_id": cliente, "nombre": nombres.get(cliente, "—"),
                                 "zona": zonas.get(z, ""), "ahora": "pagó todo"})
            continue
        fz = por_zona.setdefault(z, {"zona_id": z, "zona": zonas.get(z, "Sin zona"),
                                     "clientes": 0, "verde": 0, "amarillo": 0, "rojo": 0,
                                     "cartera": CERO, "en_riesgo": CERO})
        for f in (fz, tot):
            f["clientes"] += 1
            f[color] += 1
            f["cartera"] += saldo
            if color != "verde":
                f["en_riesgo"] += saldo
        if color == "rojo" and antes != "rojo":
            pasaron.append({"cliente_id": cliente, "nombre": nombres.get(cliente, "—"),
                            "zona": zonas.get(z, ""), "atrasadas": atr_hoy.get(cliente, 0),
                            "saldo": saldo})
        elif antes == "rojo" and color != "rojo":
            salieron.append({"cliente_id": cliente, "nombre": nombres.get(cliente, "—"),
                             "zona": zonas.get(z, ""), "ahora": color})

    # Por cobrador: las zonas que tiene asignadas.
    cobradores = []
    for u in (db.query(Usuario).filter(Usuario.empresa_id == empresa_id, Usuario.activo == True,
                                       Usuario.rol.notin_(("admin", "superadmin")))
              .order_by(Usuario.nombre)):
        ids = {z.id for z in getattr(u, "zonas_asignadas", [])} | ({u.zona_id} if u.zona_id else set())
        f = {"usuario_id": u.id, "nombre": u.nombre or u.username,
             "zonas": ", ".join(sorted(zonas.get(i, "") for i in ids if i in zonas)),
             "clientes": 0, "amarillo": 0, "rojo": 0, "cartera": CERO, "en_riesgo": CERO}
        for i in ids:
            if i in por_zona:
                for k in ("clientes", "amarillo", "rojo", "cartera", "en_riesgo"):
                    f[k] += por_zona[i][k]
        cobradores.append(f)

    # Tendencia: semana a semana, lo que se cobro contra lo que vencia.
    lunes = hoy - datetime.timedelta(days=hoy.weekday())
    inicio = lunes - datetime.timedelta(weeks=semanas - 1)
    vencia: dict[datetime.date, Decimal] = {}
    for vence, valor in (db.query(Cuota.fecha_vencimiento, func.sum(Cuota.valor))
                         .filter(Cuota.empresa_id == empresa_id,
                                 Cuota.fecha_vencimiento >= inicio, Cuota.fecha_vencimiento <= hoy)
                         .group_by(Cuota.fecha_vencimiento)):
        sem = vence - datetime.timedelta(days=vence.weekday())
        vencia[sem] = vencia.get(sem, CERO) + money(valor or 0)
    cobrado: dict[datetime.date, Decimal] = {}
    for fecha, valor in (db.query(Cobro.fecha, func.sum(Cobro.valor_cobrado))
                         .filter(Cobro.empresa_id == empresa_id,
                                 Cobro.fecha >= inicio, Cobro.fecha <= hoy)
                         .group_by(Cobro.fecha)):
        sem = fecha - datetime.timedelta(days=fecha.weekday())
        cobrado[sem] = cobrado.get(sem, CERO) + money(valor or 0)
    tendencia = []
    for i in range(semanas):
        sem = inicio + datetime.timedelta(weeks=i)
        v, c = vencia.get(sem, CERO), cobrado.get(sem, CERO)
        tendencia.append({"semana": sem, "vencia": v, "cobrado": c,
                          "cumplimiento": float(c / v) if v > 0 else None})

    zonas_lista = sorted(por_zona.values(), key=lambda f: -f["en_riesgo"])
    pasaron.sort(key=lambda f: -f["saldo"])
    return {"totales": tot, "zonas": zonas_lista, "cobradores": cobradores,
            "pasaron_a_rojo": pasaron, "salieron_de_rojo": salieron,
            "tendencia": tendencia}


# ── CONTROL DE VISITAS ────────────────────────────────────────────────────
def control_de_visitas(db: Session, empresa_id: int, desde: datetime.date,
                       hasta: datetime.date) -> list[dict]:
    """De los cobros de cada cobrador: cuantos se registraron en la puerta del
    cliente, cuantos desde un mismo sitio y cuantos sin GPS.

    "Mismo sitio" es la misma regla que usa la ruta para no inventar
    posiciones (app/utils/ubicacion.py): un punto donde se registraron cobros
    de 4 o mas clientes distintos no es la casa de ninguno, es donde el
    cobrador los anota. Puede ser legitimo (clientes que pagan en un local),
    asi que no se bloquea nada: solo se muestra.
    """
    from app.utils.ubicacion import _celda, _celdas_compartidas, leer_coordenadas

    nombres = {u.id: (u.nombre or u.username) for u in db.query(Usuario).filter(
        Usuario.empresa_id == empresa_id, Usuario.rol.notin_(("admin", "superadmin")))}
    por_cobrador: dict[int, list] = {}
    for uid, cliente, lat, lng in (
        db.query(Cobro.usuario_id, Cobro.cliente_id, Cobro.lat_cobro, Cobro.lng_cobro)
        .filter(Cobro.empresa_id == empresa_id, Cobro.fecha >= desde, Cobro.fecha <= hasta,
                Cobro.metodo_pago != "Renovacion")
    ):
        if uid in nombres:
            por_cobrador.setdefault(uid, []).append((cliente, lat, lng))

    salida = []
    for uid, cobros in por_cobrador.items():
        con_gps = []
        sin_gps = 0
        for cliente, lat, lng in cobros:
            la, lo = leer_coordenadas(lat, lng)
            if la is None:
                sin_gps += 1
            else:
                con_gps.append((cliente, la, lo))
        compartidas = _celdas_compartidas(con_gps)
        mismo = sum(1 for _, la, lo in con_gps if _celda(la, lo) in compartidas)
        total = len(cobros)
        salida.append({"usuario_id": uid, "nombre": nombres[uid], "total": total,
                       "en_puerta": len(con_gps) - mismo, "mismo_sitio": mismo,
                       "sin_gps": sin_gps})
    salida.sort(key=lambda f: -(f["mismo_sitio"] + f["sin_gps"]) / max(1, f["total"]))
    return salida
