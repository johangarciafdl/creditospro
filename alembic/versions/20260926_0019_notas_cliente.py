"""notas_cliente: el cobrador avisa, el admin corrige

El cobrador dejo de poder tocar la ficha de un cliente, y quien esta en la
calle es justamente el unico que se entera de que alguien se mudo o cambio
de numero. Sin un sitio donde apuntarlo, ese dato se pierde. La nota no
modifica nada: deja constancia y le llega al admin como pendiente.

Revision ID: 20260926_0019
Revises: 20260920_0018
"""
import sqlalchemy as sa
from alembic import op

revision = "20260926_0019"
down_revision = "20260920_0018"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "notas_cliente",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("empresa_id", sa.Integer(),
                  sa.ForeignKey("empresas.id", ondelete="CASCADE"), nullable=False),
        sa.Column("cliente_id", sa.Integer(),
                  sa.ForeignKey("clientes.id", ondelete="CASCADE"), nullable=False),
        sa.Column("texto", sa.String(600), nullable=False),
        sa.Column("usuario_id", sa.Integer(),
                  sa.ForeignKey("usuarios.id", ondelete="SET NULL"), nullable=True),
        sa.Column("escrita_por", sa.String(200), nullable=True),
        sa.Column("creado", sa.DateTime(), server_default=sa.func.now()),
        sa.Column("atendida", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("atendida_por_id", sa.Integer(),
                  sa.ForeignKey("usuarios.id", ondelete="SET NULL"), nullable=True),
        sa.Column("atendida_por", sa.String(200), nullable=True),
        sa.Column("atendida_en", sa.DateTime(), nullable=True),
        sa.CheckConstraint("length(trim(texto)) > 0", name="ck_nota_no_vacia"),
    )
    op.create_index("ix_notas_cliente_empresa_id", "notas_cliente", ["empresa_id"])
    op.create_index("ix_notas_cliente_cliente_id", "notas_cliente", ["cliente_id"])
    op.create_index("ix_notas_cliente_usuario_id", "notas_cliente", ["usuario_id"])
    # La consulta que mas se hace: las pendientes de una empresa.
    op.create_index("ix_notas_empresa_atendida", "notas_cliente", ["empresa_id", "atendida"])
    op.create_index("ix_notas_empresa_cliente", "notas_cliente", ["empresa_id", "cliente_id"])

    # Aislamiento entre empresas a nivel de base, igual que el resto de
    # tablas de negocio. Una tabla nueva sin su politica es una tabla que
    # el rol restringido podria leer entera.
    if op.get_bind().dialect.name == "postgresql":
        op.execute("ALTER TABLE notas_cliente ENABLE ROW LEVEL SECURITY")
        op.execute("""
            CREATE POLICY empresa_isolation_notas_cliente ON notas_cliente
              USING (empresa_id = public.current_empresa_id())
              WITH CHECK (empresa_id = public.current_empresa_id())
        """)


def downgrade():
    if op.get_bind().dialect.name == "postgresql":
        op.execute("DROP POLICY IF EXISTS empresa_isolation_notas_cliente ON notas_cliente")
    op.drop_table("notas_cliente")
