"""Prestamo service v2.1 - multi-tenant"""
import datetime
from decimal import Decimal, ROUND_HALF_UP
from typing import List
from app.database import Prestamo, Cuota, hoy_local


def _money(value) -> Decimal:
    return Decimal(str(value or "0")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _peso(value) -> Decimal:
    """Pesos enteros: la moneda colombiana no tiene centavos en circulacion."""
    return Decimal(str(value or "0")).quantize(Decimal("1"), rounding=ROUND_HALF_UP)


def calcular_cuotas(capital: float, tasa: float, num_cuotas: int,
                    fecha_inicio: datetime.date, plazo_dias: int = 30) -> dict:
    if num_cuotas <= 0:
        raise ValueError("num_cuotas debe ser mayor que cero")
    if plazo_dias <= 0:
        raise ValueError("plazo_dias debe ser mayor que cero")
    capital = _peso(capital)
    tasa = _money(tasa)
    if capital < 0:
        raise ValueError("capital no puede ser negativo")
    if tasa < 0:
        raise ValueError("tasa no puede ser negativa")
    # El peso colombiano no circula en centavos: una cuota de 933,36 no se
    # puede entregar ni recibir, y al mostrarla redondeada la pantalla y el
    # cobro dejaban de coincidir. Todo el plan se calcula en pesos enteros y
    # el sobrante se acumula en la ultima cuota, que es donde el cliente
    # espera el ajuste.
    interes = _peso(capital * (tasa / Decimal("100")))
    total = capital + interes
    valor_cuota = (total / Decimal(num_cuotas)).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    cuotas = []
    acumulado = Decimal("0.00")
    for i in range(1, num_cuotas + 1):
        valor = valor_cuota if i < num_cuotas else _peso(total - acumulado)
        cuotas.append({
            "numero": i,
            "valor": valor,
            "fecha_vencimiento": fecha_inicio + datetime.timedelta(days=i * plazo_dias),
        })
        acumulado += valor
    return {
        "capital": capital, "tasa_interes": tasa,
        "interes_total": interes, "total_pagar": total,
        "valor_cuota": valor_cuota, "fecha_inicio": fecha_inicio,
        "fecha_fin": fecha_inicio + datetime.timedelta(days=num_cuotas * plazo_dias),
        "num_cuotas": num_cuotas, "cuotas": cuotas,
    }


def get_estado_prestamo(prestamo: Prestamo) -> str:
    hoy = hoy_local()
    if len([c for c in prestamo.cuotas if c.estado == "Vencida"]) >= 3:
        return "Mora"
    if any(c.fecha_vencimiento < hoy and c.estado == "Pendiente" for c in prestamo.cuotas):
        return "Atrasado"
    if all(c.estado == "Pagada" for c in prestamo.cuotas):
        return "Cancelado"
    return "Activo"


def get_saldo_prestamo(prestamo: Prestamo) -> float:
    saldo = _money(prestamo.total_pagar) - sum(_money(c.valor_pagado) for c in prestamo.cuotas)
    return max(Decimal("0.00"), saldo)


def get_cuotas_proximas_vencer(db, empresa_id: int, dias: int = 2) -> List[dict]:
    """FIX: filtra por empresa_id"""
    from app.database import Cliente
    hoy = hoy_local()
    limite = hoy + datetime.timedelta(days=dias)

    cuotas = (
        db.query(Cuota).join(Prestamo).join(Cliente)
        .filter(
            Cuota.empresa_id == empresa_id,
            Cuota.estado == "Pendiente",
            Cuota.fecha_vencimiento >= hoy,
            Cuota.fecha_vencimiento <= limite,
            Cuota.notificado_wp == False,
        ).all()
    )
    hoy_ = hoy_local()
    return [{
        "cuota_id": c.id, "cliente_id": c.prestamo.cliente.id,
        "nombre": c.prestamo.cliente.nombre,
        "telefono": c.prestamo.cliente.whatsapp or c.prestamo.cliente.telefono,
        "num_cuota": c.numero, "valor": c.valor,
        "fecha_vencimiento": c.fecha_vencimiento,
        "dias_restantes": (c.fecha_vencimiento - hoy_).days,
    } for c in cuotas]


def get_cuotas_vencidas_hoy(db, empresa_id: int) -> List[dict]:
    """FIX: filtra por empresa_id y evita notificar dos veces el mismo dia
    si el scheduler y un "enviar ahora" manual coinciden."""
    from app.database import Cliente, NotificacionWP
    hoy = hoy_local()

    ya_notificadas_hoy = db.query(NotificacionWP.cuota_id).filter(
        NotificacionWP.empresa_id == empresa_id,
        NotificacionWP.tipo == "Vencimiento",
        NotificacionWP.creado >= hoy,
    )

    cuotas = (
        db.query(Cuota).join(Prestamo).join(Cliente)
        .filter(
            Cuota.empresa_id == empresa_id,
            Cuota.estado == "Pendiente",
            Cuota.fecha_vencimiento < hoy,
            Cuota.id.notin_(ya_notificadas_hoy),
        ).all()
    )
    return [{
        "cuota_id": c.id, "cliente_id": c.prestamo.cliente.id,
        "nombre": c.prestamo.cliente.nombre,
        "telefono": c.prestamo.cliente.whatsapp or c.prestamo.cliente.telefono,
        "num_cuota": c.numero, "valor": c.valor,
        "fecha_vencimiento": c.fecha_vencimiento,
        "dias_vencida": (hoy - c.fecha_vencimiento).days,
    } for c in cuotas]
