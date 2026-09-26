"""El gasto entra en la caja, y el viatico automatico sale

Los 15.000 del almuerzo se descontaban solos, sin que nadie los hubiera
escrito. Eso hace imposible cuadrar un dia que no fue como siempre -- el que
no salio a la calle, el que almorzo en casa, el que gasto el doble en
transporte -- porque el dinero que falta no tiene ninguna linea que lo
explique. Ahora todo lo que sale de la caja tiene su fila, con su valor y su
concepto, y la anota el propio cobrador.

Lo unico que cambia en la base es que el tipo `gasto` pase a ser valido.

Revision ID: 20260926_0022
Revises: 20260926_0021
"""
import sqlalchemy as sa
from alembic import op

revision = "20260926_0022"
down_revision = "20260926_0021"
branch_labels = None
depends_on = None

RESTRICCION = "ck_movimiento_tipo"
TIPOS_NUEVOS = "tipo IN ('base','gasto','entrega','ajuste_mas','ajuste_menos')"
TIPOS_VIEJOS = "tipo IN ('base','entrega','ajuste_mas','ajuste_menos')"


def _cambiar(condicion):
    """Reemplaza la restriccion de tipos.

    Postgres la suelta y la vuelve a poner. SQLite no sabe hacer eso -- una
    restriccion de tabla solo existe dentro de su CREATE TABLE -- asi que
    alembic copia la tabla entera; por eso va en batch, que conserva las
    filas que hubiera.
    """
    dialecto = op.get_bind().dialect.name
    if dialecto == "postgresql":
        op.execute(f"ALTER TABLE movimientos_caja DROP CONSTRAINT IF EXISTS {RESTRICCION}")
        op.create_check_constraint(RESTRICCION, "movimientos_caja", condicion)
        return
    with op.batch_alter_table("movimientos_caja") as lote:
        try:
            lote.drop_constraint(RESTRICCION, type_="check")
        except Exception:
            # En una base creada desde el modelo la restriccion puede no
            # llamarse asi; recrearla igualmente deja el estado correcto.
            pass
        lote.create_check_constraint(RESTRICCION, condicion)


def upgrade():
    _cambiar(TIPOS_NUEVOS)


def downgrade():
    # Los gastos ya anotados dejarian de cumplir la restriccion vieja, asi que
    # se retiran antes: volver atras no puede dejar la tabla en un estado que
    # la propia base rechaza.
    op.execute("DELETE FROM movimientos_caja WHERE tipo = 'gasto'")
    _cambiar(TIPOS_VIEJOS)
