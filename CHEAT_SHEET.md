# ⚡ CHEAT SHEET - CREDITOSPRO v3.0

## COMANDOS ESENCIALES

### Iniciar servidor
```bash
cd C:\Users\johan\Downloads\CreditosPro_FINAL\CreditosPro_v2_seguro_base\CreditosPro_v2
python run.py
# http://localhost:8000
```

### Acceso remoto (ngrok)
```bash
# Terminal 2 (mientras run.py está corriendo)
ngrok http 8000
# https://xxxxx.ngrok-free.dev
```

### Migraciones BD
```bash
alembic upgrade head        # Aplicar todas
alembic revision -m "nombre"  # Crear nueva
alembic downgrade -1        # Revertir última
```

### Limpiar duplicados
```bash
python limpiar_elruso_duplicado.py
```

---

## USUARIOS POR DEFECTO

| Usuario | Contraseña | Rol | Acceso |
|---------|-----------|-----|--------|
| johan | XXXXXX | ADMIN | Todo |
| julian | 197991 | GERENTE | Sin config |
| marcos | Marcos123 | COBRADOR | Solo cobros |

---

## URLs PRINCIPALES

```
http://localhost:8000/              Dashboard
http://localhost:8000/clientes      Gestión clientes
http://localhost:8000/prestamos     Gestión préstamos
http://localhost:8000/cobros        Registro de cobros
http://localhost:8000/reportes      Reportes
http://localhost:8000/docs          API docs Swagger
http://localhost:8000/redoc         API docs ReDoc
```

---

## ESTRUCTURA BD (SQL Queries rápidas)

```sql
-- Ver todas las empresas
SELECT id, nombre FROM empresa;

-- Ver usuarios de una empresa
SELECT * FROM usuario WHERE empresa_id = 1;

-- Ver préstamos activos
SELECT * FROM prestamo WHERE estado = 'ACTIVO';

-- Ver cobros del mes
SELECT * FROM cobro WHERE DATE(fecha) >= DATE('now', 'start of month');

-- Cartera vencida
SELECT * FROM prestamo 
WHERE estado = 'ACTIVO' AND vencimiento < NOW();

-- Total cobrado por usuario
SELECT usuario_id, SUM(monto) 
FROM cobro 
WHERE DATE(fecha) = DATE('now')
GROUP BY usuario_id;
```

---

## ARCHIVOS CRÍTICOS

| Archivo | Propósito |
|---------|-----------|
| `run.py` | Punto entrada servidor |
| `app/main.py` | Configuración FastAPI |
| `app/database.py` | Modelos SQLAlchemy |
| `templates/base.html` | HTML maestra (incluye CSS/JS) |
| `.env` | Variables de entorno ⚠️ SECRETO |
| `requirements.txt` | Dependencias Python |
| `alembic.ini` | Config migraciones |

---

## ERRORES COMUNES Y SOLUCIONES

### ❌ `ModuleNotFoundError: No module named 'fastapi'`
```bash
pip install -r requirements.txt
```

### ❌ `DATABASE_URL not set`
```bash
# Copia .env.example a .env y configura
```

### ❌ `Port 8000 already in use`
```bash
# Opción 1: Cambiar PORT en .env
# Opción 2: Matar proceso
netsh int ipv4 show tcpconn | findstr "8000"
taskkill /PID [numero] /F
```

### ❌ `ngrok: command not found`
```bash
cd C:\Users\johan\Downloads\ngrok
.\ngrok.exe http 8000
```

### ❌ `ERR_NGROK_8012 - Agent failed to establish connection`
```
→ Python no está corriendo
→ Ejecuta "python run.py" en otra terminal
```

### ❌ Dashboard invisible/blanco
```
→ Anime.js error (arreglado en base.html)
→ Refresh (Ctrl+Shift+Del) cache
→ Verifica consola browser (F12)
```

---

## ESTRUCTURA CARPETAS IMPORTANTES

```
app/
├── routers/         ← Endpoints (GET/POST/PUT/DELETE)
├── schemas/         ← Validación Pydantic
├── services/        ← Lógica negocio
├── repositories/    ← Acceso datos
├── utils/           ← Helpers
└── database.py      ← Modelos BD

templates/
├── base.html        ← Maestra (CSS + JS global)
├── dashboard.html   ← Panel principal
├── clientes.html
├── prestamos.html
└── cobros.html

static/
├── css/
├── js/
├── manifest.json    ← PWA config
└── sw.js            ← Service Worker (offline)
```

---

## FLUJO DE AUTENTICACIÓN

```
1. Usuario ingresa login
2. POST /api/auth/login { username, password }
3. Backend:
   - Busca usuario en BD
   - Valida password (bcrypt)
   - Genera JWT token
4. Frontend:
   - Almacena token en localStorage
   - Incluye en header: Authorization: Bearer [TOKEN]
5. Todos los endpoints requieren token válido
6. Token expira en 24 horas → re-login
```

---

## MULTI-TENANCY (Aislamiento empresas)

**Clave:** `empresa_id` en TODAS las tablas

```python
# Backend valida automáticamente:
# - Usuario solo ve datos de su empresa
# - Queries filtran por empresa_id del usuario
# - DELETE en cascada elimina todo de esa empresa

# Ejemplo query:
prestamos = db.query(Prestamo).filter(
    Prestamo.empresa_id == usuario.empresa_id,
    Prestamo.estado == 'ACTIVO'
).all()
```

---

## DEPLOYMENT OPTIONS

### Opción 1: Local (tu PC) ✅ ACTUAL
```
- Ejecutar python run.py
- Acceso: http://localhost:8000
- Remoto: ngrok http 8000
```

### Opción 2: Railway (Recomendado)
```
1. Conectar repo a Railway.app
2. Config DATABASE_URL (PostgreSQL Railway)
3. Deploy automático en push
4. URL: https://creditospro-prod.railway.app
```

### Opción 3: Heroku (Deprecated)
```
1. Crear Procfile
2. git push heroku main
3. Monitorear: heroku logs -t
```

---

## PERFORMANCE TIPS

```python
# ❌ Malo - N+1 queries
for prestamo in prestamos:
    print(prestamo.cliente.nombre)  # Query por cada uno

# ✅ Bueno - Eager load
prestamos = db.query(Prestamo).options(
    joinedload(Prestamo.cliente)
).all()
```

---

## TESTING

```bash
# Ejecutar tests
pytest tests/

# Con coverage
pytest --cov=app tests/

# Tests específicos
pytest tests/test_security_hardening.py -v
```

---

## LOGS Y DEBUG

```python
# En terminal:
# Ver nivel "warning" (default)

# Cambiar en run.py:
uvicorn.run(..., log_level="debug")  # Más verboso

# Ver errores en browser:
# F12 → Console (JavaScript errors)
# F12 → Network (requests fallidos)
```

---

## VARIABLES DE ENTORNO IMPORTANTES

```env
DATABASE_URL          # Conexión BD (CRÍTICO)
SECRET_KEY            # Encriptación JWT (CRÍTICO)
PORT                  # Puerto servidor (default 8000)
DEBUG                 # True=desarrollo, False=producción
MACHINE_ID            # Auto-generado para licencias
LICENSE_CHECK         # Verificar licencia en startup
```

---

## BACKUP & RESTORE

```bash
# Backup BD SQLite
copy creditospro.db creditospro_backup_26-05-2026.db

# Restore
copy creditospro_backup_26-05-2026.db creditospro.db

# PostgreSQL backup
pg_dump -U user dbname > backup.sql

# PostgreSQL restore
psql -U user dbname < backup.sql
```

---

## CONTACTO RÁPIDO

**GitHub Copilot:** Este AI (Claude Haiku 4.5)
**Documentación:** `DOCUMENTACION_PROYECTO_IA.md`
**Cambios técnicos:** `RESUMEN_CAMBIOS_v3_0.md`
**Manual usuario:** `GUIA_USO_DIARIO.md`

---

**Última actualización:** 26/05/2026 ⏰
