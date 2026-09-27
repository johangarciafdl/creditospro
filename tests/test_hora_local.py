"""Toda hora se guarda en UTC y se le enseña a la persona en la de Colombia.

Reportado en produccion: un prestamo cobrado a las 8:36 de la noche salia
registrado a la 1:35. La base (Postgres en Supabase) trabaja en UTC, cinco
horas por delante de Colombia, y las pantallas enseñaban esa hora tal cual.

Habia ademas un segundo problema debajo: parte de las horas se escribian con
datetime.now(), que da UTC en el servidor pero la hora de Colombia en el
portatil de quien desarrolla. La misma columna quedaba con dos escalas segun
donde corriera el codigo, y ninguna conversion al mostrarla podia acertar
con las dos. Ahora se escribe siempre en UTC y se muestra siempre en la hora
del negocio.
"""
import datetime
import pathlib
import re

RAIZ = pathlib.Path(__file__).resolve().parent.parent


def test_la_hora_utc_se_enseña_en_la_de_colombia():
    from app.database import a_hora_local
    # 01:36 UTC del 27 = 20:36 del 26 en Bogota (UTC-5, sin horario de verano).
    utc = datetime.datetime(2026, 9, 27, 1, 36)
    local = a_hora_local(utc)
    assert local == datetime.datetime(2026, 9, 26, 20, 36), local
    assert a_hora_local(None) is None


def test_lo_que_se_guarda_esta_en_utc_en_cualquier_maquina():
    """En el servidor datetime.now() ya es UTC; en un portatil de Colombia
    no. ahora_utc tiene que dar lo mismo en los dos."""
    from app.database import ahora_utc
    esperado = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)
    assert abs((ahora_utc() - esperado).total_seconds()) < 2
    assert ahora_utc().tzinfo is None, "las columnas son sin zona"


def test_el_corte_del_dia_esta_en_la_misma_escala_que_lo_guardado():
    """Medianoche de Colombia = 05:00 UTC. Si el corte estuviera en otra
    escala, "¿paso hoy?" partiria la jornada en dos."""
    from app.database import hoy_local, inicio_dia_negocio
    corte = inicio_dia_negocio()
    assert corte.tzinfo is None
    assert corte == datetime.datetime.combine(hoy_local(), datetime.time(5, 0)), corte


def test_nadie_escribe_una_hora_con_la_de_la_maquina():
    """datetime.now() sin zona es la hora de la maquina: UTC en el servidor,
    la de Colombia en desarrollo. Una sola de esas en una columna de hora
    basta para que la misma columna tenga dos escalas."""
    culpables = []
    for f in (RAIZ / "app").rglob("*.py"):
        for n, linea in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
            if re.search(r"(=|hora=)\s*datetime\.datetime\.now\(\)", linea):
                culpables.append(f"{f.relative_to(RAIZ)}:{n}: {linea.strip()[:80]}")
    assert not culpables, "horas guardadas con la de la maquina:\n  " + "\n  ".join(culpables)


def test_las_pantallas_no_enseñan_una_hora_sin_convertir():
    """Cualquier .strftime con hora sobre una columna guardada tiene que pasar
    antes por a_hora_local (o el filtro hora_local en las plantillas)."""
    sospechosos = []
    for f in list((RAIZ / "app").rglob("*.py")) + list((RAIZ / "templates").rglob("*.html")):
        texto = f.read_text(encoding="utf-8")
        for n, linea in enumerate(texto.splitlines(), 1):
            if "%H:%M" not in linea:
                continue
            if any(ok in linea for ok in ("a_hora_local(", "hora_local", "ahora_local()",
                                          "time.strftime")):
                continue
            sospechosos.append(f"{f.relative_to(RAIZ)}:{n}: {linea.strip()[:90]}")
    assert not sospechosos, "horas que se enseñan en UTC:\n  " + "\n  ".join(sospechosos)
