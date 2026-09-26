"""empresas.interfaz_cobrador: el interruptor de interfaz del cobrador

Cada empresa trabaja distinto: unas quieren que el cobrador entre a los
mismos modulos que el admin, y otras quieren una sola pantalla con la ruta
del dia y nada mas. Hasta ahora la unica forma de tener las dos cosas era
mantener dos versiones del software.

Todas las empresas que ya existen aterrizan en "completa", que es
exactamente lo que ven hoy: el despliegue no cambia nada hasta que un admin
mueva el interruptor a mano en su propia empresa.

Revision ID: 20260926_0020
Revises: 20260926_0019
"""
import sqlalchemy as sa
from alembic import op

revision = "20260926_0020"
down_revision = "20260926_0019"
branch_labels = None
depends_on = None


def upgrade():
    # server_default hace el relleno de las filas que ya existen: no hay un
    # UPDATE aparte que pueda quedarse a medias sobre una tabla con datos
    # reales. La columna nace NOT NULL con valor, no nullable-y-luego-arreglar.
    op.add_column(
        "empresas",
        sa.Column("interfaz_cobrador", sa.String(20),
                  nullable=False, server_default="completa"),
    )

    # La aplicacion ya normaliza cualquier valor raro a "completa", pero la
    # restriccion vive tambien en la base para que un script de mantenimiento
    # o una consulta a mano no puedan dejar una empresa con una interfaz que
    # no existe. Solo en Postgres: SQLite necesitaria recrear la tabla entera
    # para añadir un CHECK, y el desarrollo local no lo necesita.
    if op.get_bind().dialect.name == "postgresql":
        op.create_check_constraint(
            "ck_empresa_interfaz_cobrador", "empresas",
            "interfaz_cobrador IN ('completa', 'simple')",
        )


def downgrade():
    if op.get_bind().dialect.name == "postgresql":
        op.drop_constraint("ck_empresa_interfaz_cobrador", "empresas",
                           type_="check")
    op.drop_column("empresas", "interfaz_cobrador")
