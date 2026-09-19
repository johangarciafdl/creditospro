"""Registro de visitas en las que el cliente no pago

Sin esta tabla, un dia sin cobro es indistinguible de un dia sin visita.
Cada fila deja constancia de que se fue a cobrar y no se pudo, con la fecha
y el motivo, para que despues se vea "se debio pagar el X" junto a "se pago
el Y" o "no pago el X".

Revision ID: 20260919_0016
Revises: 20260919_0015
"""
from alembic import op
import sqlalchemy as sa

revision = "20260919_0016"
down_revision = "20260919_0015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "no_pagos",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("empresa_id", sa.Integer(), nullable=False),
        sa.Column("cuota_id", sa.Integer(), nullable=False),
        sa.Column("prestamo_id", sa.Integer(), nullable=False),
        sa.Column("cliente_id", sa.Integer(), nullable=False),
        sa.Column("zona_id", sa.Integer(), nullable=True),
        sa.Column("fecha", sa.Date(), nullable=False),
        sa.Column("motivo", sa.String(length=300), nullable=True),
        sa.Column("usuario_id", sa.Integer(), nullable=True),
        sa.Column("registrado_por", sa.String(length=200), nullable=True),
        sa.Column("creado", sa.DateTime(), server_default=sa.func.now(), nullable=True),
        sa.ForeignKeyConstraint(["empresa_id"], ["empresas.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["cuota_id"], ["cuotas.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["prestamo_id"], ["prestamos.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["cliente_id"], ["clientes.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["zona_id"], ["zonas.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["usuario_id"], ["usuarios.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("cuota_id", "fecha", name="uq_no_pago_cuota_fecha"),
    )
    op.create_index("ix_no_pagos_id", "no_pagos", ["id"])
    # Postgres no indexa las claves foraneas solo: sin esto, cada CASCADE
    # recorre la tabla entera.
    for col in ("empresa_id", "cuota_id", "prestamo_id", "cliente_id", "zona_id", "usuario_id"):
        op.create_index("ix_no_pagos_" + col, "no_pagos", [col])
    # Consulta del panel: "las visitas fallidas de esta empresa hoy".
    op.create_index("ix_no_pagos_empresa_fecha", "no_pagos", ["empresa_id", "fecha"])


def downgrade() -> None:
    op.drop_index("ix_no_pagos_empresa_fecha", table_name="no_pagos")
    for col in ("usuario_id", "zona_id", "cliente_id", "prestamo_id", "cuota_id", "empresa_id"):
        op.drop_index("ix_no_pagos_" + col, table_name="no_pagos")
    op.drop_index("ix_no_pagos_id", table_name="no_pagos")
    op.drop_table("no_pagos")
