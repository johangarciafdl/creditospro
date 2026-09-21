"""El detalle de una cuota no puede contradecir a su propia fila.

Un cobro se anota entero en la cuota donde se recibio, pero si supera su
saldo el excedente se aplica a las siguientes. Sin distinguir lo *recibido*
de lo *aplicado*, el detalle mentia por los dos lados: la cuota de origen
mostraba "pagos: 80.000" aunque solo valia 60.000, y la de destino decia
"sin pagos registrados" mientras su fila anunciaba que ya solo faltaban
40.000 de 60.000. Dos pantallas de la misma cuota decian cosas distintas.

Se comprueba la aritmetica que sostiene el texto, que es lo que puede
romperse al cambiar el reparto.
"""
import datetime
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base, Cobro, Cuota


@pytest.fixture()
def db():
    motor = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(motor)
    s = sessionmaker(bind=motor)()
    yield s
    s.close()


def _cuota(db, numero, valor, pagado="0"):
    c = Cuota(empresa_id=1, prestamo_id=1, numero=numero, valor=Decimal(str(valor)),
              valor_pagado=Decimal(str(pagado)), estado="Pendiente",
              fecha_vencimiento=datetime.date(2026, 10, numero))
    db.add(c); db.flush()
    return c


def _cobro(db, cuota, valor):
    db.add(Cobro(empresa_id=1, cuota_id=cuota.id, prestamo_id=1, cliente_id=1,
                 zona_id=1, valor_cobrado=Decimal(str(valor)),
                 fecha=datetime.date(2026, 9, 21)))
    db.flush()


def _recibido(db, cuota) -> Decimal:
    """Lo que el cobrador recibio anotado en esta cuota."""
    return sum((c.valor_cobrado for c in
                db.query(Cobro).filter(Cobro.cuota_id == cuota.id).all()),
               Decimal("0"))


def test_la_cuota_de_origen_distingue_lo_recibido_de_lo_aplicado(db):
    """Recibio 80.000 pero solo 60.000 se quedaron aqui."""
    c1 = _cuota(db, 1, 60000, 60000)   # saldada
    _cuota(db, 2, 60000, 20000)        # recibio el excedente
    _cobro(db, c1, 80000)
    db.commit()

    recibido, aplicado = _recibido(db, c1), Decimal(str(c1.valor_pagado))
    assert recibido == 80000
    assert aplicado == 60000
    assert recibido > aplicado, "hay que avisar de que parte paso a otras cuotas"
    assert recibido - aplicado == 20000


def test_la_cuota_de_destino_tiene_dinero_sin_cobro_propio(db):
    """No se le puede decir 'sin pagos registrados' teniendo 20.000 abonados."""
    c2 = _cuota(db, 2, 60000, 20000)
    db.commit()

    assert _recibido(db, c2) == 0, "el cobro se anoto en la cuota anterior"
    assert Decimal(str(c2.valor_pagado)) > 0, "pero si tiene dinero aplicado"


def test_una_cuota_pagada_de_golpe_no_avisa_de_ningun_reparto(db):
    """Si recibido y aplicado coinciden, no hay nada que explicar."""
    c = _cuota(db, 1, 60000, 60000)
    _cobro(db, c, 60000)
    db.commit()
    assert _recibido(db, c) == Decimal(str(c.valor_pagado))


def test_varios_abonos_suman_lo_aplicado(db):
    """Tres abonos parciales en la misma cuota: ni sobra ni falta."""
    c = _cuota(db, 1, 60000, 45000)
    for v in (20000, 15000, 10000):
        _cobro(db, c, v)
    db.commit()
    assert _recibido(db, c) == 45000 == Decimal(str(c.valor_pagado))


def test_una_cuota_puede_recibir_abono_propio_y_excedente_ajeno(db):
    """El reparto solo va hacia adelante, asi que esto es posible."""
    c = _cuota(db, 2, 60000, 50000)   # 30.000 propios + 20.000 heredados
    _cobro(db, c, 30000)
    db.commit()
    recibido, aplicado = _recibido(db, c), Decimal(str(c.valor_pagado))
    assert aplicado > recibido, "tiene mas aplicado que recibido en su propio nombre"
