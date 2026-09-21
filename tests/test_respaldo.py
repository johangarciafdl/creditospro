"""La copia de seguridad se hace sola y no se deja ninguna tabla.

Habia un script que hacia esto, pero habia que acordarse de ejecutarlo. Un
respaldo que depende de la memoria de una persona no es un respaldo, es una
intencion; y para un negocio de prestamos perder la base es perder el
negocio.

Lo que mas se vigila aqui es la cobertura: el script anterior llevaba la
lista de tablas escrita a mano y se habia quedado sin cinco de las nuevas
sin que nada lo avisara. Es el mismo patron de una tabla que se crea y no
hereda lo que tienen sus hermanas.
"""
import datetime
import gzip
import json
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base, Cliente, Empresa, Zona
from app.services import respaldo


@pytest.fixture()
def db():
    motor = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(motor)
    s = sessionmaker(bind=motor)()
    yield s
    s.close()


def test_el_respaldo_cubre_todas_las_tablas_del_modelo():
    """Una tabla nueva entra sola, sin tocar ninguna lista."""
    tablas = set(respaldo._nombre_tablas())
    del_modelo = set(Base.metadata.tables)
    assert tablas == del_modelo, "el respaldo y el modelo deben coincidir"
    # Las que el script antiguo se habia dejado fuera.
    for olvidada in ("rutas_cobro", "no_pagos", "archivos"):
        assert olvidada in tablas, f"{olvidada} quedaria sin respaldar"


def test_el_volcado_incluye_los_datos(db):
    e = Empresa(nombre="Prueba", activa=True); db.add(e); db.flush()
    z = Zona(empresa_id=e.id, codigo="Z1", nombre="Centro"); db.add(z); db.flush()
    db.add(Cliente(empresa_id=e.id, cedula="123", nombre="Ana", telefono="3001234567",
                   zona_id=z.id, activo=True))
    db.commit()

    contenido = respaldo.volcar(db)
    assert contenido["tablas"]["clientes"]["total"] == 1
    assert contenido["tablas"]["clientes"]["filas"][0]["nombre"] == "Ana"
    assert contenido["fecha_negocio"], "debe quedar la fecha del negocio"


def test_el_dinero_no_pierde_centavos_al_serializar():
    """Un Decimal convertido a float pierde precision; se guarda como texto."""
    assert respaldo._serializable(Decimal("933.36")) == "933.36"
    assert respaldo._serializable(Decimal("1777.76")) == "1777.76"
    assert isinstance(respaldo._serializable(Decimal("0.01")), str)


def test_las_fechas_se_guardan_en_formato_recuperable():
    d = datetime.date(2026, 9, 21)
    assert respaldo._serializable(d) == "2026-09-21"
    assert datetime.date.fromisoformat(respaldo._serializable(d)) == d


def test_los_bytes_no_inflan_la_copia():
    """Las imagenes viven en Storage; un blob antiguo no debe colarse entero."""
    salida = respaldo._serializable(b"x" * 5000)
    assert "5000 bytes omitidos" in salida
    assert len(salida) < 100


def test_lo_comprimido_se_vuelve_a_leer(db):
    db.add(Empresa(nombre="Prueba", activa=True)); db.commit()
    contenido = respaldo.volcar(db)
    datos = respaldo.comprimir(contenido)

    recuperado = json.loads(gzip.decompress(datos))
    assert recuperado["tablas"]["empresas"]["total"] == 1
    assert len(datos) < len(json.dumps(contenido, default=str)), "debe comprimir"


def test_sin_credenciales_avisa_en_vez_de_fingir(db, monkeypatch):
    """Guardar la copia en el contenedor es lo mismo que no tenerla."""
    monkeypatch.setattr(respaldo.supabase_storage, "disponible", lambda: False)
    with pytest.raises(RuntimeError, match="No hay donde guardar"):
        respaldo.crear_respaldo(db)


def test_no_se_puede_descargar_nada_fuera_del_bucket():
    """El nombre llega por la URL: no puede servir para salirse."""
    for malo in ("../secreto", "otra/carpeta/x.gz", "respaldo-/../x", "cualquier.json"):
        assert respaldo.descargar_respaldo(malo) is None


def test_solo_se_listan_los_respaldos(monkeypatch):
    """El prefix de Supabase filtra carpetas, no nombres: se filtra aqui."""
    monkeypatch.setattr(respaldo.supabase_storage, "listar", lambda **k: [
        {"name": "respaldo-2026-09-21_0300.json.gz", "created_at": "2026-09-21T03:00:00Z",
         "metadata": {"size": 1000}},
        {"name": "otra-cosa.txt", "created_at": "2026-09-21T03:00:00Z", "metadata": {}},
    ])
    nombres = [r["nombre"] for r in respaldo.listar_respaldos()]
    assert nombres == ["respaldo-2026-09-21_0300.json.gz"]


def test_se_purgan_las_copias_viejas_y_solo_esas(monkeypatch):
    ahora = datetime.datetime.now(datetime.timezone.utc)
    vieja = (ahora - datetime.timedelta(days=30)).isoformat().replace("+00:00", "Z")
    nueva = (ahora - datetime.timedelta(days=2)).isoformat().replace("+00:00", "Z")
    monkeypatch.setattr(respaldo.supabase_storage, "listar", lambda **k: [
        {"name": "respaldo-vieja.json.gz", "created_at": vieja, "metadata": {}},
        {"name": "respaldo-nueva.json.gz", "created_at": nueva, "metadata": {}},
    ])
    borradas = []
    monkeypatch.setattr(respaldo.supabase_storage, "borrar",
                        lambda nombre, bucket=None: borradas.append(nombre) or True)

    assert respaldo.purgar_antiguos(dias=14) == 1
    assert borradas == ["respaldo-vieja.json.gz"], "la reciente no se toca"
