"""Anular prestamos y retirar clientes, sin borrar su historia

El administrador puede eliminar un prestamo o un cliente. No se borran: se
anulan (prestamo) o se retiran (cliente). Desaparecen de la ruta, de la
cartera y de los totales, pero quedan en el historial con quien, cuando y por
que, y los cobros que ya se hicieron siguen en los reportes de su semana.

- prestamos.estado admite 'Anulado'; las cuotas pendientes de un prestamo
  anulado pasan a 'Anulada' (asi ninguna consulta de "cuotas pendientes" las
  vuelve a ofrecer).
- prestamos: anulado_por, anulado_en, motivo_anulacion.
- clientes: retirado_por, retirado_en, motivo_retiro (el retiro es activo=False).

Idempotente. En Postgres la restriccion se suelta y se vuelve a poner; en
SQLite va en batch (ver 20260926_0022).

Revision ID: 20261003_0028
Revises: 20261003_0027
"""
import sqlalchemy as sa
from alembic import op

revision = "20261003_0028"
down_revision = "20261003_0027"
branch_labels = None
depends_on = None

PRESTAMO = ("prestamos", "ck_prestamo_estado",
            "estado IN ('Activo','Pagado','Mora','Castigado','Cancelado','Atrasado','Anulado')")
CUOTA = ("cuotas", "ck_cuota_estado",
         "estado IN ('Pendiente','Pagada','Vencida','Parcial','Anulada')")


def _restriccion(tabla, nombre, condicion):
    if op.get_bind().dialect.name == "postgresql":
        op.execute(f"ALTER TABLE {tabla} DROP CONSTRAINT IF EXISTS {nombre}")
        op.create_check_constraint(nombre, tabla, condicion)
        return
    with op.batch_alter_table(tabla) as lote:
        try:
            lote.drop_constraint(nombre, type_="check")
        except Exception:
            pass
        lote.create_check_constraint(nombre, condicion)


def _columna(tabla, columna):
    cols = {c["name"] for c in sa.inspect(op.get_bind()).get_columns(tabla)}
    if columna.name not in cols:
        op.add_column(tabla, columna)


def upgrade():
    _columna("prestamos", sa.Column("anulado_por", sa.String(200), nullable=True))
    _columna("prestamos", sa.Column("anulado_en", sa.DateTime(), nullable=True))
    _columna("prestamos", sa.Column("motivo_anulacion", sa.String(300), nullable=True))
    _columna("clientes", sa.Column("retirado_por", sa.String(200), nullable=True))
    _columna("clientes", sa.Column("retirado_en", sa.DateTime(), nullable=True))
    _columna("clientes", sa.Column("motivo_retiro", sa.String(300), nullable=True))
    _restriccion(*PRESTAMO)
    _restriccion(*CUOTA)


def downgrade():
    op.execute("UPDATE cuotas SET estado = 'Pendiente' WHERE estado = 'Anulada'")
    op.execute("UPDATE prestamos SET estado = 'Cancelado' WHERE estado = 'Anulado'")
    _restriccion("prestamos", "ck_prestamo_estado",
                 "estado IN ('Activo','Pagado','Mora','Castigado','Cancelado','Atrasado')")
    _restriccion("cuotas", "ck_cuota_estado",
                 "estado IN ('Pendiente','Pagada','Vencida','Parcial')")
