"""El dinero se suma en Decimal, nunca mezclado con float.

La ficha de un cliente suma los saldos de todos sus prestamos. El saldo se
calculaba con `max(0.0, total - pagado)`, y ese `max` devuelve cosas de
distinto tipo segun el caso: el float 0.0 cuando el prestamo esta saldado
(porque empatan y `max` se queda con el primero) y un Decimal cuando queda
algo por pagar.

Mientras un cliente tuviera solo prestamos de una clase no pasaba nada. En
cuanto tuvo uno pagado y otro pendiente a la vez, la plantilla intento
sumarlos y la pagina entera murio con "unsupported operand type(s) for +:
'decimal.Decimal' and 'float'". Desde fuera se veia como un error al crear
el prestamo, porque el fallo aparecia al recargar la ficha justo despues.

El fallo llevaba ahi desde el primer despliegue y solo esperaba esa
combinacion.
"""
import datetime
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base, Cliente, Cuota, Empresa, Prestamo, Zona
from app.utils.money import money


@pytest.fixture()
def db():
    motor = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(motor)
    s = sessionmaker(bind=motor)()
    yield s
    s.close()


def _prestamo(db, cliente_id, zona_id, total, pagado_por_cuota):
    p = Prestamo(empresa_id=1, cliente_id=cliente_id, zona_id=zona_id,
                 capital=Decimal(str(total)), tasa_interes=Decimal("20"),
                 total_pagar=Decimal(str(total)), num_cuotas=len(pagado_por_cuota),
                 valor_cuota=Decimal(str(total)) / len(pagado_por_cuota),
                 estado="Activo", fecha_inicio=datetime.date(2026, 9, 1),
                 fecha_fin=datetime.date(2026, 12, 1))
    db.add(p); db.flush()
    cuota = Decimal(str(total)) / len(pagado_por_cuota)
    for i, pagado in enumerate(pagado_por_cuota, start=1):
        db.add(Cuota(empresa_id=1, prestamo_id=p.id, numero=i, valor=cuota,
                     valor_pagado=Decimal(str(pagado)),
                     estado="Pagada" if Decimal(str(pagado)) >= cuota else "Pendiente",
                     fecha_vencimiento=datetime.date(2026, 10, i)))
    db.flush()
    return p


def _saldos(db, cliente_id):
    """Reproduce el calculo del router para cada prestamo del cliente."""
    salida = []
    for p in db.query(Prestamo).filter(Prestamo.cliente_id == cliente_id).all():
        pagado = sum((money(c.valor_pagado) for c in p.cuotas), Decimal("0"))
        salida.append(max(Decimal("0"), money(p.total_pagar or p.capital or 0) - pagado))
    return salida


@pytest.fixture()
def cliente(db):
    db.add(Empresa(id=1, nombre="Prueba", activa=True))
    db.add(Zona(id=1, empresa_id=1, codigo="Z1", nombre="Centro"))
    c = Cliente(empresa_id=1, cedula="1", nombre="Gina", telefono="3000000000",
                zona_id=1, activo=True)
    db.add(c); db.flush()
    return c


def test_un_prestamo_pagado_y_otro_pendiente_se_pueden_sumar(db, cliente):
    """La combinacion exacta que tumbaba la ficha."""
    _prestamo(db, cliente.id, 1, 3600000, [900000, 900000, 900000, 900000])  # saldado
    _prestamo(db, cliente.id, 1, 240000, [0, 0, 0, 0])                        # pendiente
    db.commit()

    saldos = _saldos(db, cliente.id)
    assert all(isinstance(s, Decimal) for s in saldos), \
        "un saldo float y otro Decimal hacen imposible sumarlos"
    assert sum(saldos, Decimal("0")) == Decimal("240000")


def test_el_saldo_de_un_prestamo_saldado_es_decimal_cero(db, cliente):
    """Aqui es donde max(0.0, Decimal) colaba un float."""
    _prestamo(db, cliente.id, 1, 100000, [50000, 50000])
    db.commit()
    saldo = _saldos(db, cliente.id)[0]
    assert saldo == 0
    assert isinstance(saldo, Decimal), "debe ser Decimal, no float"


def test_la_base_impide_pagar_mas_que_la_cuota(db, cliente):
    """Descubierto al escribir estas pruebas: hay un guardarrail en el esquema.

    ck_cuota_pagado_no_excede evita que una cuota quede con mas pagado que
    su valor, asi que el saldo de un prestamo nunca puede salir negativo por
    esa via. El reparto de un sobrepago tiene que trocear el importe entre
    varias cuotas justamente por esto.
    """
    from sqlalchemy.exc import IntegrityError

    with pytest.raises(IntegrityError, match="ck_cuota_pagado_no_excede"):
        _prestamo(db, cliente.id, 1, 100000, [80000, 80000])  # 80.000 en una de 50.000
        db.commit()
    db.rollback()


def test_varios_prestamos_en_cualquier_estado_suman(db, cliente):
    _prestamo(db, cliente.id, 1, 100000, [100000])      # saldado
    _prestamo(db, cliente.id, 1, 200000, [50000])       # parcial
    _prestamo(db, cliente.id, 1, 300000, [0])           # sin tocar
    db.commit()
    saldos = _saldos(db, cliente.id)
    assert sum(saldos, Decimal("0")) == Decimal("450000")
    assert all(isinstance(s, Decimal) for s in saldos)


def test_la_ficha_no_mezcla_float_y_decimal_en_dinero():
    """max(0.0, ...) sobre dinero es la firma del fallo."""
    import pathlib
    import re
    ruta = pathlib.Path(__file__).resolve().parent.parent / "app" / "routers" / "clientes.py"
    culpables = [
        f"linea {n}: {l.strip()[:80]}"
        for n, l in enumerate(ruta.read_text(encoding="utf-8").splitlines(), 1)
        # Sin contar los comentarios, que es donde se explica el fallo.
        if re.search(r"max\(0\.0,|min\(0\.0,", l) and not l.strip().startswith("#")
    ]
    assert not culpables, (
        "Usa Decimal(\"0\") y no 0.0 al acotar dinero:" + chr(10) + "  "
        + (chr(10) + "  ").join(culpables)
    )


# ── La plantilla, renderizada de verdad ─────────────────────────────────────
# Las pruebas de arriba comprueban la aritmetica; esta comprueba que la
# pagina se genera. El fallo original no estaba en el calculo sino en
# sumarlos dentro de la plantilla, asi que hay que pasar por Jinja.

def _ficha(prestamos):
    """Renderiza el bloque de la ficha que suma los saldos de los prestamos."""
    from app.templates import templates
    plantilla = templates.env.from_string(
        "{% set total_prestado = namespace(v=0) %}"
        "{% set total_pagado_t = namespace(v=0) %}"
        "{% set total_saldo = namespace(v=0) %}"
        "{% for p in prestamos %}"
        "{% set total_prestado.v = total_prestado.v + p.capital %}"
        "{% set total_pagado_t.v = total_pagado_t.v + p.pagado %}"
        "{% set total_saldo.v = total_saldo.v + p.saldo %}"
        "{% endfor %}"
        "{{ total_prestado.v | cop }}|{{ total_pagado_t.v | cop }}|{{ total_saldo.v | cop }}"
    )
    return plantilla.render(prestamos=prestamos)


def _p(capital, pagado, saldo):
    return {"capital": Decimal(str(capital)), "pagado": Decimal(str(pagado)),
            "saldo": Decimal(str(saldo))}


def test_la_ficha_suma_prestamos_en_cualquier_estado():
    """Uno saldado y uno pendiente: la combinacion que tumbaba la pagina."""
    salida = _ficha([_p(3600000, 3600000, 0), _p(240000, 0, 240000)])
    assert salida == "$3.840.000|$3.600.000|$240.000"


def test_la_ficha_funciona_sin_ningun_prestamo():
    assert _ficha([]) == "$0|$0|$0"


def test_la_barra_de_progreso_sale_redondeada_y_acotada():
    """El |round iba pegado al 0 del else y nunca se aplicaba al calculo.

    Salia width:33.33333333333333333333333333% en el atributo de estilo, y
    con abonos de mas la barra pasaba del 100 y se salia de su carril.
    """
    from app.templates import templates
    t = templates.env.from_string(
        "{{ [100, ((p.pagado / p.capital * 100) | round | int)] | min if p.capital else 0 }}")
    assert t.render(p=_p(900000, 300000, 600000)) == "33"
    assert t.render(p=_p(3000000, 900000, 2100000)) == "30"
    assert t.render(p=_p(100000, 0, 100000)) == "0"
    assert t.render(p=_p(100000, 150000, 0)) == "100", "no puede pasar del 100"
    assert t.render(p={"capital": Decimal("0"), "pagado": Decimal("0")}) == "0", "sin dividir por cero"


def test_la_plantilla_no_deja_decimales_sueltos_en_un_atributo_de_estilo():
    """Un width con 28 decimales es la firma de un |round mal colocado."""
    import pathlib
    import re
    ruta = (pathlib.Path(__file__).resolve().parent.parent
            / "templates" / "cliente_detalle.html")
    culpables = [
        f"linea {n}: {l.strip()[:90]}"
        for n, l in enumerate(ruta.read_text(encoding="utf-8").splitlines(), 1)
        # Un calculo dentro de width: sin pasar por round
        if re.search(r"width:\{\{[^}]*[*/][^}]*\}\}", l) and "round" not in l
    ]
    assert not culpables, "Redondea antes de meterlo en el estilo:" + chr(10) + chr(10).join(culpables)
