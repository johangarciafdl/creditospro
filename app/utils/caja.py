"""El cuadre de caja de un cobrador: cuanto dinero deberia tener encima.

Un cobrador sale por la manana con una base -- normalmente 500.000, pero la
escribe el administrador cada vez porque hay dias que pide mas --, recoge
durante el dia, presta parte de lo que recoge, se descuenta el almuerzo y
devuelve el resto por la tarde. Si al contar no cuadra, hay que poder decir
exactamente donde se rompio; y si nadie lleva la cuenta, un cobrador
descuadrado se descubre semanas despues o no se descubre.

    esperado = base + cobrado - prestado - viaticos - entregas +/- ajustes

Cada sumando sale de su propia tabla y ninguno se copia:

- base, entregas y ajustes  ->  movimientos_caja
- cobrado                   ->  cobros   (neto: las devueltas que el cobrador
                                le da al cliente ya estan descontadas de lo
                                que registro, no son una linea aparte)
- prestado                  ->  prestamos, por desembolsado_por_id
- viaticos                  ->  no son una fila, se calculan (ver abajo)

Todo el calculo vive aqui y no en el router porque la misma cifra la miran el
cobrador y el administrador, y dos implementaciones del mismo numero acaban
dando dos numeros distintos -- que es exactamente lo que un cuadre de caja no
puede permitirse.
"""
from __future__ import annotations

import datetime
from decimal import Decimal

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import Cobro, MovimientoCaja, Prestamo, Usuario
from app.utils.money import money

# Los 15.000 del almuerzo. No se guardan como fila: serian una fila por
# cobrador y por dia, lo que obliga a una tarea programada que ademas
# generaria filas los dias que nadie salio a la calle. Se calculan, y solo
# los dias en que el cobrador se movio -- tuvo base, cobro algo o presto algo.
# Si un dia concreto no le tocan, el admin lo corrige con un ajuste.
VIATICO_DIARIO = Decimal("15000")

TIPOS = ("base", "entrega", "ajuste_mas", "ajuste_menos")

# Que le hace cada tipo al dinero que el cobrador lleva encima.
EFECTO = {
    "base": 1,          # la oficina le entrega
    "entrega": -1,      # el devuelve a la oficina
    "ajuste_mas": 1,
    "ajuste_menos": -1,
}

NOMBRES = {
    "base": "Base entregada",
    "entrega": "Entregado a la oficina",
    "ajuste_mas": "Ajuste a favor",
    "ajuste_menos": "Ajuste en contra",
}


def cuadre(db: Session, empresa_id: int, usuario_id: int,
           fecha: datetime.date) -> dict:
    """El cuadre de ese cobrador ese dia, con el desglose que lo explica.

    Devuelve siempre la misma forma, tambien cuando no hubo movimiento: una
    pantalla que a veces trae unas claves y a veces otras obliga a cada
    consumidor a defenderse, y alguno se olvida.
    """
    base = Decimal("0")
    entregado = Decimal("0")
    ajustes = Decimal("0")
    movimientos = []

    filas = (
        db.query(MovimientoCaja)
        .filter(MovimientoCaja.empresa_id == empresa_id,
                MovimientoCaja.usuario_id == usuario_id,
                MovimientoCaja.fecha == fecha)
        .order_by(MovimientoCaja.id)
        .all()
    )
    for m in filas:
        valor = money(m.valor)
        if m.tipo == "base":
            base += valor
        elif m.tipo == "entrega":
            entregado += valor
        else:
            ajustes += valor * EFECTO.get(m.tipo, 0)
        movimientos.append({
            "id": m.id,
            "tipo": m.tipo,
            "nombre": NOMBRES.get(m.tipo, m.tipo),
            "valor": float(valor),
            "efecto": EFECTO.get(m.tipo, 0),
            "concepto": m.concepto or "",
            "registrado_por": m.registrado_por or "—",
        })

    cobrado = money(
        db.query(func.coalesce(func.sum(Cobro.valor_cobrado), 0))
        .filter(Cobro.empresa_id == empresa_id,
                Cobro.usuario_id == usuario_id,
                Cobro.fecha == fecha)
        .scalar() or 0
    )
    num_cobros = (
        db.query(func.count(Cobro.id))
        .filter(Cobro.empresa_id == empresa_id,
                Cobro.usuario_id == usuario_id,
                Cobro.fecha == fecha)
        .scalar() or 0
    )

    prestado = money(
        db.query(func.coalesce(func.sum(Prestamo.capital), 0))
        .filter(Prestamo.empresa_id == empresa_id,
                Prestamo.desembolsado_por_id == usuario_id,
                Prestamo.fecha_desembolso == fecha)
        .scalar() or 0
    )
    num_prestamos = (
        db.query(func.count(Prestamo.id))
        .filter(Prestamo.empresa_id == empresa_id,
                Prestamo.desembolsado_por_id == usuario_id,
                Prestamo.fecha_desembolso == fecha)
        .scalar() or 0
    )

    hubo_movimiento = bool(filas or num_cobros or num_prestamos)
    viaticos = VIATICO_DIARIO if hubo_movimiento else Decimal("0")

    esperado = base + cobrado - prestado - viaticos - entregado + ajustes

    return {
        "usuario_id": usuario_id,
        "fecha": fecha.isoformat(),
        "base": float(base),
        "cobrado": float(cobrado),
        "num_cobros": num_cobros,
        "prestado": float(prestado),
        "num_prestamos": num_prestamos,
        "viaticos": float(viaticos),
        "entregado": float(entregado),
        "ajustes": float(ajustes),
        "esperado": float(esperado),
        "hubo_movimiento": hubo_movimiento,
        # Sobregiro: el cobrador presta con lo que recoge, asi que prestar mas
        # de lo cobrado en el dia significa que echo mano de la base o de
        # dinero que no era suyo. No se prohibe -- hay dias en que la oficina
        # lo autoriza -- pero tiene que verse.
        "sobregiro": bool(prestado > cobrado),
        "sobregiro_valor": float(max(Decimal("0"), prestado - cobrado)),
        "movimientos": movimientos,
    }


def cuadre_de_todos(db: Session, empresa_id: int,
                    fecha: datetime.date) -> list[dict]:
    """El cuadre del dia de cada cobrador de la empresa, para el admin.

    Incluye a los que no se movieron: un cobrador que no aparece en la lista
    es indistinguible de uno que no existe, y lo que el administrador necesita
    saber por la tarde es precisamente quien no ha entregado.
    """
    usuarios = (
        db.query(Usuario)
        .filter(Usuario.empresa_id == empresa_id,
                Usuario.activo == True,
                Usuario.rol.notin_(("admin", "superadmin")))
        .order_by(Usuario.nombre)
        .all()
    )
    salida = []
    for u in usuarios:
        fila = cuadre(db, empresa_id, u.id, fecha)
        fila["nombre"] = u.nombre or u.username
        fila["username"] = u.username
        salida.append(fila)
    return salida
