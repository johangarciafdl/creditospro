"""usuarios.empresa_id nullable -- el superadmin de plataforma no pertenece a ninguna empresa

El rol 'superadmin' administra TODAS las empresas desde /plataforma; antes
tenia que crearse dentro de una empresa "de mentiras" solo para satisfacer
esta columna NOT NULL, lo cual mezclaba su identidad de dueno de la
plataforma con la de un cliente mas. Ahora esa fila puede tener
empresa_id NULL -- ver get_current_user() en app/routers/auth.py.

Revision ID: 20260909_0010
Revises: 20260909_0009
Create Date: 2026-09-09
"""
from alembic import op
import sqlalchemy as sa

revision = "20260909_0010"
down_revision = "20260909_0009"
branch_labels = None
depends_on = None


def upgrade():
    op.alter_column("usuarios", "empresa_id", existing_type=sa.Integer(), nullable=True)


def downgrade():
    op.alter_column("usuarios", "empresa_id", existing_type=sa.Integer(), nullable=False)
