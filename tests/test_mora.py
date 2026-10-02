"""El panel de mora: el mismo semaforo de la ruta, por zona, por cobrador y
con lo que cambio en la ultima semana."""
import datetime
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import (Base, Cliente, Cobro, Cuota, Empresa, Prestamo, Usuario, Zona,
                          hoy_local)
from app.utils.mora import panel

HOY = hoy_local()


@pytest.fixture()
def db():
    motor = create_engine("sqlite://")
    Base.metadata.create_all(motor)
    s = sessionmaker(bind=motor)()
    e = Empresa(id=1, nombre="MoraSA")
    z = Zona(id=1, empresa_id=1, codigo="M1", nombre="Centro", activa=True)
    cob = Usuario(id=1, empresa_id=1, username="moracob", nombre="Mora Cob", rol="cobrador",
                  password_hash="x", activo=True)
    s.add_all([e, z, cob]); s.flush()
    cob.zonas_asignadas.append(z)
    s.commit()
    yield s
    s.close()


def _cliente(s, nombre, vencidas_hace, pagadas=(), cobros=()):
    """Un cliente con una cuota de 10.000 por cada dia de `vencidas_hace`
    (dias atras que vencio). `pagadas`: indices pagados del todo hoy.
    `cobros`: (indice, dias_atras) con el cobro que la pago."""
    c = Cliente(empresa_id=1, cedula=nombre, nombre=nombre, telefono="3000000000",
                zona_id=1, activo=True)
    s.add(c); s.flush()
    p = Prestamo(empresa_id=1, cliente_id=c.id, zona_id=1, capital=Decimal("100000"),
                 tasa_interes=Decimal("20"), total_pagar=Decimal("120000"),
                 num_cuotas=len(vencidas_hace), valor_cuota=Decimal("10000"), estado="Activo",
                 fecha_inicio=HOY - datetime.timedelta(days=60), fecha_fin=HOY)
    s.add(p); s.flush()
    for i, dias in enumerate(vencidas_hace):
        pagada = i in pagadas
        cu = Cuota(empresa_id=1, prestamo_id=p.id, numero=i + 1, valor=Decimal("10000"),
                   valor_pagado=Decimal("10000" if pagada else "0"),
                   estado="Pagada" if pagada else "Pendiente",
                   fecha_vencimiento=HOY - datetime.timedelta(days=dias))
        s.add(cu); s.flush()
        for idx, atras in cobros:
            if idx == i:
                s.add(Cobro(empresa_id=1, cuota_id=cu.id, prestamo_id=p.id, cliente_id=c.id,
                            zona_id=1, valor_cobrado=Decimal("10000"),
                            fecha=HOY - datetime.timedelta(days=atras)))
    s.commit()
    return c.id


def test_el_semaforo_y_lo_que_cambio_en_la_semana(db):
    _cliente(db, "Amarilla", [3, -5])                      # 1 atrasada
    rojo = _cliente(db, "Nuevo Rojo", [20, 15, 10, 5, 2])  # 5 hoy; hace 7 dias 3
    _cliente(db, "Al Dia", [-2, -9])                       # nada vencido
    sale = _cliente(db, "Pago Todo", [30, 25, 20, 15],     # hace 7 dias 4 (rojo)
                    pagadas={0, 1, 2, 3},
                    cobros=[(0, 2), (1, 2), (2, 2), (3, 2)])
    p = panel(db, 1, HOY)
    t = p["totales"]
    assert (t["verde"], t["amarillo"], t["rojo"]) == (1, 1, 1)
    assert t["cartera"] == Decimal("90000")             # 20.000 + 50.000 + 20.000
    assert t["en_riesgo"] == Decimal("70000")           # amarilla + rojo
    assert [c["cliente_id"] for c in p["pasaron_a_rojo"]] == [rojo]
    assert [c["cliente_id"] for c in p["salieron_de_rojo"]] == [sale]
    assert p["salieron_de_rojo"][0]["ahora"] == "pagó todo"
    assert p["zonas"][0]["rojo"] == 1
    assert p["cobradores"][0]["en_riesgo"] == Decimal("70000")


def test_la_tendencia_compara_lo_cobrado_con_lo_que_vencia(db):
    _cliente(db, "Semana", [1, 2], pagadas={0}, cobros=[(0, 1)])
    t = panel(db, 1, HOY)["tendencia"]
    assert len(t) == 8
    ultima = [s for s in t if s["vencia"] > 0]
    assert ultima and sum(s["cobrado"] for s in ultima) == Decimal("10000")


def test_el_panel_es_solo_del_admin():
    from pathlib import Path
    fin = Path("app/routers/finanzas.py").read_text(encoding="utf-8")
    bloque = fin.split('@router.get("/mora/datos")')[1][:400]
    assert "_admin(request, db)" in bloque


def test_control_de_visitas_separa_puerta_mismo_sitio_y_sin_gps(db):
    """Cuatro clientes cobrados desde el mismo punto = el sitio del cobrador;
    uno en su puerta; uno sin GPS."""
    from app.utils.mora import control_de_visitas
    ids = [_cliente(db, f"Cli{i}", [1]) for i in range(6)]
    oficina = (6.3179, -75.5579)
    for i, cid in enumerate(ids):
        cu = db.query(Cuota).join(Prestamo).filter(Prestamo.cliente_id == cid).first()
        lat, lng = ((oficina[0] + i * 0.00002, oficina[1]) if i < 4
                    else (6.25, -75.59) if i == 4 else (None, None))
        db.add(Cobro(empresa_id=1, cuota_id=cu.id, prestamo_id=cu.prestamo_id, cliente_id=cid,
                     zona_id=1, valor_cobrado=Decimal("1000"), fecha=HOY, usuario_id=1,
                     lat_cobro=lat, lng_cobro=lng))
    db.commit()
    v = control_de_visitas(db, 1, HOY, HOY)[0]
    assert (v["total"], v["mismo_sitio"], v["en_puerta"], v["sin_gps"]) == (6, 4, 1, 1)
