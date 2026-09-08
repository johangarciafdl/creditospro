"""pin search_path on current_empresa_id() (RLS helper)

Supabase's security advisor flags any function without a fixed search_path
as WARN ("function_search_path_mutable"): without SET search_path, a
function resolves unqualified names against whatever search_path the
calling session has, which a malicious session could manipulate. This
function calls no unqualified names (only current_setting()/NULLIF, both
resolved from pg_catalog regardless), so it isn't practically exploitable
today -- but every RLS policy in the app depends on this function, so
pinning it is cheap, safe defense-in-depth worth doing anyway.

Revision ID: 20260908_0008
Revises: 20260907_0007
Create Date: 2026-09-08
"""
from alembic import op

revision = "20260908_0008"
down_revision = "20260907_0007"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return  # RLS/esta funcion no existen en SQLite (dev)
    op.execute("""
        CREATE OR REPLACE FUNCTION public.current_empresa_id()
        RETURNS integer
        LANGUAGE sql
        STABLE
        SET search_path = ''
        AS $$
          SELECT NULLIF(current_setting('app.empresa_id', true), '')::integer;
        $$;
    """)


def downgrade():
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    op.execute("""
        CREATE OR REPLACE FUNCTION public.current_empresa_id()
        RETURNS integer
        LANGUAGE sql
        STABLE
        AS $$
          SELECT NULLIF(current_setting('app.empresa_id', true), '')::integer;
        $$;
    """)
