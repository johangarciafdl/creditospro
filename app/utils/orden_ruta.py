"""El orden en que un cobrador recorre cada zona.

Reglas (decididas con el negocio):

- El orden es de cada cobrador y por zona. Lo arma el arrastrando tarjetas, o
  el administrador por el. Es el mismo en la vista simple y en Cobros ->
  Pendientes de la clasica.
- Una vez puesto, nada lo mueve solo: ni cobrar, ni que alguien cambie de
  color, ni que le den un prestamo nuevo a un cliente que ya estaba.
- Lo unico que entra solo es el cliente recien dado de alta: aparece arriba.
- Una zona que el cobrador nunca ha ordenado sale alfabetica, con los
  clientes recien dados de alta arriba (del mas nuevo al mas viejo).

Todo se resuelve con una consulta por peticion; el orden de una zona son unas
centenas de filas como mucho.
"""
from __future__ import annotations

import datetime
from typing import Iterable

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import Cliente, OrdenRuta, ahora_utc

# Cuanto tiempo un cliente dado de alta cuenta como "nuevo" y, si el cobrador
# aun no lo tiene en su orden, sale arriba.
RECIENTE = datetime.timedelta(days=3)


def es_reciente(momento: datetime.datetime | None) -> bool:
    return bool(momento) and momento >= ahora_utc() - RECIENTE


def posiciones(db: Session, usuario_id: int | None,
               zona_ids: Iterable[int]) -> dict[tuple[int, int], int]:
    """{(zona_id, cliente_id): posicion} del orden de ese usuario."""
    zona_ids = [z for z in zona_ids if z]
    if not usuario_id or not zona_ids:
        return {}
    return {
        (z, c): p for z, c, p in (
            db.query(OrdenRuta.zona_id, OrdenRuta.cliente_id, OrdenRuta.posicion)
            .filter(OrdenRuta.usuario_id == usuario_id,
                    OrdenRuta.zona_id.in_(zona_ids))
            .all()
        )
    }


def clave_de_orden(cliente: Cliente, pos: dict[tuple[int, int], int]):
    """Clave para sorted(): lo que tiene posicion, por posicion; lo nuevo sin
    posicion, arriba de todo; el resto sin posicion, al final y alfabetico.

    Va dentro de cada zona: quien ordena por zona agrupa antes por zona.
    """
    p = pos.get((cliente.zona_id, cliente.id))
    if p is not None:
        return (1, p, "")
    nombre = (cliente.nombre or "").lower()
    if es_reciente(cliente.creado):
        # Del mas nuevo al mas viejo: el timestamp negado ordena al reves.
        return (0, -cliente.creado.timestamp(), nombre)
    return (2, 0, nombre)


def guardar(db: Session, empresa_id: int, usuario_id: int, zona_id: int,
            todos: list[Cliente], ordenados: list[int]) -> int:
    """Guarda el orden nuevo de una zona. Devuelve cuantos quedaron.

    `ordenados` puede ser un subconjunto de la zona: la lista de Pendientes de
    la clasica solo muestra a quien debe, y la vista simple puede estar
    filtrada por el buscador. Los que no vienen conservan su lugar; los que
    vienen se reparten, en el orden nuevo, en los huecos que ya ocupaban.
    Asi, reordenar lo que se ve nunca desordena lo que no se ve.
    """
    pos = posiciones(db, usuario_id, [zona_id])
    actual = [c.id for c in sorted(todos, key=lambda c: clave_de_orden(c, pos))]
    en_zona = set(actual)
    vistos: list[int] = []
    for cid in ordenados:
        if cid in en_zona and cid not in vistos:
            vistos.append(cid)
    marcados = set(vistos)
    huecos = iter(vistos)
    nuevo = [next(huecos) if cid in marcados else cid for cid in actual]

    db.query(OrdenRuta).filter(OrdenRuta.usuario_id == usuario_id,
                               OrdenRuta.zona_id == zona_id).delete(synchronize_session=False)
    ahora = ahora_utc()
    db.add_all([
        OrdenRuta(empresa_id=empresa_id, usuario_id=usuario_id, zona_id=zona_id,
                  cliente_id=cid, posicion=i, actualizado=ahora)
        for i, cid in enumerate(nuevo)
    ])
    return len(nuevo)


def poner_arriba(db: Session, empresa_id: int, zona_id: int, cliente_id: int) -> None:
    """Un cliente que acaba de llegar a la zona entra arriba en el orden de
    cada cobrador que ya la tiene ordenada. Si no, con el orden fijo, quedaria
    donde cayera al dejar de ser "reciente" -- un salto que nadie pidio.
    """
    if not zona_id or not cliente_id:
        return
    minimos = (
        db.query(OrdenRuta.usuario_id, func.min(OrdenRuta.posicion))
        .filter(OrdenRuta.empresa_id == empresa_id, OrdenRuta.zona_id == zona_id)
        .group_by(OrdenRuta.usuario_id)
        .all()
    )
    if not minimos:
        return
    ya = {u for (u,) in db.query(OrdenRuta.usuario_id).filter(
        OrdenRuta.zona_id == zona_id, OrdenRuta.cliente_id == cliente_id).all()}
    ahora = ahora_utc()
    db.add_all([
        OrdenRuta(empresa_id=empresa_id, usuario_id=u, zona_id=zona_id,
                  cliente_id=cliente_id, posicion=(m or 0) - 1, actualizado=ahora)
        for u, m in minimos if u not in ya
    ])
