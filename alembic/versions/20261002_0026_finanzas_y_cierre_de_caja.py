"""Finanzas: ciclos de liquidacion, caja general y cierre de caja diario

- empresas.ciclo_inicio: desde que dia corren los ciclos de 6 semanas.
- movimientos_caja_general: lo que entra y sale de la caja del dueño a mano
  (saldo inicial, retiros, aportes, pagos a cobradores, reserva, ajustes).
- liquidaciones: cada ciclo cerrado, con sus cifras y su reparto.
- cierres_caja: el cobrador declara lo que entrega y el admin confirma.

Cada paso comprueba antes si ya esta hecho (dos contenedores pueden migrar a
la vez; ver 20260926_0021). En Postgres las tres tablas nuevas salen ya con
RLS y su politica: en Supabase una tabla sin RLS queda abierta a la API
publica desde el primer minuto.

Revision ID: 20261002_0026
Revises: 20261002_0025
"""
import sqlalchemy as sa
from alembic import op

revision = "20261002_0026"
down_revision = "20261002_0025"
branch_labels = None
depends_on = None


def _insp():
    return sa.inspect(op.get_bind())


def _hay_tabla(nombre):
    return nombre in _insp().get_table_names()


def _hay_columna(tabla, columna):
    return columna in {c["name"] for c in _insp().get_columns(tabla)}


def _hay_indice(tabla, nombre):
    return nombre in {i["name"] for i in _insp().get_indexes(tabla)}


def upgrade():
    if not _hay_columna("empresas", "ciclo_inicio"):
        op.add_column("empresas", sa.Column("ciclo_inicio", sa.Date(), nullable=True))

    if not _hay_tabla("liquidaciones"):
        op.create_table(
            "liquidaciones",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("empresa_id", sa.Integer(),
                      sa.ForeignKey("empresas.id", ondelete="CASCADE"), nullable=False),
            sa.Column("numero", sa.Integer(), nullable=False),
            sa.Column("desde", sa.Date(), nullable=False),
            sa.Column("hasta", sa.Date(), nullable=False),
            sa.Column("cobrado", sa.Numeric(14, 2), nullable=False, server_default="0"),
            sa.Column("prestado", sa.Numeric(14, 2), nullable=False, server_default="0"),
            sa.Column("gastos", sa.Numeric(14, 2), nullable=False, server_default="0"),
            sa.Column("intereses", sa.Numeric(14, 2), nullable=False, server_default="0"),
            sa.Column("resultado", sa.Numeric(14, 2), nullable=False, server_default="0"),
            sa.Column("base", sa.Numeric(14, 2), nullable=False, server_default="0"),
            sa.Column("retiro", sa.Numeric(14, 2), nullable=False, server_default="0"),
            sa.Column("reserva", sa.Numeric(14, 2), nullable=False, server_default="0"),
            sa.Column("pagos_cobradores", sa.Numeric(14, 2), nullable=False, server_default="0"),
            sa.Column("detalle", sa.Text(), nullable=True),
            sa.Column("cerrado_por_id", sa.Integer(),
                      sa.ForeignKey("usuarios.id", ondelete="SET NULL"), nullable=True),
            sa.Column("cerrado_por", sa.String(200), nullable=True),
            sa.Column("creado", sa.DateTime(), server_default=sa.func.now()),
            sa.UniqueConstraint("empresa_id", "numero", name="uq_liquidacion_empresa_numero"),
        )
    for nombre, cols in (("ix_liquidaciones_id", ["id"]),
                         ("ix_liquidaciones_empresa_id", ["empresa_id"])):
        if not _hay_indice("liquidaciones", nombre):
            op.create_index(nombre, "liquidaciones", cols)

    if not _hay_tabla("movimientos_caja_general"):
        op.create_table(
            "movimientos_caja_general",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("empresa_id", sa.Integer(),
                      sa.ForeignKey("empresas.id", ondelete="CASCADE"), nullable=False),
            sa.Column("fecha", sa.Date(), nullable=False),
            sa.Column("tipo", sa.String(20), nullable=False),
            sa.Column("valor", sa.Numeric(14, 2), nullable=False),
            sa.Column("concepto", sa.String(300), nullable=True),
            sa.Column("usuario_id", sa.Integer(),
                      sa.ForeignKey("usuarios.id", ondelete="SET NULL"), nullable=True),
            sa.Column("liquidacion_id", sa.Integer(),
                      sa.ForeignKey("liquidaciones.id", ondelete="SET NULL"), nullable=True),
            sa.Column("registrado_por_id", sa.Integer(),
                      sa.ForeignKey("usuarios.id", ondelete="SET NULL"), nullable=True),
            sa.Column("registrado_por", sa.String(200), nullable=True),
            sa.Column("creado", sa.DateTime(), server_default=sa.func.now()),
            sa.CheckConstraint("valor >= 0", name="ck_caja_general_valor"),
            sa.CheckConstraint(
                "tipo IN ('saldo_inicial','aporte','retiro','pago_cobrador','a_reserva',"
                "'de_reserva','ajuste_mas','ajuste_menos')",
                name="ck_caja_general_tipo"),
        )
    for nombre, cols in (("ix_movimientos_caja_general_id", ["id"]),
                         ("ix_movimientos_caja_general_empresa_id", ["empresa_id"]),
                         ("ix_caja_general_empresa_fecha", ["empresa_id", "fecha"])):
        if not _hay_indice("movimientos_caja_general", nombre):
            op.create_index(nombre, "movimientos_caja_general", cols)

    if not _hay_tabla("cierres_caja"):
        op.create_table(
            "cierres_caja",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("empresa_id", sa.Integer(),
                      sa.ForeignKey("empresas.id", ondelete="CASCADE"), nullable=False),
            sa.Column("usuario_id", sa.Integer(),
                      sa.ForeignKey("usuarios.id", ondelete="CASCADE"), nullable=False),
            sa.Column("fecha", sa.Date(), nullable=False),
            sa.Column("esperado", sa.Numeric(14, 2), nullable=False, server_default="0"),
            sa.Column("declarado", sa.Numeric(14, 2), nullable=True),
            sa.Column("recibido", sa.Numeric(14, 2), nullable=True),
            sa.Column("diferencia", sa.Numeric(14, 2), nullable=True),
            sa.Column("nota", sa.String(300), nullable=True),
            sa.Column("estado", sa.String(20), nullable=False, server_default="declarado"),
            sa.Column("declarado_en", sa.DateTime(), nullable=True),
            sa.Column("confirmado_por_id", sa.Integer(),
                      sa.ForeignKey("usuarios.id", ondelete="SET NULL"), nullable=True),
            sa.Column("confirmado_por", sa.String(200), nullable=True),
            sa.Column("confirmado_en", sa.DateTime(), nullable=True),
            sa.UniqueConstraint("usuario_id", "fecha", name="uq_cierre_usuario_fecha"),
            sa.CheckConstraint("estado IN ('declarado','confirmado')", name="ck_cierre_estado"),
        )
    for nombre, cols in (("ix_cierres_caja_id", ["id"]),
                         ("ix_cierres_caja_empresa_id", ["empresa_id"]),
                         ("ix_cierres_empresa_fecha", ["empresa_id", "fecha"])):
        if not _hay_indice("cierres_caja", nombre):
            op.create_index(nombre, "cierres_caja", cols)

    bind = op.get_bind()
    if bind.dialect.name == "postgresql" and bind.execute(sa.text(
            "SELECT 1 FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace "
            "WHERE n.nspname = 'public' AND p.proname = 'current_empresa_id'")).first():
        for tabla in ("liquidaciones", "movimientos_caja_general", "cierres_caja"):
            op.execute(f"ALTER TABLE {tabla} ENABLE ROW LEVEL SECURITY")
            op.execute(f"DROP POLICY IF EXISTS empresa_isolation_{tabla} ON {tabla}")
            op.execute(f"""
                CREATE POLICY empresa_isolation_{tabla} ON {tabla}
                  USING (empresa_id = public.current_empresa_id())
                  WITH CHECK (empresa_id = public.current_empresa_id())
            """)


def downgrade():
    op.drop_table("cierres_caja")
    op.drop_table("movimientos_caja_general")
    op.drop_table("liquidaciones")
    op.drop_column("empresas", "ciclo_inicio")
