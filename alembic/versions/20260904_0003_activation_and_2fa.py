"""company activation keys and user two-factor authentication

Revision ID: 20260904_0003
Revises: 20260509_0002
Create Date: 2026-09-04
"""
from alembic import op
import sqlalchemy as sa

revision = "20260904_0003"
down_revision = "20260509_0002"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("empresas", sa.Column("activation_key_hash", sa.String(length=64), nullable=True))
    op.add_column("empresas", sa.Column("activation_key_hint", sa.String(length=24), nullable=True))
    op.add_column(
        "empresas",
        sa.Column("activation_enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.create_index("ix_empresas_activation_key_hash", "empresas", ["activation_key_hash"], unique=True)

    op.add_column(
        "usuarios",
        sa.Column("two_factor_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column("usuarios", sa.Column("two_factor_secret", sa.Text(), nullable=True))
    op.add_column("usuarios", sa.Column("two_factor_backup_hashes", sa.Text(), nullable=True))


def downgrade():
    op.drop_column("usuarios", "two_factor_backup_hashes")
    op.drop_column("usuarios", "two_factor_secret")
    op.drop_column("usuarios", "two_factor_enabled")
    op.drop_index("ix_empresas_activation_key_hash", table_name="empresas")
    op.drop_column("empresas", "activation_enabled")
    op.drop_column("empresas", "activation_key_hint")
    op.drop_column("empresas", "activation_key_hash")
