-- RLS de CreditosPro para PostgreSQL/Supabase
-- Aplicado y probado en producción el 2026-09-07: verificado que el rol
-- restringido ve exactamente los mismos datos que el owner para su propia
-- empresa, y cero filas sin contexto de tenant o con uno inexistente.
-- Requiere DATABASE_URL_APP apuntando a creditospro_app y ENABLE_DATABASE_RLS=1
-- (ver .env.example). El backend sigue conectándose con DATABASE_URL (el rol
-- owner) para el scheduler, auditoría, activación de licencia y registro de
-- empresa nueva — esas rutas necesitan legítimamente ver más de una empresa
-- antes de tener un usuario autenticado (ver app/database.py: SessionLocal
-- vs AppSessionLocal/get_db_system).

BEGIN;

-- Rol de aplicación: el backend debe conectarse con este rol para las
-- consultas por-empresa, no con el owner (que hace bypass de RLS siempre).
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'creditospro_app') THEN
    CREATE ROLE creditospro_app LOGIN PASSWORD :'creditospro_app_password'
      NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS;
  END IF;
END
$$;
GRANT USAGE ON SCHEMA public TO creditospro_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO creditospro_app;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO creditospro_app;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO creditospro_app;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT USAGE, SELECT ON SEQUENCES TO creditospro_app;

CREATE OR REPLACE FUNCTION public.current_empresa_id()
RETURNS integer
LANGUAGE sql
STABLE
AS $$
  SELECT NULLIF(current_setting('app.empresa_id', true), '')::integer;
$$;

-- Aislamiento por empresa.
ALTER TABLE empresas ENABLE ROW LEVEL SECURITY;
ALTER TABLE usuarios ENABLE ROW LEVEL SECURITY;
ALTER TABLE zonas ENABLE ROW LEVEL SECURITY;
ALTER TABLE clientes ENABLE ROW LEVEL SECURITY;
ALTER TABLE prestamos ENABLE ROW LEVEL SECURITY;
ALTER TABLE cuotas ENABLE ROW LEVEL SECURITY;
ALTER TABLE cobros ENABLE ROW LEVEL SECURITY;
ALTER TABLE notificaciones_wp ENABLE ROW LEVEL SECURITY;
ALTER TABLE configuracion ENABLE ROW LEVEL SECURITY;
ALTER TABLE audit_log ENABLE ROW LEVEL SECURITY;
ALTER TABLE usuario_zonas ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS empresa_isolation_empresas ON empresas;
CREATE POLICY empresa_isolation_empresas ON empresas
  USING (id = public.current_empresa_id())
  WITH CHECK (id = public.current_empresa_id());

DROP POLICY IF EXISTS empresa_isolation_usuarios ON usuarios;
CREATE POLICY empresa_isolation_usuarios ON usuarios
  USING (empresa_id = public.current_empresa_id())
  WITH CHECK (empresa_id = public.current_empresa_id());

DROP POLICY IF EXISTS empresa_isolation_zonas ON zonas;
CREATE POLICY empresa_isolation_zonas ON zonas
  USING (empresa_id = public.current_empresa_id())
  WITH CHECK (empresa_id = public.current_empresa_id());

DROP POLICY IF EXISTS empresa_isolation_clientes ON clientes;
CREATE POLICY empresa_isolation_clientes ON clientes
  USING (empresa_id = public.current_empresa_id())
  WITH CHECK (empresa_id = public.current_empresa_id());

DROP POLICY IF EXISTS empresa_isolation_prestamos ON prestamos;
CREATE POLICY empresa_isolation_prestamos ON prestamos
  USING (empresa_id = public.current_empresa_id())
  WITH CHECK (empresa_id = public.current_empresa_id());

DROP POLICY IF EXISTS empresa_isolation_cuotas ON cuotas;
CREATE POLICY empresa_isolation_cuotas ON cuotas
  USING (empresa_id = public.current_empresa_id())
  WITH CHECK (empresa_id = public.current_empresa_id());

DROP POLICY IF EXISTS empresa_isolation_cobros ON cobros;
CREATE POLICY empresa_isolation_cobros ON cobros
  USING (empresa_id = public.current_empresa_id())
  WITH CHECK (empresa_id = public.current_empresa_id());

DROP POLICY IF EXISTS empresa_isolation_notificaciones ON notificaciones_wp;
CREATE POLICY empresa_isolation_notificaciones ON notificaciones_wp
  USING (empresa_id = public.current_empresa_id())
  WITH CHECK (empresa_id = public.current_empresa_id());

DROP POLICY IF EXISTS empresa_isolation_configuracion ON configuracion;
CREATE POLICY empresa_isolation_configuracion ON configuracion
  USING (empresa_id = public.current_empresa_id())
  WITH CHECK (empresa_id = public.current_empresa_id());

DROP POLICY IF EXISTS empresa_isolation_audit ON audit_log;
CREATE POLICY empresa_isolation_audit ON audit_log
  USING (empresa_id = public.current_empresa_id())
  WITH CHECK (empresa_id = public.current_empresa_id());

-- usuario_zonas no tiene empresa_id propio: se valida via el usuario asociado.
DROP POLICY IF EXISTS empresa_isolation_usuario_zonas ON usuario_zonas;
CREATE POLICY empresa_isolation_usuario_zonas ON usuario_zonas
  USING (EXISTS (
    SELECT 1 FROM usuarios u
    WHERE u.id = usuario_zonas.usuario_id AND u.empresa_id = public.current_empresa_id()
  ))
  WITH CHECK (EXISTS (
    SELECT 1 FROM usuarios u
    WHERE u.id = usuario_zonas.usuario_id AND u.empresa_id = public.current_empresa_id()
  ));

COMMIT;

-- En cada transacción autenticada del backend debe ejecutarse, por ejemplo:
-- SET LOCAL app.empresa_id = '123';
-- Nunca aceptar este valor directamente desde el frontend.
-- Debe derivarse del usuario autenticado en el backend
-- (ver app/database.py: set_tenant_context + evento after_begin).
