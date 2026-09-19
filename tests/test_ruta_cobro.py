"""La ruta semanal decide que zonas ve un cobrador cada dia.

Se prueba contra get_allowed_zone_ids porque es el unico punto por el que
pasan todos los modulos (cobros, clientes, prestamos, reportes): si la regla
vale ahi, vale en toda la aplicacion.
"""
import datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base, Empresa, RutaCobro, Usuario, Zona
from app.utils import zone_permissions as zp


@pytest.fixture()
def db():
    motor = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(motor)
    sesion = sessionmaker(bind=motor)()
    yield sesion
    sesion.close()


@pytest.fixture()
def escenario(db):
    empresa = Empresa(id=1, nombre="ElRusso")
    db.add(empresa)
    zonas = {}
    for zid, nombre in [(1, "Bello"), (2, "Copacabana"), (3, "Niquia"), (4, "Castilla")]:
        z = Zona(id=zid, empresa_id=1, codigo=f"Z{zid}", nombre=nombre, activa=True)
        zonas[nombre] = z
        db.add(z)
    cobrador = Usuario(id=10, empresa_id=1, username="cob", nombre="Cobrador",
                       password_hash="x", rol="cobrador", activo=True)
    cobrador.zonas_asignadas = [zonas["Bello"], zonas["Copacabana"], zonas["Niquia"]]
    db.add(cobrador)
    db.commit()
    return db, cobrador, zonas


def _ruta(db, usuario_id, dia, zona_ids):
    for zid in zona_ids:
        db.add(RutaCobro(empresa_id=1, usuario_id=usuario_id, zona_id=zid, dia_semana=dia))
    db.commit()


def test_sin_ruta_configurada_ve_todas_sus_zonas(escenario, monkeypatch):
    """Activar la funcion no puede dejar sin trabajo a los cobradores que ya existian."""
    db, cobrador, _ = escenario
    monkeypatch.setattr(zp, "dia_semana_local", lambda: 0)
    assert sorted(zp.get_allowed_zone_ids(db, cobrador)) == [1, 2, 3]


def test_con_ruta_solo_ve_las_zonas_del_dia(escenario, monkeypatch):
    db, cobrador, _ = escenario
    _ruta(db, 10, 0, [1])        # lunes: Bello
    _ruta(db, 10, 1, [2])        # martes: Copacabana

    monkeypatch.setattr(zp, "dia_semana_local", lambda: 0)
    cobrador._ruta_hoy_cache = None
    assert zp.get_allowed_zone_ids(db, cobrador) == [1]

    monkeypatch.setattr(zp, "dia_semana_local", lambda: 1)
    cobrador._ruta_hoy_cache = None
    assert zp.get_allowed_zone_ids(db, cobrador) == [2]


def test_dia_sin_zonas_en_la_ruta_no_habilita_ninguna(escenario, monkeypatch):
    db, cobrador, _ = escenario
    _ruta(db, 10, 0, [1])
    monkeypatch.setattr(zp, "dia_semana_local", lambda: 6)   # domingo
    cobrador._ruta_hoy_cache = None
    assert zp.get_allowed_zone_ids(db, cobrador) == []


def test_la_ruta_nunca_amplia_permisos(escenario, monkeypatch):
    """Si le quitan una zona al cobrador, la ruta no puede devolversela."""
    db, cobrador, _ = escenario
    _ruta(db, 10, 0, [1, 4])     # Castilla (4) NO esta asignada al cobrador
    monkeypatch.setattr(zp, "dia_semana_local", lambda: 0)
    cobrador._ruta_hoy_cache = None
    assert zp.get_allowed_zone_ids(db, cobrador) == [1]


def test_el_administrador_no_queda_restringido(escenario, monkeypatch):
    db, _, _ = escenario
    admin = Usuario(id=11, empresa_id=1, username="adm", nombre="Admin",
                    password_hash="x", rol="admin", activo=True)
    db.add(admin); db.commit()
    _ruta(db, 11, 0, [1])
    monkeypatch.setattr(zp, "dia_semana_local", lambda: 3)
    assert zp.get_allowed_zone_ids(db, admin) is None


def test_la_fecha_es_la_de_colombia_no_la_del_servidor():
    """A las 19:00 de Colombia el servidor en UTC ya cree que es manana."""
    from app.database import hoy_local
    from zoneinfo import ZoneInfo

    esperado = datetime.datetime.now(ZoneInfo("America/Bogota")).date()
    assert hoy_local() == esperado


def test_el_limite_de_zonas_por_dia_esta_definido():
    assert zp.MAX_ZONAS_POR_DIA == 3
    assert len(zp.DIAS_SEMANA) == 7
