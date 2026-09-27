"""Que la tabla de cuotas se mantenga sola antes de degradarse

Medido en produccion: contar las cuotas vencidas en el panel tardaba 40 ms,
el 84 % de toda la consulta de cabecera. La tabla `cuotas` NUNCA se habia
vaciado (last_autovacuum = null) y arrastraba 1.670 filas muertas. Sin el
vaciado, el mapa de visibilidad esta vacio y un "index only scan" tiene que ir
igualmente a la tabla por cada fila: 4.510 lecturas de mas para contar 6.946.

Un VACUUM ANALYZE manual lo bajo a 1,4 ms y 0 lecturas a la tabla. Pero volveria
a pasar: con los valores por defecto, Postgres no vacia una tabla hasta que sus
filas muertas superan 50 + 20 % de las vivas. Con 8.500 cuotas son ~1.750, y la
tabla estaba en 1.670 -- justo por debajo, indefinidamente.

Aqui se baja el umbral para `cuotas`, que es la tabla que mas se reescribe (cada
cobro actualiza una cuota, y el planificador las pasa de Pendiente a Vencida),
a 50 + 2 %: unas 220 filas muertas. Se vacia mas a menudo y cada vez con menos
trabajo, que es justo lo que conviene a una tabla que se consulta en cada carga
del panel.

Solo en Postgres: SQLite no tiene autovacuum.

Revision ID: 20260927_0023
Revises: 20260926_0022
"""
from alembic import op

revision = "20260927_0023"
down_revision = "20260926_0022"
branch_labels = None
depends_on = None


def upgrade():
    if op.get_bind().dialect.name != "postgresql":
        return
    op.execute(
        "ALTER TABLE cuotas SET ("
        "autovacuum_vacuum_scale_factor = 0.02, "
        "autovacuum_analyze_scale_factor = 0.02)"
    )


def downgrade():
    if op.get_bind().dialect.name != "postgresql":
        return
    op.execute(
        "ALTER TABLE cuotas RESET ("
        "autovacuum_vacuum_scale_factor, autovacuum_analyze_scale_factor)"
    )
