"""Las cuentas del dueño: ciclos de 6 semanas y caja general.

Un prestamo se paga en unas 6 semanas, asi que el negocio se mira en bloques
de 6 semanas desde una fecha que fija el administrador (empresas.ciclo_inicio).
De cada ciclo, zona por zona:

- cobrado:   lo que entro por cobros.
- prestado:  lo que salio en prestamos nuevos (el dia del desembolso).
- intereses: la parte de lo cobrado que es interes. Cada peso cobrado se
             reparte entre capital e interes en la misma proporcion que el
             prestamo: de uno de 500.000 al 20 % (600.000 en total), cada
             peso es 5/6 capital y 1/6 interes.

- gastos, salarios y descuento: los de los cuadres semanales que el
             administrador verifico para esa zona (la caja del cobrador es solo
             una guia y no sube nada). Una semana sin cuadre no aporta gastos.

Y en total:

- resultado:  cobrado - prestado - gastos - salarios - descuento. Es el flujo
              de caja, la plata que de verdad quedo de mas (o de menos, si se
              presto mas de lo que entro: la cartera crecio). Es lo que se
              reparte al cerrar el ciclo.
- ganancia:   intereses - gastos - salarios - descuento. Lo que el negocio
              gano, aunque parte siga en la calle.

La caja general es la plata del dueño. Su saldo no se guarda en ninguna parte:
se calcula cada vez desde el saldo inicial que puso el administrador, mas el
efectivo de cada cuadre semanal verificado, menos la base que se llevo esa
zona, mas o menos lo anotado a mano (retiros, aportes, pagos, reserva,
ajustes) y lo que genera el cierre de cada ciclo. Un saldo guardado acaba
desacordandose de los movimientos que lo explican; uno calculado no puede.
"""
from __future__ import annotations

import datetime
import json
from decimal import Decimal

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import (Cobro, Cuota, Liquidacion, MovimientoCajaGeneral,
                          Prestamo, Zona)
from app.utils.money import money, money_int

SEMANAS_CICLO = 6
DIAS_CICLO = SEMANAS_CICLO * 7
CERO = Decimal("0")

# Que le hace cada tipo anotado a mano a (caja, reserva).
EFECTO_GENERAL = {
    "saldo_inicial": (1, 0),
    "aporte": (1, 0),
    "retiro": (-1, 0),
    "pago_cobrador": (-1, 0),
    "a_reserva": (-1, 1),
    "de_reserva": (1, -1),
    "ajuste_mas": (1, 0),
    "ajuste_menos": (-1, 0),
}
NOMBRES_GENERAL = {
    "saldo_inicial": "Saldo inicial",
    "aporte": "Aporte del dueño",
    "retiro": "Retiro del dueño",
    "pago_cobrador": "Pago a cobrador",
    "a_reserva": "Pasa a reserva",
    "de_reserva": "Sale de la reserva",
    "ajuste_mas": "Ajuste a favor",
    "ajuste_menos": "Ajuste en contra",
}
# Los que el administrador puede anotar a mano desde la pantalla. El saldo
# inicial va por su propio camino (una sola vez) y los pagos a cobradores
# salen del cierre de un ciclo.
TIPOS_MANUALES = ("aporte", "retiro", "a_reserva", "de_reserva", "ajuste_mas", "ajuste_menos")


# ── Ciclos ─────────────────────────────────────────────────────────────────

def ciclo(inicio: datetime.date, numero: int) -> tuple[datetime.date, datetime.date]:
    desde = inicio + datetime.timedelta(days=DIAS_CICLO * (numero - 1))
    return desde, desde + datetime.timedelta(days=DIAS_CICLO - 1)


def numero_de(inicio: datetime.date, fecha: datetime.date) -> int:
    """El ciclo en que cae esa fecha (1, 2, ...). 0 si es antes del inicio."""
    if fecha < inicio:
        return 0
    return (fecha - inicio).days // DIAS_CICLO + 1


# ── Resumen de un periodo ─────────────────────────────────────────────────

def resumen(db: Session, empresa_id: int, desde: datetime.date,
            hasta: datetime.date) -> dict:
    """Las cifras del periodo, por zona y en total. Todo en Decimal."""
    zonas = {z.id: z.nombre for z in db.query(Zona.id, Zona.nombre)
             .filter(Zona.empresa_id == empresa_id)}
    por_zona: dict[int | None, dict] = {}

    def fila(zid):
        if zid not in por_zona:
            por_zona[zid] = {"zona_id": zid, "zona": zonas.get(zid, "Sin zona"),
                             "cobrado": CERO, "prestado": CERO, "intereses": CERO}
        return por_zona[zid]

    # Lo cobrado, prestamo a prestamo: para separar el interes hace falta
    # saber de que prestamo es cada peso.
    cobros = (
        db.query(Cobro.zona_id, Cobro.prestamo_id,
                 func.sum(Cobro.valor_cobrado))
        .filter(Cobro.empresa_id == empresa_id,
                Cobro.fecha >= desde, Cobro.fecha <= hasta)
        .group_by(Cobro.zona_id, Cobro.prestamo_id)
        .all()
    )
    pids = {pid for _, pid, _ in cobros}
    proporcion: dict[int, Decimal] = {}
    if pids:
        prestamos = {p.id: p for p in db.query(Prestamo.id, Prestamo.capital, Prestamo.total_pagar)
                     .filter(Prestamo.id.in_(pids))}
        # Los prestamos importados no traen total_pagar: se suma de las cuotas.
        sin_total = [pid for pid, p in prestamos.items() if not p.total_pagar]
        totales = {}
        if sin_total:
            totales = {pid: money(t or 0) for pid, t in
                       db.query(Cuota.prestamo_id, func.sum(Cuota.valor))
                       .filter(Cuota.prestamo_id.in_(sin_total))
                       .group_by(Cuota.prestamo_id)}
        for pid, p in prestamos.items():
            capital = money(p.capital or 0)
            total = money(p.total_pagar) if p.total_pagar else totales.get(pid, CERO)
            proporcion[pid] = ((total - capital) / total) if total > capital and total > 0 else CERO

    for zid, pid, valor in cobros:
        valor = money(valor or 0)
        f = fila(zid)
        f["cobrado"] += valor
        # En pesos enteros, como todo el negocio (ver calcular_cuotas).
        f["intereses"] += money_int(valor * proporcion.get(pid, CERO))

    # Lo prestado, el dia que salio el dinero (los importados no tienen
    # fecha de desembolso: se toma la de inicio).
    dia_salida = func.coalesce(Prestamo.fecha_desembolso, Prestamo.fecha_inicio)
    for zid, capital in (
        db.query(Prestamo.zona_id, func.sum(Prestamo.capital))
        .filter(Prestamo.empresa_id == empresa_id,
                Prestamo.estado != "Anulado",          # anulado = no salio de verdad
                dia_salida >= desde, dia_salida <= hasta)
        .group_by(Prestamo.zona_id)
        .all()
    ):
        fila(zid)["prestado"] += money(capital or 0)

    # Gastos, salarios y descuentos: los de los cuadres semanales que el
    # administrador verifico para cada zona (la caja del cobrador es solo una
    # guia y no sube nada). Una semana sin cuadre verificado no aporta gastos:
    # por eso se cuenta cuantos faltan, para que el resultado no se lea como
    # definitivo si aun hay semanas sin cuadrar.
    from app.database import CuadreSemanal
    from app.utils.cuadre_semanal import inicio_semana
    lunes = inicio_semana(desde)
    cuadrados = 0
    for c in (db.query(CuadreSemanal)
              .filter(CuadreSemanal.empresa_id == empresa_id,
                      CuadreSemanal.semana >= lunes, CuadreSemanal.semana <= hasta)):
        f = fila(c.zona_id)
        f["gastos"] = f.get("gastos", CERO) + money(c.gastos)
        f["salarios"] = f.get("salarios", CERO) + money(c.salarios)
        f["descuento"] = f.get("descuento", CERO) + money(c.descuento)
        f["semanas_cuadradas"] = f.get("semanas_cuadradas", 0) + 1
        cuadrados += 1
    semanas = ((hasta - lunes).days // 7) + 1
    zonas_activas = db.query(func.count(Zona.id)).filter(
        Zona.empresa_id == empresa_id, Zona.activa == True).scalar() or 0

    filas = sorted(por_zona.values(), key=lambda f: (f["zona"] or "").lower())
    for f in filas:
        for k in ("gastos", "salarios", "descuento"):
            f.setdefault(k, CERO)
        f.setdefault("semanas_cuadradas", 0)
        f["flujo"] = f["cobrado"] - f["prestado"]
        f["resultado"] = f["flujo"] - f["gastos"] - f["salarios"] - f["descuento"]
        f["utilidad"] = f["intereses"] - f["gastos"] - f["salarios"] - f["descuento"]
    total = lambda k: sum((f[k] for f in filas), CERO)  # noqa: E731
    cobrado, prestado, intereses = total("cobrado"), total("prestado"), total("intereses")
    gastos, salarios, descuento = total("gastos"), total("salarios"), total("descuento")
    salidas = gastos + salarios + descuento
    return {
        "desde": desde, "hasta": hasta,
        "zonas": filas,
        "cobrado": cobrado, "prestado": prestado, "intereses": intereses,
        "gastos": gastos, "salarios": salarios, "descuento": descuento,
        "semanas": semanas, "cuadres_verificados": cuadrados,
        "cuadres_esperados": semanas * zonas_activas,
        "resultado": cobrado - prestado - salidas,
        "ganancia": intereses - salidas,
    }


# ── Caja general ───────────────────────────────────────────────────────────

def caja_general(db: Session, empresa_id: int, hoy: datetime.date) -> dict:
    movimientos = (
        db.query(MovimientoCajaGeneral)
        .filter(MovimientoCajaGeneral.empresa_id == empresa_id)
        .order_by(MovimientoCajaGeneral.fecha.desc(), MovimientoCajaGeneral.id.desc())
        .all()
    )
    inicial = next((m for m in movimientos if m.tipo == "saldo_inicial"), None)
    if not inicial:
        return {"activa": False, "movimientos": []}

    caja = reserva = CERO
    for m in movimientos:
        efecto_caja, efecto_reserva = EFECTO_GENERAL.get(m.tipo, (0, 0))
        caja += money(m.valor) * efecto_caja
        reserva += money(m.valor) * efecto_reserva

    # Desde que se activo la caja general, cada cuadre semanal verificado
    # suma el efectivo que la zona devolvio y resta la base que se llevo.
    from app.database import CuadreSemanal
    cuadres = (db.query(CuadreSemanal)
               .filter(CuadreSemanal.empresa_id == empresa_id,
                       CuadreSemanal.verificado_en >= inicial.creado)
               .all()) if inicial.creado else []
    entregas = sum((money(c.efectivo) for c in cuadres), CERO)
    bases = sum((money(c.base) for c in cuadres), CERO)
    caja += entregas - bases
    return {
        "activa": True,
        "desde": inicial.fecha,
        "saldo_inicial": money(inicial.valor),
        "entregas": entregas,
        "bases": bases,
        "cuadres": len(cuadres),
        "caja": caja,
        "reserva": reserva,
        "movimientos": [{
            "id": m.id, "fecha": m.fecha, "tipo": m.tipo,
            "nombre": NOMBRES_GENERAL.get(m.tipo, m.tipo),
            "valor": money(m.valor), "efecto": EFECTO_GENERAL.get(m.tipo, (0, 0))[0],
            "concepto": m.concepto or "", "registrado_por": m.registrado_por or "—",
            "de_liquidacion": bool(m.liquidacion_id),
        } for m in movimientos[:200]],
    }


def detalle_guardado(liq: Liquidacion) -> dict:
    try:
        return json.loads(liq.detalle or "{}")
    except ValueError:
        return {}
