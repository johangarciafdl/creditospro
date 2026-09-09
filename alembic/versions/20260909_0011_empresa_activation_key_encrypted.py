"""add Empresa.activation_key_encrypted (reversible copy of activation key)

Permite que el superadmin vea de nuevo una clave de activacion ya
entregada, desde /plataforma, sin tener que rotarla. El hash existente
(activation_key_hash) sigue siendo el unico usado para validar
/license/activate -- esta columna es solo para poder mostrarla.

Revision ID: 20260909_0011
Revises: 20260909_0010
Create Date: 2026-09-09
"""
from alembic import op
import sqlalchemy as sa

revision = "20260909_0011"
down_revision = "20260909_0010"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("empresas", sa.Column("activation_key_encrypted", sa.Text(), nullable=True))


def downgrade():
    op.drop_column("empresas", "activation_key_encrypted")
