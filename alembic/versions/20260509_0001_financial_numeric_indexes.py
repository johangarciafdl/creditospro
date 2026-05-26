"""financial numeric columns and indexes

Revision ID: 20260509_0001
Revises:
Create Date: 2026-05-09
"""
from alembic import op
import sqlalchemy as sa

revision = "20260509_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    money = sa.Numeric(12, 2)
    pct = sa.Numeric(5, 2)
    for table, column, typ in [
        ("prestamos", "capital", money),
        ("prestamos", "tasa_interes", pct),
        ("prestamos", "interes_total", money),
        ("prestamos", "total_pagar", money),
        ("prestamos", "valor_cuota", money),
        ("cuotas", "valor", money),
        ("cuotas", "valor_pagado", money),
        ("cobros", "valor_cobrado", money),
        ("configuracion", "tasa_default", pct),
    ]:
        op.alter_column(table, column, type_=typ, postgresql_using=f"{column}::numeric")

    op.create_index("ix_prestamos_empresa_cliente", "prestamos", ["empresa_id", "cliente_id"], if_not_exists=True)
    op.create_index("ix_prestamos_empresa_zona_estado", "prestamos", ["empresa_id", "zona_id", "estado"], if_not_exists=True)
    op.create_index("ix_cuotas_empresa_prestamo_estado", "cuotas", ["empresa_id", "prestamo_id", "estado"], if_not_exists=True)
    op.create_index("ix_cuotas_empresa_estado_vencimiento", "cuotas", ["empresa_id", "estado", "fecha_vencimiento"], if_not_exists=True)
    op.create_index("ix_cobros_empresa_fecha", "cobros", ["empresa_id", "fecha"], if_not_exists=True)
    op.create_index("ix_cobros_empresa_cliente", "cobros", ["empresa_id", "cliente_id"], if_not_exists=True)
    op.create_index("ix_cobros_empresa_prestamo", "cobros", ["empresa_id", "prestamo_id"], if_not_exists=True)


def downgrade():
    op.drop_index("ix_cobros_empresa_prestamo", table_name="cobros", if_exists=True)
    op.drop_index("ix_cobros_empresa_cliente", table_name="cobros", if_exists=True)
    op.drop_index("ix_cobros_empresa_fecha", table_name="cobros", if_exists=True)
    op.drop_index("ix_cuotas_empresa_estado_vencimiento", table_name="cuotas", if_exists=True)
    op.drop_index("ix_cuotas_empresa_prestamo_estado", table_name="cuotas", if_exists=True)
    op.drop_index("ix_prestamos_empresa_zona_estado", table_name="prestamos", if_exists=True)
    op.drop_index("ix_prestamos_empresa_cliente", table_name="prestamos", if_exists=True)

    for table, column in [
        ("prestamos", "capital"),
        ("prestamos", "tasa_interes"),
        ("prestamos", "interes_total"),
        ("prestamos", "total_pagar"),
        ("prestamos", "valor_cuota"),
        ("cuotas", "valor"),
        ("cuotas", "valor_pagado"),
        ("cobros", "valor_cobrado"),
        ("configuracion", "tasa_default"),
    ]:
        op.alter_column(table, column, type_=sa.Float(), postgresql_using=f"{column}::double precision")
