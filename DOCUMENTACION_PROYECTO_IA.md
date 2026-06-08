# 📋 DOCUMENTACIÓN COMPLETA DE CREDITOSPRO v3.0
**Última actualización:** 26 de mayo de 2026

---

## 1️⃣ DESCRIPCIÓN GENERAL DEL PROYECTO

### ¿Qué es CreditosPro?
**CreditosPro v3.0** es una **aplicación web empresarial multi-tenant** (SaaS) diseñada para gestionar **créditos, préstamos, cobros y cobradores** en múltiples empresas de forma simultánea con aislamiento total de datos.

**Caso de uso principal:** Administrar cartera de créditos para prestamistas, financieras o empresas de comercio electrónico que otorgan crédito a clientes.

**Principales características:**
- ✅ Multi-empresa (cada empresa tiene datos 100% aislados)
- ✅ Gestión de clientes, préstamos, cobros y zonas de venta
- ✅ Sistema de usuarios con roles (admin, gerente, cobrador)
- ✅ Reportes financieros y análisis de cartera
- ✅ Acceso móvil para cobradores en terreno
- ✅ Sistema de licencias con verificación de máquina

---

## 2️⃣ STACK TECNOLÓGICO

### Backend
```
Lenguaje:         Python 3.11+
Framework Web:    FastAPI (moderno, rápido, auto-documentado)
Servidor:         Uvicorn (ASGI)
Base de Datos:    SQLite (desarrollo) / PostgreSQL (producción)
ORM:              SQLAlchemy 2.0+
Autenticación:    JWT (JSON Web Tokens)
Validación:       Pydantic v2
```

### Frontend
```
Motor de plantillas:  Jinja2 (templates HTML dinámicos)
JavaScript:          Vanilla JS (sin frameworks pesados)
Librerías:          
  - Anime.js (animaciones suaves)
  - Chart.js (gráficos)
  - DataTables (tablas interactivas)
CSS:                Bootstrap 5 + CSS personalizado
```

### Infraestructura
```
Despliegue local:     Windows PC (Python virtualenv)
Despliegue remoto:    Railway, Heroku o servidor Linux
Puerto por defecto:   8000
Proxy remoto:         ngrok (para acceso móvil desde cualquier lugar)
```

### Migraciones
```
Herramienta:          Alembic
Ubicación:            /app/alembic/
Comando:              alembic upgrade head
```

---

## 3️⃣ ARQUITECTURA DE LA APLICACIÓN

### Estructura de carpetas
```
CreditosPro_v2/
├── app/                          # Aplicación principal
│   ├── __init__.py
│   ├── main.py                   # Punto de entrada FastAPI
│   ├── database.py               # Modelos SQLAlchemy (Empresa, Usuario, etc)
│   ├── routers/                  # Endpoints de la API
│   │   ├── auth.py              # Login, registro
│   │   ├── dashboard.py         # Panel principal
│   │   ├── clientes.py          # CRUD de clientes
│   │   ├── prestamos.py         # CRUD de préstamos
│   │   ├── cobros.py            # CRUD de cobros/pagos
│   │   ├── reportes.py          # Reportes y estadísticas
│   │   ├── zonas.py             # Zonas de venta
│   │   ├── whatsapp.py          # Integración WhatsApp
│   │   ├── license_router.py    # Manejo de licencias
│   │   └── pwa.py               # Progressive Web App
│   ├── schemas/                 # Modelos Pydantic (validación)
│   │   ├── usuario.py
│   │   ├── cliente.py
│   │   ├── prestamo.py
│   │   └── ...
│   ├── services/                # Lógica de negocio
│   │   ├── prestamo_service.py
│   │   ├── excel_service.py
│   │   ├── whatsapp_service.py
│   │   └── scheduler.py         # Tareas programadas
│   ├── utils/                   # Utilidades
│   │   ├── license.py           # Manejo de licencias
│   │   ├── csrf.py              # Protección CSRF
│   │   ├── money.py             # Operaciones monetarias
│   │   └── license_middleware.py
│   └── repositories/            # Acceso a datos (patrón repository)
├── templates/                    # HTML Jinja2
│   ├── base.html                # Plantilla maestra
│   ├── dashboard.html
│   ├── clientes.html
│   ├── prestamos.html
│   ├── cobros.html
│   ├── reportes.html
│   └── auth/
├── static/                      # Recursos estáticos
│   ├── css/
│   ├── js/
│   ├── icons/
│   ├── manifest.json           # PWA manifest
│   └── sw.js                   # Service Worker
├── run.py                       # Script para iniciar servidor
├── requirements.txt             # Dependencias Python
├── .env                        # Variables de entorno (NO en Git)
├── alembic.ini                 # Configuración migraciones
└── tests/                      # Tests automatizados
```

---

## 4️⃣ MODELOS DE DATOS (Base de Datos)

### Relaciones principales
```
EMPRESA (1)
├── (1:N) USUARIO
├── (1:N) ZONA
├── (1:N) CLIENTE
└── (1:N) PRESTAMO
    └── (1:N) COBRO
```

### Tablas principales

#### **Empresa** (Empresas del sistema)
```python
id:                 INTEGER PRIMARY KEY
nombre:             VARCHAR (ej: "ElRuso", "Juansmart")
ciudad:             VARCHAR
país:               VARCHAR
moneda:             VARCHAR (ej: "USD")
activa:             BOOLEAN (default: True)
plan:               VARCHAR (ej: "BASICO", "PROFESIONAL")
```

#### **Usuario** (Trabajadores)
```python
id:                 INTEGER PRIMARY KEY
empresa_id:         INTEGER FK → Empresa.id
username:           VARCHAR UNIQUE (global)
password_hash:      VARCHAR
rol:                VARCHAR (ADMIN, GERENTE, COBRADOR)
activo:             BOOLEAN
nombre_completo:    VARCHAR
email:              VARCHAR
```

**Usuarios por defecto:**
- `johan` / `XXXXXX` → ADMIN (acceso total)
- `julian` / `197991` → GERENTE (todo menos config)
- `marcos` / `Marcos123` → COBRADOR (solo registrar cobros)

#### **Zona** (Territorios de venta)
```python
id:                 INTEGER PRIMARY KEY
empresa_id:         INTEGER FK
código:             VARCHAR (ej: "Z01")
nombre:             VARCHAR (ej: "Centro")
ciudad:             VARCHAR
activa:             BOOLEAN
```

#### **Cliente** (Deudores)
```python
id:                 INTEGER PRIMARY KEY
empresa_id:         INTEGER FK
nombre:             VARCHAR
teléfono:           VARCHAR
dirección:          VARCHAR
ciudad:             VARCHAR
estado:             VARCHAR (ACTIVO, CANCELADO, MOROSO)
created_at:         DATETIME
```

#### **Préstamo** (Crédito otorgado)
```python
id:                 INTEGER PRIMARY KEY
empresa_id:         INTEGER FK
cliente_id:         INTEGER FK
monto:              NUMERIC (monto original)
plazo:              INTEGER (meses)
tasa:               NUMERIC (% de interés)
estado:             VARCHAR (ACTIVO, PAGADO, CANCELADO)
created_at:         DATETIME
vencimiento:        DATETIME
```

#### **Cobro** (Pago registrado)
```python
id:                 INTEGER PRIMARY KEY
empresa_id:         INTEGER FK
préstamo_id:        INTEGER FK
monto:              NUMERIC
fecha:              DATETIME
método:             VARCHAR (EFECTIVO, TRANSFERENCIA, CHEQUE)
usuario_id:         INTEGER (cobrador que registró)
nota:               VARCHAR (opcional)
```

---

## 5️⃣ ROLES Y PERMISOS

| Rol | Dashboard | Ver Clientes | Crear Préstamo | Registrar Cobro | Ver Reportes | Gestionar Usuarios | Configuración |
|-----|-----------|--------------|----------------|-----------------|--------------|-------------------|---------------|
| **ADMIN** | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| **GERENTE** | ✅ | ✅ | ✅ | ✅ | ✅ | ❌ | ❌ |
| **COBRADOR** | ✅ | ✅ | ❌ | ✅ | ❌ | ❌ | ❌ |

---

## 6️⃣ FLUJOS PRINCIPALES

### Flujo 1: Crear un Préstamo
```
1. Gerente/Admin entra a CLIENTES
2. Busca cliente o crea uno nuevo
3. Va a PRÉSTAMOS → "Nuevo Préstamo"
4. Ingresa:
   - Monto inicial
   - Plazo (meses)
   - Tasa de interés
   - Fecha de vencimiento
5. Sistema calcula automáticamente:
   - Cuota mensual
   - Interés total
   - Tabla de amortización
6. Se guarda en BD con estado ACTIVO
```

### Flujo 2: Registrar Cobro (Cobrador en terreno)
```
1. Cobrador abre CreditosPro desde celular
2. Ve lista de clientes en su zona
3. Selecciona cliente → ver préstamo activo
4. Ingresa:
   - Monto del pago
   - Método (efectivo, transferencia, etc)
   - Nota (opcional)
5. Sistema:
   - Reduce saldo pendiente
   - Genera comprobante
   - Actualiza estado si está pagado
6. Registra automáticamente quién cobró y cuándo
```

### Flujo 3: Ver Reportes
```
1. Admin/Gerente va a REPORTES
2. Opciones:
   - Cartera vencida (cuánto está atrasado)
   - Cobranza del mes (cuánto se cobró)
   - Clientes morosos
   - Zona de mayor cartera
3. Gráficos interactivos con Chart.js
4. Exportar a Excel
```

---

## 7️⃣ TECNOLOGÍAS CLAVE Y POR QUÉ

### FastAPI (Backend)
**Por qué:** 
- Moderno, rápido (2x Django)
- Auto-genera documentación Swagger
- Validación automática con Pydantic
- Soporta WebSockets para tiempo real
- Excelente para APIs REST y web tradicional

### SQLAlchemy ORM
**Por qué:**
- Abstracción de BD (cambiar de SQLite a PostgreSQL sin código)
- Relaciones automáticas
- Migraciones con Alembic
- Queries expresivas y seguras (SQL injection protection)

### JWT para autenticación
**Por qué:**
- Stateless (no necesita sesiones en servidor)
- Perfecto para apps móviles
- Escalable (sin base de datos de sesiones)
- Token incluye datos del usuario (sin nueva query)

### Jinja2 + Vanilla JS
**Por qué:**
- Renderizado server-side (tradicional, pero funciona sin JS)
- Sin dependencias pesadas (npm, node_modules)
- Rápido y directo
- PWA compatible (funciona offline)

### Service Worker + Anime.js
**Por qué:**
- Permite funcionamiento offline parcial
- Animaciones suaves sin librerías pesadas
- Cache inteligente de assets

---

## 8️⃣ VARIABLES DE ENTORNO (.env)

```env
# Base de datos (CRÍTICO)
DATABASE_URL=sqlite:///./creditospro.db
# O para PostgreSQL:
# DATABASE_URL=postgresql://user:pass@localhost/creditospro

# Seguridad
SECRET_KEY=tu-clave-super-secreta-aqui-minimo-32-caracteres

# Servidor
PORT=8000
DEBUG=False

# Licencias
LICENSE_CHECK=True
MACHINE_ID=auto  # Se genera automáticamente

# WhatsApp (opcional)
TWILIO_ACCOUNT_SID=xxxx
TWILIO_AUTH_TOKEN=xxxx
TWILIO_PHONE_NUMBER=+1234567890

# Email (opcional)
SMTP_SERVER=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=tu@gmail.com
SMTP_PASSWORD=app-password
```

⚠️ **IMPORTANTE:** `.env` NUNCA se sube a Git (está en `.gitignore`)

---

## 9️⃣ CÓMO EJECUTAR EL PROYECTO

### Opción 1: Local (en tu PC)
```powershell
# 1. Ir a la carpeta
cd C:\Users\johan\Downloads\CreditosPro_FINAL\CreditosPro_v2_seguro_base\CreditosPro_v2

# 2. Crear virtualenv (si no existe)
python -m venv venv
venv\Scripts\activate

# 3. Instalar dependencias
pip install -r requirements.txt

# 4. Crear/actualizar BD
alembic upgrade head

# 5. Ejecutar servidor
python run.py

# Resultado:
# Servidor corriendo en http://127.0.0.1:8000
# Se abre navegador automáticamente
```

### Opción 2: Acceso remoto (ngrok)
```powershell
# Terminal 1: Python
python run.py

# Terminal 2: ngrok (desde carpeta ngrok)
ngrok http 8000

# Resultado:
# https://xxxxx.ngrok-free.dev → http://localhost:8000
# Funciona desde cualquier lugar del mundo
```

### Opción 3: Producción (Railway/Heroku)
```bash
# 1. Crear archivo Procfile
web: gunicorn app.main:app

# 2. Conectar repo a Railway/Heroku
# 3. Auto-despliega en cada push a main
```

---

## 🔟 ENDPOINTS PRINCIPALES DE LA API

### Autenticación
```
POST   /api/auth/register       - Registrar usuario
POST   /api/auth/login          - Login (devuelve JWT)
GET    /api/auth/me             - Usuario actual
POST   /api/auth/logout         - Logout
```

### Clientes
```
GET    /api/clientes            - Listar (multi-tenant: solo de su empresa)
POST   /api/clientes            - Crear
GET    /api/clientes/{id}       - Detalle
PUT    /api/clientes/{id}       - Actualizar
DELETE /api/clientes/{id}       - Eliminar
```

### Préstamos
```
GET    /api/prestamos           - Listar con filtros
POST   /api/prestamos           - Crear
GET    /api/prestamos/{id}      - Detalle + tabla amortización
PUT    /api/prestamos/{id}      - Actualizar
GET    /api/prestamos/{id}/cobros - Cobros registrados
```

### Cobros
```
POST   /api/cobros              - Registrar cobro
GET    /api/cobros              - Listar cobros
GET    /api/cobros/reporte      - Reportes de cobranza
```

### Reportes
```
GET    /api/reportes/cartera    - Análisis de cartera
GET    /api/reportes/cobranza   - Cobranza del período
GET    /api/reportes/morosos    - Clientes morosos
GET    /api/reportes/zonas      - Análisis por zona
```

---

## 1️⃣1️⃣ PROBLEMAS RESUELTOS (Mayo 2026)

### Problema 1: Duplicate Companies (IDs 1 y 20 - ElRuso)
**Causa:** Múltiples intentos de crear la empresa durante development
**Solución:** Script `limpiar_elruso_duplicado.py` que elimina duplicados
**Status:** ✅ Resuelto (script creado, listo para ejecutar)

### Problema 2: Dashboard Invisible ("Ninja 2" Error)
**Causa:** Anime.js (CDN) fallaba, pero HTML ocultaba elementos con opacity:0
**Síntomas:** Interfaz carga pero no se ve (invisible)
**Solución:** 
- Polyfill de Anime.js
- Timeout de 1.5s que fuerza visibilidad
- Try-catch en todas las animaciones
**Status:** ✅ Resuelto en `templates/base.html`

### Problema 3: Acceso móvil para cobradores
**Solución:** ngrok (túnel seguro que expone localhost a internet)
**Flujo:**
```
1. Ejecutar: python run.py (en PC)
2. Ejecutar: ngrok http 8000 (en otra terminal)
3. Dar link a cobrador (ej: https://xxxxx.ngrok-free.dev)
4. Cobrador abre en celular y trabaja en tiempo real
```
**Status:** ✅ Funcional

---

## 1️⃣2️⃣ SEGURIDAD IMPLEMENTADA

✅ **Autenticación:** JWT tokens con expiración
✅ **Autorización:** Role-based access control (RBAC)
✅ **Multi-tenancy:** Isolation total de datos por empresa
✅ **CSRF:** Tokens CSRF en formularios
✅ **SQL Injection:** ORM + Pydantic validación
✅ **Password:** Hash con bcrypt
✅ **HTTPS:** Soportado en producción
✅ **Licencias:** Verificación de máquina en arranque
✅ **Integridad de Scripts:** Subresource integrity (SRI) para CDN

---

## 1️⃣3️⃣ CARACTERÍSTICAS AVANZADAS

### PWA (Progressive Web App)
- Funciona sin internet (offline-first)
- Se puede instalar como app
- Sync automático cuando vuelve conexión
- Notificaciones push

### WhatsApp Integration
- Enviar cobros pendientes por WhatsApp
- Confirmaciones automáticas
- Recordatorios de vencimiento

### Reportes Excel
- Exportar cartera completa
- Gráficos automáticos
- Análisis pivottable

### Scheduler de tareas
- Recordatorios automáticos
- Cálculo diario de intereses
- Marcar como morosos después de X días

---

## 1️⃣4️⃣ DEPENDENCIAS CLAVE (requirements.txt)

```
fastapi==0.104.1        # Framework web
uvicorn==0.24.0         # Servidor ASGI
sqlalchemy==2.0.23      # ORM
alembic==1.12.0         # Migraciones BD
pydantic==2.5.0         # Validación
python-dotenv==1.0.0    # Variables de entorno
jinja2==3.1.2           # Templates HTML
bcrypt==4.1.1           # Encriptación passwords
pyjwt==2.8.1            # JWT tokens
python-multipart==0.0.6 # Form data
aiofiles==23.2.1        # Archivos async
openpyxl==3.11.0        # Exportar Excel
```

---

## 1️⃣5️⃣ ESTADO ACTUAL (26 de mayo 2026)

### ✅ Completado
- Arquitectura multi-tenant funcional
- CRUD completo (clientes, préstamos, cobros)
- Sistema de reportes
- Autenticación JWT
- Dashboard con gráficos
- PWA funcional
- Fixes de interfaz (base.html)
- Acceso móvil via ngrok

### ⚠️ Pendiente
- [ ] Ejecutar `limpiar_elruso_duplicado.py` en producción
- [ ] Sincronizar cambios a PC secundaria (si existe)
- [ ] Pruebas con cobrador real en terreno
- [ ] Validar offline sync en celular

### 🚫 No implementado
- Integración Stripe/PaymentMethod
- SMS automáticos (solo WhatsApp)
- Versionado de cambios (audit trail)

---

## 1️⃣6️⃣ PRÓXIMOS PASOS RECOMENDADOS

### Phase 1 (Inmediato)
```bash
# Ejecutar cleanup
python limpiar_elruso_duplicado.py

# Reiniciar servidor
python run.py
```

### Phase 2 (Esta semana)
```
- Prueba con cobrador Marcos en calle
- Verificar que registra cobros sin problema
- Confirmar sync de datos
```

### Phase 3 (Este mes)
```
- Entrenar a todos los cobradores
- Migrar cartera completa
- Monitorear performance
```

---

## 1️⃣7️⃣ CONTACTO / SOPORTE

**Desarrollador:** Johan Sebastian Garcia Vilar
**Email:** johansebastiangarciavilar@gmail.com
**GitHub:** [repositorio privado]

**Documentación adicional:**
- `RESUMEN_CAMBIOS_v3_0.md` - Cambios técnicos detallados
- `GUIA_USO_DIARIO.md` - Manual de usuario final
- `ACCESO_COBRADORES_FINAL.md` - Setup para cobradores

---

**Fin de documentación** 📚
Generado: 26/05/2026 - CreditosPro v3.0
