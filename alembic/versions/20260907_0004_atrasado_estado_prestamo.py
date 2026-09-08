"""normalize prestamos.estado casing and add missing financial CHECK constraints

Two independent findings from a production audit, fixed together because the
second migration step depends on the first:

1. Production has 1726 legacy `prestamos` rows with lowercase `estado`
   ('activo', 'pagado') from before the app started writing capitalized
   values. The app code already works around this everywhere with
   `.in_(["Activo","activo",...])` filters - this migration normalizes the
   data instead of leaving the workaround as the permanent fix.
2. None of the 9 CHECK constraints declared in app/database.py actually
   exist in the production database (confirmed via pg_constraint) - they
   were only ever applied to fresh SQLite/Postgres databases created via
   Base.metadata.create_all(), never retrofitted onto the existing
   production tables via a migration. This adds them, including
   'Atrasado' in ck_prestamo_estado (get_estado_prestamo() already returns
   it, and dashboard/reportes/pwa already filter for it - the constraint
   just never allowed it, which would make any payment that triggers this
   state on a constrained database roll back).

Safe to run multiple times: constraint creation is skipped if the exact
constraint already exists (e.g. on a fresh dev DB created via create_all()).

Revision ID: 20260907_0004
Revises: 20260904_0003
Create Date: 2026-09-07
"""
from alembic import op

revision = "20260907_0004"
down_revision = "20260904_0003"
branch_labels = None
depends_on = None

CHECKS = [
    ("prestamos", "ck_prestamo_capital_pos", "capital > 0"),
    ("prestamos", "ck_prestamo_cuotas_rango", "num_cuotas > 0 AND num_cuotas <= 365"),
    ("prestamos", "ck_prestamo_tasa_rango", "tasa_interes >= 0 AND tasa_interes <= 100"),
    ("prestamos", "ck_prestamo_estado",
     "estado IN ('Activo','Pagado','Mora','Castigado','Cancelado','Atrasado')"),
    ("cuotas", "ck_cuota_valor_pos", "valor > 0"),
    ("cuotas", "ck_cuota_pagado_no_neg", "valor_pagado >= 0"),
    ("cuotas", "ck_cuota_pagado_no_excede", "valor_pagado <= valor"),
    ("cuotas", "ck_cuota_estado", "estado IN ('Pendiente','Pagada','Vencida','Parcial')"),
    ("cobros", "ck_cobro_valor_pos", "valor_cobrado > 0"),
]


def upgrade():
    conn = op.get_bind()
    # 1) Normalizar casing legado antes de restringir el valor permitido.
    conn.exec_driver_sql("UPDATE prestamos SET estado = 'Activo' WHERE estado = 'activo'")
    conn.exec_driver_sql("UPDATE prestamos SET estado = 'Pagado' WHERE estado = 'pagado'")

    # 2) Crear las restricciones que faltan (idempotente: se salta si ya existe).
    for table, name, expr in CHECKS:
        exists = conn.exec_driver_sql(
            "SELECT 1 FROM pg_constraint WHERE conname = %(name)s", {"name": name}
        ).fetchone() if conn.dialect.name == "postgresql" else None
        if exists:
            continue
        with op.batch_alter_table(table) as batch_op:
            batch_op.create_check_constraint(name, expr)


def downgrade():
    for table, name, _expr in reversed(CHECKS):
        with op.batch_alter_table(table) as batch_op:
            batch_op.drop_constraint(name, type_="check")
    # La normalizacion de casing (activo->Activo, pagado->Pagado) no se revierte:
    # es una correccion de datos, no un cambio de esquema.
