"""
Lógica de negocio para préstamos y cuotas
"""
import datetime
from typing import List
from app.database import Prestamo, Cuota


def calcular_cuotas(capital: float, tasa: float, num_cuotas: int, fecha_inicio: datetime.date, plazo_dias: int = 30) -> dict:
    """
    Calcula los valores del préstamo
    """
    interes = capital * (tasa / 100)
    total = capital + interes
    valor_cuota = round(total / num_cuotas, 0)
    fecha_fin = fecha_inicio + datetime.timedelta(days=num_cuotas * plazo_dias)

    cuotas = []
    for i in range(1, num_cuotas + 1):
        fecha_venc = fecha_inicio + datetime.timedelta(days=i * plazo_dias)
        cuotas.append({
            "numero": i,
            "valor": valor_cuota,
            "fecha_vencimiento": fecha_venc,
        })

    return {
        "capital": capital,
        "tasa_interes": tasa,
        "interes_total": interes,
        "total_pagar": total,
        "valor_cuota": valor_cuota,
        "fecha_inicio": fecha_inicio,
        "fecha_fin": fecha_fin,
        "num_cuotas": num_cuotas,
        "cuotas": cuotas,
    }


def get_estado_prestamo(prestamo: Prestamo) -> str:
    hoy = datetime.date.today()
    cuotas_vencidas = [c for c in prestamo.cuotas if c.estado == "Vencida"]
    if len(cuotas_vencidas) >= 3:
        return "Mora"
    if any(c.fecha_vencimiento < hoy and c.estado == "Pendiente" for c in prestamo.cuotas):
        return "Atrasado"
    if all(c.estado == "Pagada" for c in prestamo.cuotas):
        return "Cancelado"
    return "Activo"


def get_saldo_prestamo(prestamo: Prestamo) -> float:
    pagado = sum(c.valor_pagado for c in prestamo.cuotas)
    return max(0, prestamo.total_pagar - pagado)


def get_cuotas_proximas_vencer(db, dias: int = 2) -> List[dict]:
    """
    Retorna cuotas que vencen en los próximos `dias` días
    """
    from app.database import Cuota, Prestamo, Cliente
    hoy = datetime.date.today()
    limite = hoy + datetime.timedelta(days=dias)

    cuotas = (
        db.query(Cuota)
        .join(Prestamo)
        .join(Cliente)
        .filter(
            Cuota.estado == "Pendiente",
            Cuota.fecha_vencimiento >= hoy,
            Cuota.fecha_vencimiento <= limite,
            Cuota.notificado_wp == False,
        )
        .all()
    )

    resultado = []
    for c in cuotas:
        prestamo = c.prestamo
        cliente = prestamo.cliente
        resultado.append({
            "cuota_id": c.id,
            "cliente_id": cliente.id,
            "nombre": cliente.nombre,
            "telefono": cliente.whatsapp or cliente.telefono,
            "num_cuota": c.numero,
            "valor": c.valor,
            "fecha_vencimiento": c.fecha_vencimiento,
            "dias_restantes": (c.fecha_vencimiento - hoy).days,
        })

    return resultado


def get_cuotas_vencidas_hoy(db) -> List[dict]:
    from app.database import Cuota, Prestamo, Cliente
    hoy = datetime.date.today()

    cuotas = (
        db.query(Cuota)
        .join(Prestamo)
        .join(Cliente)
        .filter(
            Cuota.estado == "Pendiente",
            Cuota.fecha_vencimiento < hoy,
        )
        .all()
    )

    resultado = []
    for c in cuotas:
        prestamo = c.prestamo
        cliente = prestamo.cliente
        resultado.append({
            "cuota_id": c.id,
            "cliente_id": cliente.id,
            "nombre": cliente.nombre,
            "telefono": cliente.whatsapp or cliente.telefono,
            "num_cuota": c.numero,
            "valor": c.valor,
            "fecha_vencimiento": c.fecha_vencimiento,
            "dias_vencida": (hoy - c.fecha_vencimiento).days,
        })

    return resultado
