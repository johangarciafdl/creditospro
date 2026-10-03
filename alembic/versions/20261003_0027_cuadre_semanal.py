"""cuadres_semanales: el cuadre verificado de cada zona por semana

Reemplaza al cierre diario de caja por cobrador: el administrador cuadra
cada zona una vez por semana (cobro, prestamos, gastos, salarios, base,
descuento y efectivo contado) y lo verifica. Ver CuadreSemanal en
app/database.py.

Idempotente (dos contenedores pueden migrar a la vez; ver 20260926_0021).
En Postgres la tabla sale ya con RLS y su politica.

Revision ID: 20261003_0027
Revises: 20261002_0026
"""
import sqlalchemy as sa
from alembic import op

revision = "20261003_0027"
down_revision = "20261002_0026"
branch_labels = None
depends_on = None


def upgrade():
    insp = sa.inspect(op.get_bind())
    if "cuadres_semanales" not in insp.get_table_names():
        dinero = lambda n: sa.Column(n, sa.Numeric(14, 2), nullable=False, server_default="0")  # noqa: E731
        op.create_table(
            "cuadres_semanales",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("empresa_id", sa.Integer(),
                      sa.ForeignKey("empresas.id", ondelete="CASCADE"), nullable=False),
            sa.Column("zona_id", sa.Integer(),
                      sa.ForeignKey("zonas.id", ondelete="CASCADE"), nullable=False),
            sa.Column("semana", sa.Date(), nullable=False),
            dinero("cobro"), dinero("prestamos"), dinero("gastos"), dinero("salarios"),
            dinero("base"), dinero("descuento"), dinero("efectivo"), dinero("esperado"),
            dinero("diferencia"), dinero("intereses"), dinero("utilidad"),
            sa.Column("nota", sa.String(300), nullable=True),
            sa.Column("verificado_por_id", sa.Integer(),
                      sa.ForeignKey("usuarios.id", ondelete="SET NULL"), nullable=True),
            sa.Column("verificado_por", sa.String(200), nullable=True),
            sa.Column("verificado_en", sa.DateTime(), server_default=sa.func.now()),
            sa.UniqueConstraint("empresa_id", "zona_id", "semana", name="uq_cuadre_zona_semana"),
        )
    indices = {i["name"] for i in sa.inspect(op.get_bind()).get_indexes("cuadres_semanales")}
    for nombre, cols in (("ix_cuadres_semanales_id", ["id"]),
                         ("ix_cuadres_semanales_empresa_id", ["empresa_id"]),
                         ("ix_cuadres_empresa_semana", ["empresa_id", "semana"])):
        if nombre not in indices:
            op.create_index(nombre, "cuadres_semanales", cols)

    bind = op.get_bind()
    if bind.dialect.name == "postgresql" and bind.execute(sa.text(
            "SELECT 1 FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace "
            "WHERE n.nspname = 'public' AND p.proname = 'current_empresa_id'")).first():
        op.execute("ALTER TABLE cuadres_semanales ENABLE ROW LEVEL SECURITY")
        op.execute("DROP POLICY IF EXISTS empresa_isolation_cuadres_semanales ON cuadres_semanales")
        op.execute("""
            CREATE POLICY empresa_isolation_cuadres_semanales ON cuadres_semanales
              USING (empresa_id = public.current_empresa_id())
              WITH CHECK (empresa_id = public.current_empresa_id())
        """)


def downgrade():
    op.drop_table("cuadres_semanales")
