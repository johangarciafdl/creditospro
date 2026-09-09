"""add Empresa.overrides (JSON) for per-empresa plan feature overrides

Part of the plan-based feature-gating system (app/utils/plan_limits.py):
Empresa.plan (already existed, unused until now) sets the default limits
per tier (basico/medio/alto); this new column lets the platform owner
grant or revoke one specific feature for one specific empresa without
changing its whole plan (e.g. let a basico client trial WhatsApp before
upgrading).

Revision ID: 20260909_0009
Revises: 20260908_0008
Create Date: 2026-09-09
"""
from alembic import op
import sqlalchemy as sa

revision = "20260909_0009"
down_revision = "20260908_0008"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("empresas", sa.Column("overrides", sa.JSON(), nullable=True))


def downgrade():
    op.drop_column("empresas", "overrides")
