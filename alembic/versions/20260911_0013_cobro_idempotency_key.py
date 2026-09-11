"""cobros.idempotency_key: evita registrar dos veces el mismo cobro offline

La PWA guarda los cobros en el celular cuando no hay señal y los sube al
recuperar conexion. Si la respuesta del servidor se perdia a mitad de
camino (tipico en la calle), el cobro quedaba marcado como NO sincronizado
y en el siguiente intento se volvia a enviar: el cliente terminaba con dos
cobros registrados por el mismo pago.

Ahora el celular genera una clave al momento de registrar el cobro y la
manda en cada reintento. El servidor, si ya vio esa clave, devuelve el
cobro que ya existe en vez de aplicar otro.

Revision ID: 20260911_0013
Revises: 20260910_0012
Create Date: 2026-09-11
"""
from alembic import op
import sqlalchemy as sa

revision = "20260911_0013"
down_revision = "20260910_0012"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("cobros", sa.Column("idempotency_key", sa.String(64), nullable=True))
    # Unico por empresa: dos empresas distintas pueden generar la misma clave
    # sin pisarse, y los cobros viejos (NULL) no chocan entre si en Postgres.
    op.create_unique_constraint("uq_cobro_idempotency", "cobros", ["empresa_id", "idempotency_key"])


def downgrade():
    op.drop_constraint("uq_cobro_idempotency", "cobros", type_="unique")
    op.drop_column("cobros", "idempotency_key")
