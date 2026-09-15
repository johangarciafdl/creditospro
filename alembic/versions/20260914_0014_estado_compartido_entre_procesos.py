"""sesiones_jwt y rate_limit_ventanas: estado compartido entre procesos

Dos piezas de estado vivian solo en la memoria de cada proceso:

- La lista de sesiones emitidas y revocadas. Cada reinicio (es decir, cada
  despliegue) la borraba, asi que un token del que ya se habia hecho
  logout volvia a ser valido; y con mas de un worker, revocar una sesion
  en uno no la revocaba en los demas.
- Los contadores del rate limit. Con N workers el limite efectivo era N
  veces el configurado: 10 intentos de login por minuto se volvian 40 con
  cuatro workers.

Las dos cosas impedian levantar la aplicacion con mas de un worker sin
perder garantias. Con estas tablas el estado es unico para todos los
procesos y sobrevive a los despliegues.

Revision ID: 20260914_0014
Revises: 20260911_0013
Create Date: 2026-09-14
"""
from alembic import op
import sqlalchemy as sa

revision = "20260914_0014"
down_revision = "20260911_0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    existentes = set(sa.inspect(bind).get_table_names())

    if "sesiones_jwt" not in existentes:
        op.create_table(
            "sesiones_jwt",
            sa.Column("jti", sa.String(64), primary_key=True),
            sa.Column("usuario_id", sa.String(40), nullable=False),
            sa.Column("expira_en", sa.Integer, nullable=False),
            sa.Column("emitida_en", sa.Integer, nullable=False),
            sa.Column("ip", sa.String(45), nullable=True),
            sa.Column("revocada", sa.Boolean, nullable=False, server_default=sa.false()),
        )
        op.create_index("ix_sesiones_jwt_usuario_id", "sesiones_jwt", ["usuario_id"])
        op.create_index("ix_sesiones_jwt_expira_en", "sesiones_jwt", ["expira_en"])
        # La consulta caliente es "jtis revocados que aun no expiran", que se
        # ejecuta cada pocos segundos en cada proceso.
        op.create_index(
            "ix_sesiones_jwt_revocada_expira", "sesiones_jwt", ["revocada", "expira_en"]
        )

    if "rate_limit_ventanas" not in existentes:
        op.create_table(
            "rate_limit_ventanas",
            sa.Column("clave", sa.String(200), primary_key=True),
            sa.Column("ventana_inicio", sa.Integer, nullable=False),
            sa.Column("conteo", sa.Integer, nullable=False, server_default="0"),
            sa.Column("actualizado_en", sa.Integer, nullable=False),
        )
        # Para la limpieza periodica de ventanas que ya no consulta nadie.
        op.create_index(
            "ix_rate_limit_ventanas_actualizado", "rate_limit_ventanas", ["actualizado_en"]
        )


def downgrade() -> None:
    op.drop_table("rate_limit_ventanas")
    op.drop_table("sesiones_jwt")
