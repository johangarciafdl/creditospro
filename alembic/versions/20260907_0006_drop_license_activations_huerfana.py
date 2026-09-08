"""drop orphaned license_activations table

Schema drift found during audit: a leftover table from an earlier version of
the licensing system, separate from `licencias_activadas` (the one actually
used by app/database.py's LicenciaActivada model). Confirmed empty (0 rows)
and never referenced anywhere in the codebase before dropping.

Revision ID: 20260907_0006
Revises: 20260907_0005
Create Date: 2026-09-07
"""
from alembic import op
import sqlalchemy as sa

revision = "20260907_0006"
down_revision = "20260907_0005"
branch_labels = None
depends_on = None


def upgrade():
    op.drop_table("license_activations")


def downgrade():
    op.create_table(
        "license_activations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("empresa_id", sa.Integer(), nullable=True),
        sa.Column("machine_id", sa.String(length=64), nullable=True),
        sa.Column("licencia", sa.Text(), nullable=True),
        sa.Column("activa", sa.Boolean(), nullable=True),
        sa.Column("vence", sa.Date(), nullable=True),
        sa.Column("creado", sa.DateTime(), nullable=True),
    )
