"""Toda tabla de negocio nueva debe aislarse como sus hermanas.

Cuando se anadio rutas_cobro se crearon la tabla, sus claves foraneas y sus
indices, pero no el RLS ni la politica que tenian las catorce anteriores. La
funcionalidad paso todas las pruebas, incluidas las de aislamiento entre
empresas, porque el filtro por empresa_id del codigo de la aplicacion si
estaba y era el que respondia. La segunda capa -- la que existe justamente
para cuando ese filtro se olvide en algun camino futuro -- faltaba, y ninguna
prueba funcional podia notarlo: mientras la primera funcione, su ausencia y
su presencia son indistinguibles desde fuera.

Por eso esta comprobacion es estructural: compara los modelos con el fichero
de politicas, sin necesidad de una base de datos Postgres viva.
"""
import pathlib
import re

from app.database import Base

RAIZ = pathlib.Path(__file__).resolve().parent.parent
POLITICAS = RAIZ / "rls_policies.sql"


def _tablas_de_negocio() -> set[str]:
    """Las que llevan empresa_id: son datos de un inquilino concreto."""
    return {
        tabla.name
        for tabla in Base.metadata.tables.values()
        if "empresa_id" in tabla.columns
    }


def test_toda_tabla_con_empresa_id_tiene_rls_y_politica():
    sql = POLITICAS.read_text(encoding="utf-8")
    con_rls = set(re.findall(r"ALTER TABLE (\w+) ENABLE ROW LEVEL SECURITY", sql))
    con_politica = set(re.findall(r"CREATE POLICY \w+ ON (\w+)", sql))

    faltan_rls = sorted(_tablas_de_negocio() - con_rls)
    faltan_politica = sorted(_tablas_de_negocio() - con_politica)

    assert not faltan_rls, (
        "Sin ENABLE ROW LEVEL SECURITY en rls_policies.sql: " + ", ".join(faltan_rls)
    )
    assert not faltan_politica, (
        "Sin politica de aislamiento en rls_policies.sql: " + ", ".join(faltan_politica)
    )


def test_la_tabla_empresas_se_aisla_por_su_propio_id():
    """empresas no tiene empresa_id: su clave primaria es el inquilino."""
    sql = POLITICAS.read_text(encoding="utf-8")
    assert "ALTER TABLE empresas ENABLE ROW LEVEL SECURITY" in sql
    assert re.search(r"CREATE POLICY \w+ ON empresas\s+USING \(id = ", sql)


def test_ninguna_politica_sobra():
    """Una politica sobre una tabla que ya no existe enmascara un olvido."""
    sql = POLITICAS.read_text(encoding="utf-8")
    nombradas = set(re.findall(r"CREATE POLICY \w+ ON (\w+)", sql))
    desconocidas = sorted(nombradas - set(Base.metadata.tables))
    assert not desconocidas, "Politicas sobre tablas inexistentes: " + ", ".join(desconocidas)
