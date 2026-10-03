"""El tablero de UNA zona, para el dashboard del administrador.

Cada zona se mira por separado y nunca se mezclan: como en el programa que
CreditosPro reemplaza, arriba de cada ruta van su capital y sus intereses por
cobrar, y debajo lo que esta pasando hoy.

- Capital e intereses por cobrar: de lo que los clientes de la zona todavia
  deben, cuanto es capital y cuanto interes. Cada prestamo se parte en la
  misma proporcion que su total (uno de 500.000 al 20 % = 600.000: cada peso
  que falta es 5/6 capital y 1/6 interes).
- Hoy: cobrado, prestado y quienes no pagaron.
- Movimiento del dia: tarjetas canceladas (terminaron de pagar), prestamos
  nuevos, renovaciones y clientes nuevos.
- Cartera: clientes con saldo, amarillos (1 a 3 cuotas atrasadas), rojos (4
  o mas) y la plata en riesgo -- el mismo semaforo de la ruta.
- Ultimos cobros del dia.

Todo con pocas consultas: la pantalla se refresca sola cada pocos segundos.
"""
from __future__ import annotations

import datetime
from decimal import Decimal

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import (Cliente, Cobro, Cuota, NoPago, Prestamo, Usuario,
                          a_hora_local, inicio_dia_negocio)
from app.utils.money import money

ESTADOS_PENDIENTES = ("Pendiente", "Vencida", "Parcial")
ESTADOS_FUERA = ("Anulado", "anulado")
ROJO_DESDE = 4
CERO = Decimal("0")
PREFIJO_RENOVACION = "Renovacion del prestamo"


def tablero_zona(db: Session, empresa_id: int, zona_id: int, hoy: datetime.date) -> dict:
    # ── Cartera: lo que falta por cobrar, partido en capital e interes ────
    filas = (
        db.query(Prestamo.id, Prestamo.cliente_id, Prestamo.capital, Prestamo.total_pagar,
                 Cuota.valor, Cuota.valor_pagado, Cuota.fecha_vencimiento)
        .join(Cuota, Cuota.prestamo_id == Prestamo.id)
        .filter(Prestamo.empresa_id == empresa_id, Prestamo.zona_id == zona_id,
                Prestamo.estado.notin_(ESTADOS_FUERA),
                Cuota.estado.in_(ESTADOS_PENDIENTES))
        .all()
    )
    saldo_prestamo: dict[int, Decimal] = {}
    datos_prestamo: dict[int, tuple] = {}
    atrasadas: dict[int, int] = {}
    saldo_cliente: dict[int, Decimal] = {}
    for pid, cid, capital, total, valor, pagado, vence in filas:
        falta = money(valor or 0) - money(pagado or 0)
        if falta <= 0:
            continue
        saldo_prestamo[pid] = saldo_prestamo.get(pid, CERO) + falta
        saldo_cliente[cid] = saldo_cliente.get(cid, CERO) + falta
        datos_prestamo[pid] = (money(capital or 0), money(total) if total else None)
        if vence and vence < hoy:
            atrasadas[cid] = atrasadas.get(cid, 0) + 1

    # Los importados no traen total_pagar: se suma de sus cuotas.
    sin_total = [pid for pid, (_, t) in datos_prestamo.items() if not t]
    if sin_total:
        for pid, t in (db.query(Cuota.prestamo_id, func.sum(Cuota.valor))
                       .filter(Cuota.prestamo_id.in_(sin_total)).group_by(Cuota.prestamo_id)):
            datos_prestamo[pid] = (datos_prestamo[pid][0], money(t or 0))

    capital_pend = interes_pend = CERO
    for pid, saldo in saldo_prestamo.items():
        capital, total = datos_prestamo[pid]
        parte_capital = (capital / total) if total and total > capital else Decimal("1")
        cap = money(saldo * parte_capital)
        capital_pend += cap
        interes_pend += saldo - cap

    amarillos = sum(1 for c in saldo_cliente if 1 <= atrasadas.get(c, 0) < ROJO_DESDE)
    rojos = sum(1 for c in saldo_cliente if atrasadas.get(c, 0) >= ROJO_DESDE)
    en_riesgo = sum((s for c, s in saldo_cliente.items() if atrasadas.get(c, 0) >= 1), CERO)

    # ── Hoy ───────────────────────────────────────────────────────────────
    cobros_hoy = (
        db.query(Cobro, Cliente.nombre)
        .join(Cliente, Cobro.cliente_id == Cliente.id)
        .filter(Cobro.empresa_id == empresa_id, Cobro.zona_id == zona_id, Cobro.fecha == hoy)
        .order_by(Cobro.hora.desc(), Cobro.id.desc())
        .all()
    )
    cobrado = sum((money(c.valor_cobrado) for c, _ in cobros_hoy
                   if c.metodo_pago != "Renovacion"), CERO)
    renovado_descontado = sum((money(c.valor_cobrado) for c, _ in cobros_hoy
                               if c.metodo_pago == "Renovacion"), CERO)

    prestamos_hoy = (
        db.query(Prestamo.id, Prestamo.capital, Prestamo.observaciones)
        .filter(Prestamo.empresa_id == empresa_id, Prestamo.zona_id == zona_id,
                Prestamo.estado.notin_(ESTADOS_FUERA),
                func.coalesce(Prestamo.fecha_desembolso, Prestamo.fecha_inicio) == hoy)
        .all()
    )
    renovaciones = [p for p in prestamos_hoy if (p.observaciones or "").startswith(PREFIJO_RENOVACION)]
    nuevos = [p for p in prestamos_hoy if p not in renovaciones]
    prestado = sum((money(p.capital or 0) for p in prestamos_hoy), CERO)

    no_pagaron = (db.query(func.count(func.distinct(NoPago.cliente_id)))
                  .filter(NoPago.empresa_id == empresa_id, NoPago.zona_id == zona_id,
                          NoPago.fecha == hoy).scalar() or 0)

    # Tarjetas canceladas hoy: prestamos que quedaron pagados con un cobro
    # de hoy (sin contar los saldados por una renovacion).
    canceladas = (
        db.query(func.count(func.distinct(Prestamo.id)))
        .join(Cobro, Cobro.prestamo_id == Prestamo.id)
        .filter(Prestamo.empresa_id == empresa_id, Prestamo.zona_id == zona_id,
                Prestamo.estado.in_(("Pagado", "pagado")), Cobro.fecha == hoy,
                Cobro.metodo_pago != "Renovacion")
        .scalar() or 0
    )
    clientes_nuevos = (db.query(func.count(Cliente.id))
                       .filter(Cliente.empresa_id == empresa_id, Cliente.zona_id == zona_id,
                               Cliente.creado >= inicio_dia_negocio()).scalar() or 0)

    nombres = {u.id: (u.nombre or u.username) for u in
               db.query(Usuario.id, Usuario.nombre, Usuario.username)
               .filter(Usuario.empresa_id == empresa_id)}
    ultimos = [{
        "hora": a_hora_local(c.hora).strftime("%H:%M") if c.hora else "—",
        "cliente": nombre, "valor": money(c.valor_cobrado),
        "cobrador": nombres.get(c.usuario_id, c.cobrador or "—"),
        "metodo": c.metodo_pago or "Efectivo",
    } for c, nombre in cobros_hoy[:12]]

    return {
        "capital_pendiente": capital_pend, "interes_pendiente": interes_pend,
        "saldo_total": capital_pend + interes_pend,
        "hoy": {"cobrado": cobrado, "num_cobros": sum(1 for c, _ in cobros_hoy
                                                       if c.metodo_pago != "Renovacion"),
                "prestado": prestado, "no_pagaron": no_pagaron,
                "renovado_descontado": renovado_descontado},
        "movimiento": {"canceladas": canceladas, "nuevos": len(nuevos),
                       "nuevos_valor": sum((money(p.capital or 0) for p in nuevos), CERO),
                       "renovaciones": len(renovaciones), "clientes_nuevos": clientes_nuevos},
        "cartera": {"clientes": len(saldo_cliente), "amarillos": amarillos, "rojos": rojos,
                    "al_dia": len(saldo_cliente) - amarillos - rojos, "en_riesgo": en_riesgo},
        "ultimos_cobros": ultimos,
    }
