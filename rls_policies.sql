-- RLS de CreditosPro para PostgreSQL/Supabase
-- NO ejecutar directamente en producción sin crear primero el rol de aplicación,
-- probar en staging y configurar SET LOCAL app.empresa_id por transacción.
-- El rol propietario de las tablas puede bypass RLS.

BEGIN;

-- Rol recomendado: el backend debe conectarse con este rol, no con el owner.
-- CREATE ROLE creditospro_app NOINHERIT;
-- GRANT USAGE ON SCHEMA public TO creditospro_app;
-- GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO creditospro_app;
-- GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO creditospro_app;

CREATE OR REPLACE FUNCTION public.current_empresa_id()
RETURNS integer
LANGUAGE sql
STABLE
AS $$
  SELECT NULLIF(current_setting('app.empresa_id', true), '')::integer;
$$;

-- Aislamiento por empresa. Activar tabla por tabla después de probar staging.
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
ALTER TABLE licencias_activadas ENABLE ROW LEVEL SECURITY;

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

DROP POLICY IF EXISTS empresa_isolation_licencias ON licencias_activadas;
CREATE POLICY empresa_isolation_licencias ON licencias_activadas
  USING (empresa_id = public.current_empresa_id())
  WITH CHECK (empresa_id = public.current_empresa_id());

COMMIT;

-- En cada transacción autenticada del backend debe ejecutarse, por ejemplo:
-- SET LOCAL app.empresa_id = '123';
-- Nunca aceptar este valor directamente desde el frontend.
-- Debe derivarse del usuario autenticado en el backend.
