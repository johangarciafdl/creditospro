"""usuario zonas many-to-many

Revision ID: 20260509_0002
Revises: 20260509_0001
Create Date: 2026-05-09
"""
from alembic import op
import sqlalchemy as sa

revision = "20260509_0002"
down_revision = "20260509_0001"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "usuario_zonas",
        sa.Column("usuario_id", sa.Integer(), nullable=False),
        sa.Column("zona_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["usuario_id"], ["usuarios.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["zona_id"], ["zonas.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("usuario_id", "zona_id"),
    )
    op.create_index("ix_usuario_zonas_zona_id", "usuario_zonas", ["zona_id"])
    op.execute("""
        INSERT INTO usuario_zonas (usuario_id, zona_id)
        SELECT id, zona_id FROM usuarios
        WHERE zona_id IS NOT NULL
        ON CONFLICT DO NOTHING
    """)


def downgrade():
    op.drop_index("ix_usuario_zonas_zona_id", table_name="usuario_zonas")
    op.drop_table("usuario_zonas")
