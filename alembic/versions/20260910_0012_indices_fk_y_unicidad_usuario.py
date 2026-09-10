"""indices en claves foraneas + unicidad (empresa_id, username)

Los advisors de rendimiento de Supabase reportaron 11 claves foraneas sin
indice que las cubra. En este esquema todas las consultas normales filtran
primero por empresa_id (y para eso ya hay indices compuestos), asi que el
impacto no esta en las lecturas del dia a dia sino en:

  - los borrados/actualizaciones del padre (borrar un cliente obliga a
    Postgres a revisar cobros y notificaciones_wp fila por fila sin indice), y
  - los joins que no arrancan desde empresa_id.

Ademas, la restriccion uq_user_empresa (empresa_id, username) estaba definida
en el modelo pero nunca llego a la base real: hasta ahora la unicidad del
username dentro de una empresa dependia solo del chequeo de la aplicacion.
Se verifico que no hay duplicados antes de crearla.

Revision ID: 20260910_0012
Revises: 20260909_0011
Create Date: 2026-09-10
"""
from alembic import op

revision = "20260910_0012"
down_revision = "20260909_0011"
branch_labels = None
depends_on = None

_INDICES = [
    ("ix_cobros_cliente_id", "cobros", "cliente_id"),
    ("ix_cobros_cuota_id", "cobros", "cuota_id"),
    ("ix_cobros_prestamo_id", "cobros", "prestamo_id"),
    ("ix_cobros_usuario_id", "cobros", "usuario_id"),
    ("ix_cobros_zona_id", "cobros", "zona_id"),
    ("ix_notificaciones_wp_cliente_id", "notificaciones_wp", "cliente_id"),
    ("ix_notificaciones_wp_cuota_id", "notificaciones_wp", "cuota_id"),
    ("ix_prestamos_zona_id", "prestamos", "zona_id"),
    ("ix_usuarios_empresa_id", "usuarios", "empresa_id"),
    ("ix_usuarios_zona_id", "usuarios", "zona_id"),
    ("ix_zonas_empresa_id", "zonas", "empresa_id"),
]


def upgrade():
    for nombre, tabla, columna in _INDICES:
        op.create_index(nombre, tabla, [columna], if_not_exists=True)
    op.create_unique_constraint("uq_user_empresa", "usuarios", ["empresa_id", "username"])


def downgrade():
    op.drop_constraint("uq_user_empresa", "usuarios", type_="unique")
    for nombre, tabla, _columna in _INDICES:
        op.drop_index(nombre, table_name=tabla, if_exists=True)
