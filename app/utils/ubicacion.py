"""Donde esta cada cliente, deducido de donde se le ha visitado.

En el sistema casi no hay direcciones: de 1.773 clientes, 9 tienen una, y
convertir direcciones de barrio ("Mz K casa 20") en coordenadas con un servicio
externo sale caro, acierta poco y obliga a mandar a un tercero donde vive cada
deudor. Lo que si hay es el GPS del celular del cobrador en cada visita:

- el cobro lo guarda solo, con cada pago;
- la visita sin pago tambien lo guarda (sin esto, los que no pagan -- justo los
  que mas hay que visitar -- no tendrian posicion nunca);
- y al dar de alta un cliente desde la calle, se guarda donde se le dio de alta.

La posicion de un cliente no la teclea nadie: se deduce de sus visitas. Por
eso no choca con la regla de que el cobrador no modifica la ficha de un
cliente -- lo que se guarda es dato de la visita, igual que la foto del cobro.
"""
from __future__ import annotations

import math
from statistics import median

from sqlalchemy import func, select, union_all
from sqlalchemy.orm import Session

from app.database import Cliente, Cobro, NoPago

# Cuantas visitas recientes se usan por cliente. Mas no mejora la posicion --
# la gente se muda, y una visita de hace un año pesa lo mismo que la de ayer --
# y si alarga la consulta.
VISITAS_POR_CLIENTE = 10

# Un punto donde "estan" varios clientes distintos no es la casa de ninguno:
# es donde el cobrador registra los pagos (su casa, la oficina, la tienda
# donde le pagan). En produccion aparecio asi: 29 clientes con cobros desde
# el mismo punto. Desde cuantos clientes se descarta el punto, y el tamaño de
# la celda (0,0001 grados, unos 11 m; se miran tambien las 8 vecinas, asi que
# el radio efectivo es de unos 30 m).
CLIENTES_POR_PUNTO_SOSPECHOSO = 4
_CELDA = 1e-4


def leer_coordenadas(lat: str | None, lng: str | None) -> tuple[float | None, float | None]:
    """Las coordenadas de un formulario, o (None, None) si no sirven.

    No lanza errores a proposito: donde se usa -- registrar que alguien no
    pago, dar de alta un cliente -- un GPS malo no puede impedir guardar la
    visita. Se guarda sin posicion y listo.

    Descarta tres casos que llegan de verdad desde un celular:
    - solo una de las dos: una latitud sin longitud no situa nada;
    - fuera de rango: un valor corrupto;
    - (0, 0): la "isla nula" en el golfo de Guinea, lo que devuelven algunos
      telefonos cuando no consiguen posicion pero contestan igualmente.
    """
    try:
        la = float(lat) if lat not in (None, "") and str(lat).strip() else None
        lo = float(lng) if lng not in (None, "") and str(lng).strip() else None
    except (TypeError, ValueError):
        return None, None
    if la is None or lo is None:
        return None, None
    if not (-90 <= la <= 90 and -180 <= lo <= 180):
        return None, None
    if abs(la) < 1e-6 and abs(lo) < 1e-6:
        return None, None
    return la, lo


def distancia_m(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Distancia en metros entre dos puntos (haversine)."""
    r = 6_371_000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def posiciones_de_clientes(db: Session, empresa_id: int,
                           cliente_ids: list[int]) -> dict[int, dict]:
    """{cliente_id: {"lat", "lng", "fuente", "visitas"}} de los que se pueda.

    Una sola consulta para toda la zona, se abra la ruta que se abra: esta
    funcion corre cada vez que el cobrador elige zona, y una consulta por
    cliente serian doscientas idas y vueltas a la base en esa pantalla.

    Dos fuentes, en este orden:
    1. La posicion de la ficha (la que se guardo al darlo de alta, o la que
       puso el administrador a mano). Es deliberada, asi que manda.
    2. La mediana de sus ultimas visitas con GPS -- cobros y visitas sin pago.
       Mediana y no media: si un cobro se registro mas tarde desde otro sitio,
       la media se va a medio camino y la mediana ni se entera.
    """
    if not cliente_ids:
        return {}

    posiciones: dict[int, dict] = {}
    for cid, lat, lng in (
        db.query(Cliente.id, Cliente.lat, Cliente.lng)
        .filter(Cliente.empresa_id == empresa_id, Cliente.id.in_(cliente_ids),
                Cliente.lat.isnot(None), Cliente.lng.isnot(None))
        .all()
    ):
        la, lo = leer_coordenadas(lat, lng)
        if la is not None:
            posiciones[cid] = {"lat": la, "lng": lo, "fuente": "ficha", "visitas": 0}

    faltan = [c for c in cliente_ids if c not in posiciones]
    if not faltan:
        return posiciones

    visitas = union_all(
        select(Cobro.cliente_id.label("cid"), Cobro.lat_cobro.label("lat"),
               Cobro.lng_cobro.label("lng"), Cobro.hora.label("momento"))
        .where(Cobro.empresa_id == empresa_id, Cobro.cliente_id.in_(faltan),
               Cobro.lat_cobro.isnot(None), Cobro.lng_cobro.isnot(None)),
        select(NoPago.cliente_id, NoPago.lat, NoPago.lng, NoPago.creado)
        .where(NoPago.empresa_id == empresa_id, NoPago.cliente_id.in_(faltan),
               NoPago.lat.isnot(None), NoPago.lng.isnot(None)),
    ).subquery()
    # Las ultimas N por cliente se eligen en la base, no aqui: un cliente con
    # un año de cobros diarios tiene cientos, y traerlos todos para quedarse
    # con diez es trabajo tirado en cada carga de la zona.
    orden = func.row_number().over(
        partition_by=visitas.c.cid, order_by=visitas.c.momento.desc()
    ).label("orden")
    numeradas = select(visitas.c.cid, visitas.c.lat, visitas.c.lng, orden).subquery()
    filas = db.execute(
        select(numeradas.c.cid, numeradas.c.lat, numeradas.c.lng)
        .where(numeradas.c.orden <= VISITAS_POR_CLIENTE)
    ).all()

    puntos_validos: list[tuple[int, float, float]] = []
    for cid, lat, lng in filas:
        la, lo = leer_coordenadas(lat, lng)
        if la is not None:
            puntos_validos.append((cid, la, lo))

    sospechosas = _celdas_compartidas(puntos_validos)
    por_cliente: dict[int, list[tuple[float, float]]] = {}
    for cid, la, lo in puntos_validos:
        if _celda(la, lo) in sospechosas:
            continue
        por_cliente.setdefault(cid, []).append((la, lo))

    for cid, puntos in por_cliente.items():
        posiciones[cid] = {
            "lat": median(p[0] for p in puntos),
            "lng": median(p[1] for p in puntos),
            "fuente": "visitas",
            "visitas": len(puntos),
        }
    return posiciones


def _celda(lat: float, lng: float) -> tuple[int, int]:
    return round(lat / _CELDA), round(lng / _CELDA)


def _celdas_compartidas(puntos: list[tuple[int, float, float]]) -> set[tuple[int, int]]:
    """Celdas donde hay visitas de demasiados clientes distintos.

    Se cuenta cada celda junto con sus ocho vecinas: un mismo sitio medido
    por un GPS de celular baila unos metros y cae a veces en la celda de al
    lado, y contarlas por separado partiria el grupo en trozos pequeños que
    no llegarian al umbral.
    """
    clientes_en: dict[tuple[int, int], set[int]] = {}
    for cid, la, lo in puntos:
        clientes_en.setdefault(_celda(la, lo), set()).add(cid)
    sospechosas = set()
    for (x, y) in clientes_en:
        vecinos: set[int] = set()
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                vecinos |= clientes_en.get((x + dx, y + dy), set())
        if len(vecinos) >= CLIENTES_POR_PUNTO_SOSPECHOSO:
            sospechosas.add((x, y))
    return sospechosas
