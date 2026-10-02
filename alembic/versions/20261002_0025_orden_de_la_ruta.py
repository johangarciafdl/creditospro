"""orden_ruta: el orden en que cada cobrador visita los clientes de una zona

El cobrador acomoda su lista arrastrando a las personas, y ese orden se queda
fijo: cobrar a alguien, o que cambie de color, ya no lo mueve. Se guarda en
el servidor (y no en el celular) para que sobreviva a un cambio de telefono y
para que el administrador pueda verlo y corregirlo.

Cada paso comprueba antes si ya esta hecho (ver 20260926_0021: el proveedor
arranca dos contenedores a la vez y los dos migran al mismo tiempo).

Revision ID: 20261002_0025
Revises: 20260927_0024
"""
import sqlalchemy as sa
from alembic import op

revision = "20261002_0025"
down_revision = "20260927_0024"
branch_labels = None
depends_on = None


def _hay_tabla(nombre):
    return nombre in sa.inspect(op.get_bind()).get_table_names()


def _hay_indice(tabla, nombre):
    return nombre in {i["name"] for i in sa.inspect(op.get_bind()).get_indexes(tabla)}


def upgrade():
    if not _hay_tabla("orden_ruta"):
        op.create_table(
            "orden_ruta",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("empresa_id", sa.Integer(),
                      sa.ForeignKey("empresas.id", ondelete="CASCADE"), nullable=False),
            sa.Column("usuario_id", sa.Integer(),
                      sa.ForeignKey("usuarios.id", ondelete="CASCADE"), nullable=False),
            sa.Column("zona_id", sa.Integer(),
                      sa.ForeignKey("zonas.id", ondelete="CASCADE"), nullable=False),
            sa.Column("cliente_id", sa.Integer(),
                      sa.ForeignKey("clientes.id", ondelete="CASCADE"), nullable=False),
            sa.Column("posicion", sa.Integer(), nullable=False),
            sa.Column("actualizado", sa.DateTime(), server_default=sa.func.now()),
            sa.UniqueConstraint("usuario_id", "zona_id", "cliente_id",
                                name="uq_orden_usuario_zona_cliente"),
        )
    if not _hay_indice("orden_ruta", "ix_orden_ruta_usuario_zona"):
        op.create_index("ix_orden_ruta_usuario_zona", "orden_ruta", ["usuario_id", "zona_id"])
    if not _hay_indice("orden_ruta", "ix_orden_ruta_empresa_id"):
        op.create_index("ix_orden_ruta_empresa_id", "orden_ruta", ["empresa_id"])
    if not _hay_indice("orden_ruta", "ix_orden_ruta_id"):
        op.create_index("ix_orden_ruta_id", "orden_ruta", ["id"])

    # En Supabase una tabla nueva queda abierta a la API publica (roles anon y
    # authenticated) hasta que se le activa RLS. Se activa aqui mismo, con la
    # misma politica que rls_policies.sql, para que no haya ni un minuto con
    # la tabla expuesta. Solo en Postgres y solo si la base ya tiene la
    # funcion de las politicas (las demas tablas ya la usan).
    bind = op.get_bind()
    if bind.dialect.name == "postgresql" and bind.execute(sa.text(
            "SELECT 1 FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace "
            "WHERE n.nspname = 'public' AND p.proname = 'current_empresa_id'")).first():
        op.execute("ALTER TABLE orden_ruta ENABLE ROW LEVEL SECURITY")
        op.execute("DROP POLICY IF EXISTS empresa_isolation_orden_ruta ON orden_ruta")
        op.execute("""
            CREATE POLICY empresa_isolation_orden_ruta ON orden_ruta
              USING (
                empresa_id = public.current_empresa_id()
                AND EXISTS (SELECT 1 FROM usuarios u
                            WHERE u.id = orden_ruta.usuario_id
                              AND u.empresa_id = public.current_empresa_id()))
              WITH CHECK (
                empresa_id = public.current_empresa_id()
                AND EXISTS (SELECT 1 FROM usuarios u
                            WHERE u.id = orden_ruta.usuario_id
                              AND u.empresa_id = public.current_empresa_id())
                AND EXISTS (SELECT 1 FROM clientes c
                            WHERE c.id = orden_ruta.cliente_id
                              AND c.empresa_id = public.current_empresa_id()))
        """)


def downgrade():
    op.drop_table("orden_ruta")
