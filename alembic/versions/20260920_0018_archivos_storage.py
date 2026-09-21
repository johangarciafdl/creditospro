"""Los bytes de las imagenes se van a Supabase Storage

archivos se queda como indice -- de que empresa es cada imagen, que es lo que
permite negarsela a otra -- y los bytes pasan a un bucket privado. La columna
datos sigue existiendo y admite nulo porque las imagenes subidas antes del
cambio se leen de ahi, y porque sin credenciales de Storage (pruebas y
desarrollo local) la aplicacion las guarda en la base como hasta ahora.

Revision ID: 20260920_0018
Revises: 20260920_0017
"""
from alembic import op
import sqlalchemy as sa

revision = "20260920_0018"
down_revision = "20260920_0017"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("archivos", sa.Column(
        "almacen", sa.String(length=20), nullable=False, server_default="bd"))
    op.add_column("archivos", sa.Column("ruta", sa.String(length=400), nullable=True))
    op.alter_column("archivos", "datos", existing_type=sa.LargeBinary(), nullable=True)
    # Localizar rapido lo que queda pendiente de mover.
    op.create_index("ix_archivos_almacen", "archivos", ["almacen"])


def downgrade() -> None:
    op.drop_index("ix_archivos_almacen", table_name="archivos")
    # Volver atras exige que no quede nada solo en Storage.
    op.execute("DELETE FROM archivos WHERE datos IS NULL")
    op.alter_column("archivos", "datos", existing_type=sa.LargeBinary(), nullable=False)
    op.drop_column("archivos", "ruta")
    op.drop_column("archivos", "almacen")
