"""add missing indexes: cuotas.prestamo_id, clientes(empresa_id, zona_id)

Both queried on hot paths without a supporting index:
- cobros.py counts pending cuotas by prestamo_id alone (no empresa_id) on
  every payment registration; the only existing index on prestamo_id is the
  composite (empresa_id, prestamo_id, estado), unusable without a leading
  empresa_id predicate.
- Cliente.zona_id is filtered in 8+ call sites, always combined with
  empresa_id, but only empresa_id alone was indexed.

Revision ID: 20260907_0005
Revises: 20260907_0004
Create Date: 2026-09-07
"""
from alembic import op

revision = "20260907_0005"
down_revision = "20260907_0004"
branch_labels = None
depends_on = None


def upgrade():
    op.create_index("ix_cuotas_prestamo_id", "cuotas", ["prestamo_id"], if_not_exists=True)
    op.create_index("ix_clientes_empresa_zona", "clientes", ["empresa_id", "zona_id"], if_not_exists=True)


def downgrade():
    op.drop_index("ix_clientes_empresa_zona", table_name="clientes", if_exists=True)
    op.drop_index("ix_cuotas_prestamo_id", table_name="cuotas", if_exists=True)
