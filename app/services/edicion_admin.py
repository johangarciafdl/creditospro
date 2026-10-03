"""Lo que el administrador puede corregir: cobros, prestamos y clientes.

Corregir un cobro o un prestamo cambia cuanto se ha pagado de cada cuota.
En vez de restar y sumar a mano (y equivocarse con un abono parcial o con un
pago que tocaba dos cuotas), se REHACE el reparto: se ponen todas las cuotas
en cero y se vuelven a aplicar los pagos en orden.

Cuidado con lo importado: en ElRusso casi todo lo pagado se cargo sin cobros
(hay 161 cobros para 7.390 cuotas). Lo que la cuota tiene pagado y ningun
cobro explica es un "pago anterior" y se conserva: se aplica primero, antes
de los cobros. Rehacer nunca borra plata que ya estaba pagada.

Eliminar no borra: el prestamo se anula y el cliente se retira; quedan en el
historial y sus cobros siguen en los reportes de su semana.
"""
from __future__ import annotations

import datetime
from decimal import Decimal

from sqlalchemy.orm import Session

from app.database import Cobro, Cuota, NoPago, Prestamo, ahora_utc, hoy_local
from app.services.prestamo_service import calcular_cuotas
from app.utils.money import money

CERO = Decimal("0")
PENDIENTES = ("Pendiente", "Vencida", "Parcial")


class EdicionInvalida(ValueError):
    pass


def _cuotas(db: Session, prestamo: Prestamo) -> list[Cuota]:
    return (db.query(Cuota).filter(Cuota.prestamo_id == prestamo.id)
            .order_by(Cuota.numero).all())


def _cobros(db: Session, prestamo: Prestamo) -> list[Cobro]:
    return (db.query(Cobro).filter(Cobro.prestamo_id == prestamo.id)
            .order_by(Cobro.fecha, Cobro.id).all())


def pagado_sin_cobro(db: Session, prestamo: Prestamo) -> Decimal:
    """Lo pagado que ningun cobro explica (importado). Se mide ANTES de
    cambiar nada."""
    pagado = sum((money(c.valor_pagado or 0) for c in _cuotas(db, prestamo)), CERO)
    cobrado = sum((money(c.valor_cobrado or 0) for c in _cobros(db, prestamo)), CERO)
    return max(CERO, pagado - cobrado)


def reconstruir(db: Session, prestamo: Prestamo, previo: Decimal) -> None:
    """Vuelve a repartir lo pagado entre las cuotas, en orden."""
    cuotas = _cuotas(db, prestamo)
    cobros = _cobros(db, prestamo)
    total_cuotas = sum((money(c.valor) for c in cuotas), CERO)
    total_pagos = previo + sum((money(c.valor_cobrado) for c in cobros), CERO)
    if total_pagos > total_cuotas:
        raise EdicionInvalida(
            f"Lo pagado ({total_pagos:,.0f}) supera el total del prestamo ({total_cuotas:,.0f}).".replace(",", "."))

    for c in cuotas:
        c.valor_pagado = CERO
        c.fecha_pago = None
    i = 0

    def aplicar(valor: Decimal, fecha):
        nonlocal i
        primera = None
        while valor > 0 and i < len(cuotas):
            c = cuotas[i]
            falta = money(c.valor) - money(c.valor_pagado)
            parte = min(falta, valor)
            c.valor_pagado = money(c.valor_pagado) + parte
            valor -= parte
            if primera is None:
                primera = c
            if money(c.valor_pagado) >= money(c.valor):
                c.fecha_pago = fecha
                i += 1
        return primera

    aplicar(previo, None)
    for co in cobros:
        primera = aplicar(money(co.valor_cobrado), co.fecha)
        if primera is not None:
            co.cuota_id = primera.id

    hoy = hoy_local()
    for c in cuotas:
        if money(c.valor_pagado) >= money(c.valor):
            c.estado = "Pagada"
        elif money(c.valor_pagado) > 0:
            c.estado = "Parcial"
        else:
            c.estado = "Vencida" if c.fecha_vencimiento and c.fecha_vencimiento < hoy else "Pendiente"
    if prestamo.estado != "Anulado":
        prestamo.estado = "Pagado" if all(c.estado == "Pagada" for c in cuotas) else "Activo"


def editar_cobro(db: Session, cobro: Cobro, nuevo_valor: Decimal) -> None:
    prestamo = db.get(Prestamo, cobro.prestamo_id)
    previo = pagado_sin_cobro(db, prestamo)
    cobro.valor_cobrado = money(nuevo_valor)
    db.flush()
    reconstruir(db, prestamo, previo)


def eliminar_cobro(db: Session, cobro: Cobro) -> None:
    prestamo = db.get(Prestamo, cobro.prestamo_id)
    previo = pagado_sin_cobro(db, prestamo)
    db.delete(cobro)
    db.flush()
    reconstruir(db, prestamo, previo)


def editar_prestamo(db: Session, prestamo: Prestamo, capital, tasa, num_cuotas: int,
                    plazo_dias: int, fecha_inicio: datetime.date) -> None:
    """Rehace las cuotas con los valores nuevos y vuelve a aplicar lo pagado."""
    if prestamo.estado == "Anulado":
        raise EdicionInvalida("El prestamo esta anulado.")
    previo = pagado_sin_cobro(db, prestamo)
    calc = calcular_cuotas(capital, tasa, num_cuotas, fecha_inicio, plazo_dias)
    nuevas = calc.get("cuotas", [])
    viejas = _cuotas(db, prestamo)
    for idx, datos in enumerate(nuevas):
        if idx < len(viejas):
            c = viejas[idx]
            c.numero = int(datos["numero"])
            c.valor = money(datos.get("valor"))
            c.fecha_vencimiento = datos["fecha_vencimiento"]
            c.valor_pagado = CERO                     # se reparte de nuevo abajo
        else:
            db.add(Cuota(empresa_id=prestamo.empresa_id, prestamo_id=prestamo.id,
                         numero=int(datos["numero"]), valor=money(datos.get("valor")),
                         fecha_vencimiento=datos["fecha_vencimiento"], estado="Pendiente",
                         valor_pagado=CERO))
    sobrantes = viejas[len(nuevas):]
    if sobrantes:
        destino = viejas[0]
        ids = [c.id for c in sobrantes]
        # Los cobros y visitas que apuntaban a cuotas que desaparecen pasan a
        # la primera (el reparto de abajo las vuelve a colocar).
        db.query(Cobro).filter(Cobro.cuota_id.in_(ids)).update(
            {Cobro.cuota_id: destino.id}, synchronize_session=False)
        db.query(NoPago).filter(NoPago.cuota_id.in_(ids)).update(
            {NoPago.cuota_id: destino.id}, synchronize_session=False)
        for c in sobrantes:
            db.delete(c)
    prestamo.capital = money(capital)
    prestamo.tasa_interes = money(tasa)
    prestamo.interes_total = money(calc.get("interes_total"))
    prestamo.total_pagar = money(calc.get("total_pagar"))
    prestamo.num_cuotas = num_cuotas
    prestamo.valor_cuota = money(calc.get("valor_cuota"))
    prestamo.plazo_dias = plazo_dias
    prestamo.fecha_inicio = fecha_inicio
    prestamo.fecha_fin = calc.get("fecha_fin")
    db.flush()
    reconstruir(db, prestamo, previo)


def anular_prestamo(db: Session, prestamo: Prestamo, quien: str, motivo: str) -> None:
    if prestamo.estado == "Anulado":
        raise EdicionInvalida("Ese prestamo ya esta anulado.")
    prestamo.estado = "Anulado"
    prestamo.anulado_por = quien
    prestamo.anulado_en = ahora_utc()
    prestamo.motivo_anulacion = motivo or None
    for c in _cuotas(db, prestamo):
        if c.estado in PENDIENTES:
            c.estado = "Anulada"


def retirar_cliente(db: Session, cliente, quien: str, motivo: str) -> int:
    """Retira al cliente y anula sus prestamos con saldo. Devuelve cuantos."""
    if not cliente.activo:
        raise EdicionInvalida("Ese cliente ya esta retirado.")
    cliente.activo = False
    cliente.retirado_por = quien
    cliente.retirado_en = ahora_utc()
    cliente.motivo_retiro = motivo or None
    n = 0
    for p in db.query(Prestamo).filter(Prestamo.cliente_id == cliente.id,
                                       Prestamo.estado.notin_(("Anulado", "Pagado", "Cancelado"))):
        anular_prestamo(db, p, quien, f"Cliente retirado: {motivo}" if motivo else "Cliente retirado")
        n += 1
    return n
