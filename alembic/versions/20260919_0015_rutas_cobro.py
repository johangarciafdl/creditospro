"""Ruta semanal de cobro por cobrador

Cada fila dice: este cobrador, este dia de la semana, esta zona. Sin filas
para un usuario, ese usuario sigue cobrando en todas sus zonas asignadas
(comportamiento anterior); en cuanto el administrador le arma la ruta, pasa
a regir la ruta.

Revision ID: 20260919_0014
Revises: 20260914_0014
"""
from alembic import op
import sqlalchemy as sa

revision = "20260919_0015"
down_revision = "20260914_0014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "rutas_cobro",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("empresa_id", sa.Integer(), nullable=False),
        sa.Column("usuario_id", sa.Integer(), nullable=False),
        sa.Column("zona_id", sa.Integer(), nullable=False),
        sa.Column("dia_semana", sa.Integer(), nullable=False),
        sa.Column("creado", sa.DateTime(), server_default=sa.func.now(), nullable=True),
        sa.ForeignKeyConstraint(["empresa_id"], ["empresas.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["usuario_id"], ["usuarios.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["zona_id"], ["zonas.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("usuario_id", "dia_semana", "zona_id", name="uq_ruta_usuario_dia_zona"),
        sa.CheckConstraint("dia_semana >= 0 AND dia_semana <= 6", name="ck_ruta_dia_semana"),
    )
    op.create_index("ix_rutas_cobro_id", "rutas_cobro", ["id"])
    # Consulta de cada peticion de un cobrador: "mis zonas de hoy".
    op.create_index("ix_rutas_cobro_usuario_dia", "rutas_cobro", ["usuario_id", "dia_semana"])
    # Postgres no indexa las claves foraneas solo: sin estos, borrar una zona
    # o una empresa obliga a recorrer la tabla entera para el CASCADE.
    op.create_index("ix_rutas_cobro_empresa_id", "rutas_cobro", ["empresa_id"])
    op.create_index("ix_rutas_cobro_zona_id", "rutas_cobro", ["zona_id"])


def downgrade() -> None:
    op.drop_index("ix_rutas_cobro_zona_id", table_name="rutas_cobro")
    op.drop_index("ix_rutas_cobro_empresa_id", table_name="rutas_cobro")
    op.drop_index("ix_rutas_cobro_usuario_dia", table_name="rutas_cobro")
    op.drop_index("ix_rutas_cobro_id", table_name="rutas_cobro")
    op.drop_table("rutas_cobro")
