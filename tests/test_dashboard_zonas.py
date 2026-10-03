"""El dashboard del admin: un tablero por zona, nunca mezcladas.

Zona Norte: un prestamo de 100.000 al 20 % (120.000) del que se pagaron
60.000 -> faltan 60.000 = 50.000 de capital + 10.000 de interes.
Zona Sur: uno de 300.000 al 20 % (360.000) sin pagar -> 300.000 + 60.000.
"""
import datetime
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import (Base, Cliente, Cobro, Cuota, Empresa, NoPago, Prestamo, Zona,
                          hoy_local)
from app.utils.tablero import tablero_zona

HOY = hoy_local()


@pytest.fixture()
def db():
    motor = create_engine("sqlite://")
    Base.metadata.create_all(motor)
    s = sessionmaker(bind=motor)()
    s.add(Empresa(id=1, nombre="TableroSA"))
    s.add_all([Zona(id=1, empresa_id=1, codigo="N", nombre="Norte", activa=True),
               Zona(id=2, empresa_id=1, codigo="S", nombre="Sur", activa=True)])
    s.commit()
    yield s
    s.close()


def _prestamo(s, zona, capital, total, cuotas, pagadas, vencidas_hace=None, renovacion=False,
              desembolso=None):
    c = Cliente(empresa_id=1, cedula=f"{zona}{capital}", nombre=f"Cliente {zona} {capital}",
                telefono="3000000000", zona_id=zona, activo=True)
    s.add(c); s.flush()
    p = Prestamo(empresa_id=1, cliente_id=c.id, zona_id=zona, capital=Decimal(capital),
                 tasa_interes=Decimal("20"), total_pagar=Decimal(total), num_cuotas=cuotas,
                 valor_cuota=Decimal(total) / cuotas, estado="Activo",
                 fecha_inicio=HOY - datetime.timedelta(days=30), fecha_fin=HOY,
                 fecha_desembolso=desembolso or HOY - datetime.timedelta(days=30),
                 observaciones="Renovacion del prestamo #9: x" if renovacion else None)
    s.add(p); s.flush()
    valor = Decimal(total) / cuotas
    for n in range(cuotas):
        pagada = n < pagadas
        dias = (vencidas_hace or [])[n] if vencidas_hace else -1 - n
        s.add(Cuota(empresa_id=1, prestamo_id=p.id, numero=n + 1, valor=valor,
                    valor_pagado=valor if pagada else Decimal("0"),
                    estado="Pagada" if pagada else "Pendiente",
                    fecha_vencimiento=HOY - datetime.timedelta(days=dias)))
    s.commit()
    return c, p


def test_capital_e_intereses_por_zona_sin_mezclar(db):
    _prestamo(db, 1, "100000", "120000", 2, pagadas=1)
    _prestamo(db, 2, "300000", "360000", 3, pagadas=0)
    norte = tablero_zona(db, 1, 1, HOY)
    sur = tablero_zona(db, 1, 2, HOY)
    assert (norte["capital_pendiente"], norte["interes_pendiente"]) == (Decimal("50000"), Decimal("10000"))
    assert (sur["capital_pendiente"], sur["interes_pendiente"]) == (Decimal("300000"), Decimal("60000"))


def test_lo_de_hoy_y_el_movimiento_del_dia(db):
    c, p = _prestamo(db, 1, "100000", "120000", 2, pagadas=0, vencidas_hace=[5, 1])
    cu = db.query(Cuota).filter(Cuota.prestamo_id == p.id).first()
    db.add(Cobro(empresa_id=1, cuota_id=cu.id, prestamo_id=p.id, cliente_id=c.id, zona_id=1,
                 valor_cobrado=Decimal("20000"), fecha=HOY))
    db.add(NoPago(empresa_id=1, cuota_id=cu.id, prestamo_id=p.id, cliente_id=c.id, zona_id=1,
                  fecha=HOY))
    _prestamo(db, 1, "200000", "240000", 4, pagadas=0, desembolso=HOY)              # nuevo
    _prestamo(db, 1, "150000", "180000", 3, pagadas=0, desembolso=HOY, renovacion=True)
    _prestamo(db, 2, "999000", "999000", 1, pagadas=0, desembolso=HOY)              # otra zona
    db.commit()
    t = tablero_zona(db, 1, 1, HOY)
    assert t["hoy"]["cobrado"] == Decimal("20000") and t["hoy"]["num_cobros"] == 1
    assert t["hoy"]["prestado"] == Decimal("350000")      # nuevo + renovacion, no la otra zona
    assert t["hoy"]["no_pagaron"] == 1
    assert t["movimiento"]["nuevos"] == 1 and t["movimiento"]["renovaciones"] == 1
    assert t["cartera"]["amarillos"] == 1                   # 2 cuotas atrasadas
    assert t["ultimos_cobros"][0]["valor"] == Decimal("20000")


def test_la_pantalla_tiene_un_boton_por_zona_y_se_refresca_sola():
    html = Path("templates/dashboard_zonas.html").read_text(encoding="utf-8")
    assert 'class="zona-tab"' in html and "setInterval" in html and "document.hidden" in html
    ruta = Path("app/routers/dashboard.py").read_text(encoding="utf-8")
    bloque = ruta.split('@router.get("/dashboard/zona/{zona_id}")')[1][:900]
    assert "es_admin(user)" in bloque and "Zona.empresa_id == user.empresa_id" in bloque
