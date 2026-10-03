"""El cuadre semanal de una zona (ver CuadreSemanal en app/database.py).

El sistema propone lo que sabe -- cuanto se cobro y cuanto se presto en la
zona esa semana, y que parte de lo cobrado es interes --; el administrador
pone lo que solo el sabe (gastos, salarios, base, descuento y el efectivo que
conto) y la cuenta sale aqui, en un solo sitio: la misma para "Calcular", para
"Verificar" y para los reportes.

Renovaciones: el saldo que se descuenta al renovar no es efectivo. Por eso el
COBRO no lo incluye y los PRESTAMOS cuentan solo lo entregado en mano
(capital del prestamo nuevo menos lo descontado), que es lo que salio de la
caja de verdad.
"""
from __future__ import annotations

import datetime
from decimal import Decimal

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import Cobro, CuadreSemanal
from app.utils import finanzas as fz
from app.utils.money import money_int

CERO = Decimal("0")
CAMPOS_ADMIN = ("gastos", "salarios", "base", "descuento", "efectivo")


def inicio_semana(fecha: datetime.date) -> datetime.date:
    """El domingo con que empieza la semana de esa fecha.

    El cuadre se hace los sabados: cada semana va de domingo a sabado, y lo
    que se cobre un domingo entra en el cuadre del sabado siguiente.
    """
    return fecha - datetime.timedelta(days=(fecha.weekday() + 1) % 7)


def propuesta(db: Session, empresa_id: int, zona_id: int, semana: datetime.date) -> dict:
    """Lo que el sistema sabe de esa zona esa semana (domingo a sabado)."""
    desde = inicio_semana(semana)
    hasta = desde + datetime.timedelta(days=6)
    r = fz.resumen(db, empresa_id, desde, hasta)
    fila = next((z for z in r["zonas"] if z["zona_id"] == zona_id), None)
    cobrado = fila["cobrado"] if fila else CERO
    prestado = fila["prestado"] if fila else CERO
    intereses = fila["intereses"] if fila else CERO
    renovado = money_int(
        db.query(func.coalesce(func.sum(Cobro.valor_cobrado), 0))
        .filter(Cobro.empresa_id == empresa_id, Cobro.zona_id == zona_id,
                Cobro.fecha >= desde, Cobro.fecha <= hasta,
                Cobro.metodo_pago == "Renovacion")
        .scalar() or 0)
    return {
        "semana": desde, "hasta": hasta,
        "cobro": money_int(cobrado - renovado),
        "prestamos": money_int(max(CERO, prestado - renovado)),
        "intereses": money_int(intereses),
        "renovado": renovado,
    }


def calcular(cobro, prestamos, gastos, salarios, base, descuento, efectivo, intereses) -> dict:
    """La cuenta del cuadre. Todo en pesos enteros."""
    v = {k: money_int(x or 0) for k, x in dict(
        cobro=cobro, prestamos=prestamos, gastos=gastos, salarios=salarios, base=base,
        descuento=descuento, efectivo=efectivo, intereses=intereses).items()}
    esperado = v["base"] + v["cobro"] - v["prestamos"] - v["gastos"] - v["salarios"] - v["descuento"]
    return dict(v, esperado=esperado,
                diferencia=v["efectivo"] - esperado,
                utilidad=v["intereses"] - v["gastos"] - v["salarios"] - v["descuento"])


def verificados(db: Session, empresa_id: int, desde: datetime.date,
                hasta: datetime.date, zona_id: int | None = None) -> list[CuadreSemanal]:
    q = db.query(CuadreSemanal).filter(CuadreSemanal.empresa_id == empresa_id,
                                       CuadreSemanal.semana >= inicio_semana(desde),
                                       CuadreSemanal.semana <= hasta)
    if zona_id:
        q = q.filter(CuadreSemanal.zona_id == zona_id)
    return q.order_by(CuadreSemanal.semana, CuadreSemanal.zona_id).all()
