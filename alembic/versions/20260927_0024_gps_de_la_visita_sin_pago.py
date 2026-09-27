"""no_pagos.lat / lng: la visita sin pago tambien dice donde fue

Para ordenar la ruta del cobrador por cercania hace falta saber donde vive cada
cliente, y en el sistema casi no hay direcciones. Lo que si hay es el GPS que se
guarda solo con cada cobro -- pero el cobro solo existe para quien paga, y los
clientes que no pagan son justo los que mas hay que visitar. Con estas dos
columnas, cada visita cuenta, pague o no.

Son nullable y sin valor por defecto: las visitas de antes no tienen posicion y
no hay forma honesta de inventarsela.

Cada paso comprueba antes si ya esta hecho (ver 20260926_0021: el proveedor
arranca dos contenedores a la vez y los dos migran al mismo tiempo).

Revision ID: 20260927_0024
Revises: 20260927_0023
"""
import sqlalchemy as sa
from alembic import op

revision = "20260927_0024"
down_revision = "20260927_0023"
branch_labels = None
depends_on = None


def _hay_columna(tabla, columna):
    return columna in {c["name"] for c in sa.inspect(op.get_bind()).get_columns(tabla)}


def upgrade():
    if not _hay_columna("no_pagos", "lat"):
        op.add_column("no_pagos", sa.Column("lat", sa.Float(), nullable=True))
    if not _hay_columna("no_pagos", "lng"):
        op.add_column("no_pagos", sa.Column("lng", sa.Float(), nullable=True))


def downgrade():
    op.drop_column("no_pagos", "lng")
    op.drop_column("no_pagos", "lat")
