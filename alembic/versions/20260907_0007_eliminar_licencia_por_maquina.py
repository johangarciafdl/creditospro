"""remove the machine-based licensing system (licencias_activadas)

Per user decision: CreditosPro keeps only the per-empresa commercial
activation key (Empresa.activation_key_hash, app/utils/company_activation.py,
POST /license/activate) and drops the separate machine-fingerprint-tied
license system (license_manager.py, owner_tool.py, CPRO- keys). That whole
subsystem is removed from the codebase in this same change.

licencias_activadas had exactly one row before this migration, kept here for
the record (not restored by downgrade, since the machine-license code that
would use it is gone too):
  id=1, empresa_id=1, machine_id='6364D661B6466B650609E5DD3ED88BB5',
  activa=True, creado=2026-06-08 15:33:10

Revision ID: 20260907_0007
Revises: 20260907_0006
Create Date: 2026-09-07
"""
from alembic import op
import sqlalchemy as sa

revision = "20260907_0007"
down_revision = "20260907_0006"
branch_labels = None
depends_on = None


def upgrade():
    op.drop_table("licencias_activadas")


def downgrade():
    op.create_table(
        "licencias_activadas",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("empresa_id", sa.Integer(),
                  sa.ForeignKey("empresas.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("machine_id", sa.String(length=64), nullable=False, index=True),
        sa.Column("ip", sa.String(length=45), nullable=True),
        sa.Column("license_key", sa.Text(), nullable=False),
        sa.Column("activa", sa.Boolean(), nullable=True),
        sa.Column("creado", sa.DateTime(), nullable=True),
        sa.UniqueConstraint("machine_id", name="uq_licencia_machine"),
    )
