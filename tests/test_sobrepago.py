"""Cuando el cliente paga de mas, el excedente pasa a las cuotas siguientes.

El caso del usuario: prestamo de 100 en dos cuotas de 50; en la primera el
cliente da 60. La cuota 1 queda saldada y la 2 pasa a deber 40. Antes el
sistema rechazaba el cobro entero con "El valor supera el saldo de la
cuota", asi que el cobrador anotaba 50 y los otros 10 no quedaban en ningun
lado.
"""
import datetime
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base, Cuota
from app.routers.cobros import aplicar_cobro_atomico
from app.utils.money import money


@pytest.fixture()
def db():
    motor = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(motor)
    s = sessionmaker(bind=motor)()
    yield s
    s.close()


def _cuotas(db, valores):
    """Crea las cuotas de un prestamo con los valores dados."""
    creadas = []
    for i, v in enumerate(valores, start=1):
        c = Cuota(empresa_id=1, prestamo_id=1, numero=i, valor=Decimal(str(v)),
                  valor_pagado=Decimal("0"), estado="Pendiente",
                  fecha_vencimiento=datetime.date(2026, 1, i))
        db.add(c)
        creadas.append(c)
    db.commit()
    return creadas


def _repartir(db, cuotas, desde, importe):
    """Reproduce el reparto del endpoint: primero la cuota, luego las siguientes."""
    restante = money(desde.valor) - money(desde.valor_pagado)
    reparto = [(desde, min(importe, restante))]
    excedente = importe - restante
    for siguiente in [c for c in cuotas if c.numero > desde.numero]:
        if excedente <= 0:
            break
        saldo = money(siguiente.valor) - money(siguiente.valor_pagado)
        if saldo <= 0:
            continue
        aplicar = min(excedente, saldo)
        reparto.append((siguiente, aplicar))
        excedente -= aplicar
    for cuota, valor in reparto:
        assert aplicar_cobro_atomico(db, cuota, valor)
    db.commit()
    return reparto, excedente


def test_el_caso_del_ejemplo_100_en_dos_cuotas(db):
    """Presta 100 en 2 cuotas de 50; paga 60 en la primera."""
    c1, c2 = _cuotas(db, [50, 50])
    _repartir(db, [c1, c2], c1, money(60))

    assert c1.valor_pagado == money(50) and c1.estado == "Pagada"
    assert c2.valor_pagado == money(10) and c2.estado == "Parcial"
    # A la segunda cuota ya solo le faltan 40.
    assert money(c2.valor) - money(c2.valor_pagado) == money(40)


def test_el_excedente_se_reparte_entre_varias_cuotas(db):
    c1, c2, c3 = _cuotas(db, [50, 50, 50])
    reparto, sobra = _repartir(db, [c1, c2, c3], c1, money(130))

    assert sobra == 0
    assert [(c.numero, float(v)) for c, v in reparto] == [(1, 50.0), (2, 50.0), (3, 30.0)]
    assert c1.estado == "Pagada" and c2.estado == "Pagada" and c3.estado == "Parcial"


def test_respeta_lo_ya_abonado_en_la_cuota_siguiente(db):
    c1, c2 = _cuotas(db, [50, 50])
    c2.valor_pagado = money(30)          # ya habia abonado 30 en la cuota 2
    c2.estado = "Parcial"
    db.commit()

    _repartir(db, [c1, c2], c1, money(70))

    assert c1.estado == "Pagada"
    # Solo le faltaban 20, no 50: no puede quedar pagada de mas.
    assert c2.valor_pagado == money(50) and c2.estado == "Pagada"


def test_pagar_mas_que_todo_el_prestamo_deja_excedente_sin_aplicar(db):
    """El endpoint rechaza este caso; aqui se comprueba que se detecta."""
    c1, c2 = _cuotas(db, [50, 50])
    _, sobra = _repartir(db, [c1, c2], c1, money(120))
    assert sobra == money(20), "debe sobrar lo que el prestamo ya no debe"


def test_nunca_se_paga_de_mas_en_ninguna_cuota(db):
    c1, c2, c3 = _cuotas(db, [50, 50, 50])
    _repartir(db, [c1, c2, c3], c1, money(150))
    for c in (c1, c2, c3):
        assert money(c.valor_pagado) <= money(c.valor)
        assert c.estado == "Pagada"


def test_la_fecha_del_pago_puede_no_ser_hoy(db):
    """Un cobro recibido el lunes y registrado el miercoles lleva la del lunes."""
    (c1,) = _cuotas(db, [50])
    lunes = datetime.date(2026, 1, 5)
    assert aplicar_cobro_atomico(db, c1, money(50), lunes)
    db.commit()
    assert c1.fecha_pago == lunes


def test_la_suma_de_lo_aplicado_es_exactamente_lo_recibido(db):
    """Ni un peso se pierde ni se inventa al repartir."""
    c1, c2, c3 = _cuotas(db, [33.33, 33.33, 33.34])
    recibido = money("75.10")
    reparto, sobra = _repartir(db, [c1, c2, c3], c1, recibido)
    aplicado = sum((v for _, v in reparto), money(0))
    assert aplicado + sobra == recibido
