"""Las imagenes pasan del disco del contenedor a la base de datos

El proveedor da un disco efimero: cada despliegue borraba uploads/, asi que
toda foto tomada por un cobrador desaparecia y el perfil del cliente se
quedaba con la imagen rota. Aqui viajan con la base de datos y entran en sus
copias de seguridad. De paso, cobros gana la columna donde anotar su foto,
que se pedia en pantalla y no se guardaba en ninguna parte.

Revision ID: 20260920_0017
Revises: 20260919_0016
"""
from alembic import op
import sqlalchemy as sa

revision = "20260920_0017"
down_revision = "20260919_0016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "archivos",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("empresa_id", sa.Integer(), nullable=False),
        sa.Column("nombre", sa.String(length=300), nullable=False),
        sa.Column("tipo", sa.String(length=30), nullable=False, server_default="cliente"),
        sa.Column("mime", sa.String(length=80), nullable=False, server_default="image/jpeg"),
        sa.Column("datos", sa.LargeBinary(), nullable=False),
        sa.Column("tamano", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("creado", sa.DateTime(), server_default=sa.func.now(), nullable=True),
        sa.ForeignKeyConstraint(["empresa_id"], ["empresas.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("nombre", name="uq_archivo_nombre"),
    )
    op.create_index("ix_archivos_id", "archivos", ["id"])
    # Postgres no indexa las claves foraneas solo: sin esto cada CASCADE
    # recorre la tabla entera.
    op.create_index("ix_archivos_empresa_id", "archivos", ["empresa_id"])
    op.create_index("ix_archivos_nombre", "archivos", ["nombre"])
    op.create_index("ix_archivos_empresa_tipo", "archivos", ["empresa_id", "tipo"])

    op.add_column("cobros", sa.Column("foto_path", sa.String(length=300), nullable=True))


def downgrade() -> None:
    op.drop_column("cobros", "foto_path")
    op.drop_index("ix_archivos_empresa_tipo", table_name="archivos")
    op.drop_index("ix_archivos_nombre", table_name="archivos")
    op.drop_index("ix_archivos_empresa_id", table_name="archivos")
    op.drop_index("ix_archivos_id", table_name="archivos")
    op.drop_table("archivos")
