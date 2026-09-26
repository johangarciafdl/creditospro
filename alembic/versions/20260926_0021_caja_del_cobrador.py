"""movimientos_caja y el desembolso del prestamo: el cuadre del cobrador

Un cobrador sale con una base, recoge durante el dia, presta parte de lo que
recoge y devuelve el resto por la tarde. Hasta ahora el sistema sabia lo que
recogia y nada mas, asi que no habia forma de decir si al final del dia le
sobraba o le faltaba dinero -- y un cobrador descuadrado se descubria semanas
despues, o no se descubria.

Dos piezas:

- `movimientos_caja`: la base que entrega la oficina, lo que el cobrador
  devuelve, y las correcciones. Los cobros y los desembolsos no se copian
  aqui: ya estan en `cobros` y en `prestamos`.
- `prestamos.desembolsado_por_id` / `fecha_desembolso`: el admin aprueba el
  prestamo, pero los billetes salen del bolsillo de un cobrador concreto y ese
  dia. Sin esas dos columnas el desembolso no se le puede descontar a nadie.

Cada paso comprueba antes si ya esta hecho. No es cosmetico: ver `upgrade()`.

Revision ID: 20260926_0021
Revises: 20260926_0020
"""
import sqlalchemy as sa
from alembic import op

revision = "20260926_0021"
down_revision = "20260926_0020"
branch_labels = None
depends_on = None


def _inspector():
    return sa.inspect(op.get_bind())


def _hay_tabla(nombre):
    return nombre in _inspector().get_table_names()


def _hay_columna(tabla, columna):
    return columna in {c["name"] for c in _inspector().get_columns(tabla)}


def _crear_indice(nombre, tabla, columnas):
    if nombre not in {i["name"] for i in _inspector().get_indexes(tabla)}:
        op.create_index(nombre, tabla, columnas)


def upgrade():
    """Cada paso comprueba antes si ya esta hecho.

    No es cosmetico. El proveedor arranca dos contenedores a la vez y cada uno
    ejecuta `alembic upgrade head` en su arranque: los dos entran al mismo
    tiempo, uno crea la tabla y el otro se estrella con "la relacion ya
    existe". El que se estrella tumba el despliegue, y a partir de ahi todos
    los arranques mueren en el mismo sitio -- un bucle del que no se sale
    solo, porque el trabajo a medias no se deshace.

    Comprobar antes de crear convierte ese choque en algo inocuo: el segundo
    encuentra la tabla hecha, sigue adelante, y los dos terminan en el mismo
    estado. Es tambien lo que permite retomar una migracion que se quedo a
    medias sin tener que tocar la base a mano.
    """
    if not _hay_tabla("movimientos_caja"):
        op.create_table(
            "movimientos_caja",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("empresa_id", sa.Integer(),
                      sa.ForeignKey("empresas.id", ondelete="CASCADE"), nullable=False),
            sa.Column("usuario_id", sa.Integer(),
                      sa.ForeignKey("usuarios.id", ondelete="CASCADE"), nullable=False),
            sa.Column("fecha", sa.Date(), nullable=False),
            sa.Column("tipo", sa.String(20), nullable=False),
            sa.Column("valor", sa.Numeric(12, 2), nullable=False),
            sa.Column("concepto", sa.String(300), nullable=True),
            sa.Column("registrado_por_id", sa.Integer(),
                      sa.ForeignKey("usuarios.id", ondelete="SET NULL"), nullable=True),
            sa.Column("registrado_por", sa.String(200), nullable=True),
            sa.Column("creado", sa.DateTime(), server_default=sa.func.now()),
            # El valor es siempre positivo: el sentido lo pone el tipo. Un
            # signo guardado dentro del numero se equivoca en silencio, y en un
            # cuadre de caja eso no se nota -- simplemente le cuadra a quien no
            # deberia.
            sa.CheckConstraint("valor > 0", name="ck_movimiento_valor_pos"),
            sa.CheckConstraint("tipo IN ('base','entrega','ajuste_mas','ajuste_menos')",
                               name="ck_movimiento_tipo"),
        )

    _crear_indice("ix_movimientos_caja_empresa_id", "movimientos_caja", ["empresa_id"])
    _crear_indice("ix_movimientos_caja_usuario_id", "movimientos_caja", ["usuario_id"])
    _crear_indice("ix_movimientos_caja_fecha", "movimientos_caja", ["fecha"])
    # La consulta que se hace siempre: la caja de un cobrador en un dia.
    _crear_indice("ix_movimientos_empresa_usuario_fecha", "movimientos_caja",
                  ["empresa_id", "usuario_id", "fecha"])
    _crear_indice("ix_movimientos_empresa_fecha", "movimientos_caja",
                  ["empresa_id", "fecha"])

    # Aislamiento entre empresas a nivel de base, igual que el resto de tablas
    # de negocio. Una tabla nueva sin su politica es una tabla que el rol
    # restringido podria leer entera. El DROP previo es para que reintentar no
    # se estrelle contra la politica que dejo el intento anterior.
    if op.get_bind().dialect.name == "postgresql":
        op.execute("ALTER TABLE movimientos_caja ENABLE ROW LEVEL SECURITY")
        op.execute("DROP POLICY IF EXISTS empresa_isolation_movimientos_caja "
                   "ON movimientos_caja")
        op.execute(
            "CREATE POLICY empresa_isolation_movimientos_caja ON movimientos_caja "
            "  USING (empresa_id = public.current_empresa_id()) "
            "  WITH CHECK (empresa_id = public.current_empresa_id())"
        )

    if not _hay_columna("prestamos", "desembolsado_por_id"):
        op.add_column("prestamos",
                      sa.Column("desembolsado_por_id", sa.Integer(), nullable=True))
    if not _hay_columna("prestamos", "fecha_desembolso"):
        op.add_column("prestamos",
                      sa.Column("fecha_desembolso", sa.Date(), nullable=True))
    _crear_indice("ix_prestamos_desembolsado_por_id", "prestamos",
                  ["desembolsado_por_id"])
    _crear_indice("ix_prestamos_fecha_desembolso", "prestamos", ["fecha_desembolso"])

    # SQLite no sabe anadir una restriccion a una tabla que ya existe -- haria
    # falta copiar la tabla entera -- asi que la clave foranea se crea solo en
    # Postgres, que es donde corre esto de verdad. En una base SQLite nueva la
    # declara el modelo al crear las tablas, y en una que ya existia se queda
    # sin ella: SQLite ni siquiera comprueba las foraneas salvo que se le pida.
    if op.get_bind().dialect.name == "postgresql":
        existentes = {f["name"] for f in _inspector().get_foreign_keys("prestamos")}
        if "fk_prestamo_desembolsado_por" not in existentes:
            op.create_foreign_key("fk_prestamo_desembolsado_por", "prestamos",
                                  "usuarios", ["desembolsado_por_id"], ["id"],
                                  ondelete="SET NULL")

    # Los prestamos que ya existen se quedan sin desembolso atribuido, y asi
    # debe ser: nadie sabe hoy quien entrego aquel dinero, y rellenarlo a ojo
    # descuadraria cajas de dias que ya estan cerrados. El cuadre solo cuenta
    # los desembolsos que se registren a partir de ahora.


def downgrade():
    if op.get_bind().dialect.name == "postgresql":
        op.execute("ALTER TABLE prestamos DROP CONSTRAINT IF EXISTS "
                   "fk_prestamo_desembolsado_por")
    op.drop_index("ix_prestamos_fecha_desembolso", table_name="prestamos")
    op.drop_index("ix_prestamos_desembolsado_por_id", table_name="prestamos")
    op.drop_column("prestamos", "fecha_desembolso")
    op.drop_column("prestamos", "desembolsado_por_id")
    if op.get_bind().dialect.name == "postgresql":
        op.execute("DROP POLICY IF EXISTS empresa_isolation_movimientos_caja "
                   "ON movimientos_caja")
    op.drop_table("movimientos_caja")
