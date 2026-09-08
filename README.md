# CreditosPro

Sistema de gestión de créditos y cobros multi-empresa (FastAPI + PostgreSQL/Supabase), pensado para una operadora de microcréditos con cobradores en campo. Incluye panel web para administración, PWA para cobradores en celular, recordatorios por WhatsApp (Green API) y sincronización offline.

> Para arquitectura técnica, comandos de desarrollo y convenciones de código, ver [CLAUDE.md](CLAUDE.md). Este documento es la guía operativa: instalación, uso diario, acceso remoto y mantenimiento.

## Índice

- [Primer uso / instalación](#primer-uso--instalación)
- [Uso diario](#uso-diario)
- [Acceso desde el celular (cobradores)](#acceso-desde-el-celular-cobradores)
- [Acceso sin la WiFi de la oficina](#acceso-sin-la-wifi-de-la-oficina)
- [Trabajo offline](#trabajo-offline)
- [Sincronizar entre dos equipos](#sincronizar-entre-dos-equipos)
- [Agregar una empresa nueva](#agregar-una-empresa-nueva)
- [Activar una empresa (licenciamiento)](#activar-una-empresa-licenciamiento)
- [Scripts de mantenimiento](#scripts-de-mantenimiento)
- [Backups](#backups)
- [Despliegue](#despliegue)
- [Seguridad](#seguridad)
- [Estructura del proyecto](#estructura-del-proyecto)
- [Solución de problemas](#solución-de-problemas)

## Primer uso / instalación

Requisitos: Windows 7+, [Python 3.11+](https://python.org/downloads) (marca **"Add Python to PATH"** durante la instalación), conexión a internet.

```powershell
cd C:\ruta\a\CreditosPro
pip install -r requirements.txt

# Copia .env.example a .env y completa DATABASE_URL, SECRET_KEY, SESSION_SECRET_KEY
copy .env.example .env
```

Primer arranque:

```powershell
python run.py
```

Se abre Chrome automáticamente. Si no tienes usuarios todavía, créalos desde el panel de administración (`/auth/usuarios`) una vez que hayas iniciado sesión con el primer admin creado durante el registro de la empresa.

## Uso diario

**Opción recomendada — acceso directo en el escritorio:**

1. Doble clic en `crear_acceso_directo.bat` (una sola vez).
2. Desde entonces, doble clic en el ícono **CreditosPro** del escritorio para iniciar sin ver ninguna terminal.

**Inicio automático al encender el PC** (opcional): doble clic en `setup_inicio_automatico.bat`. Para desactivarlo: `Win + R` → `shell:startup` → borra el acceso directo `CreditosPro`.

**Manual:** doble clic en `Iniciar CreditosPro.bat`, o `python run.py` desde PowerShell.

Al iniciar, la consola muestra las URLs disponibles:

```
Acceso local:        http://127.0.0.1:8000
Desde otros PCs:     http://<tu-IP-local>:8000
Celular en WiFi:     http://<tu-IP-local>:8000
```

## Acceso desde el celular (cobradores)

Requiere que el celular esté en la **misma red WiFi** que el PC donde corre CreditosPro.

1. En el PC, obtén tu IP local: `ipconfig` (PowerShell) → busca "Dirección IPv4" (ej. `192.168.1.50`).
2. En el celular, abre Chrome y entra a `http://<esa-IP>:8000`.
3. Chrome ofrece "Agregar a pantalla de inicio" / "Instalar aplicación" — acéptalo para que funcione como app nativa.
4. Inicia sesión con tu usuario y contraseña.

Si la IP cambia (reinicio del router, DHCP), repite el paso 1 — es lo único que cambia.

## Acceso sin la WiFi de la oficina

Si el cobrador está en la calle y no puede llegar a la WiFi del PC, crea un **hotspot móvil** desde el PC (requiere que el PC tenga internet propio, por WiFi o datos):

**Windows 11 / 10:** Configuración → Red e Internet → *Punto de acceso móvil* (Windows 10: *Hotspot móvil*) → configura un nombre y una contraseña fuerte → actívalo.

El celular se conecta a esa red igual que a cualquier WiFi, y luego entra a `http://<IP-del-hotspot>:8000` (usualmente `192.168.137.1` o similar; verifica con `ipconfig` en el PC tras activar el hotspot).

Alternativa: si el PC no tiene internet propio, se puede compartir el hotspot del **celular del administrador** y conectar el PC a esa red en vez de al revés.

## Trabajo offline

La PWA cachea datos mientras el cobrador tiene señal, y permite seguir consultando clientes/cuotas y registrar cobros sin conexión; los cambios se sincronizan solos al recuperar la red. Para que esto funcione bien:

1. Por la mañana, con WiFi/datos disponibles, abre la app normalmente para que el celular descargue los datos del día.
2. En la calle, sin señal, sigue usando la app — los cobros registrados quedan guardados localmente.
3. Al recuperar conexión (de vuelta en la oficina, o con datos móviles), la app sincroniza automáticamente.

Si el celular no tiene datos móviles ni acceso a la WiFi del PC en ningún momento del día, no hay forma de sincronizar en tiempo real — la alternativa es anotar los cobros y registrarlos manualmente al volver a tener acceso.

## Sincronizar entre dos equipos

Para propagar cambios puntuales (por ejemplo una plantilla actualizada) entre dos instalaciones de CreditosPro sin repetir todo el proceso de instalación:

- **Por red local:** `sync_archivos.ps1` (PowerShell) o `sync_archivos.bat` (CMD) — pide la IP, usuario y ruta del otro equipo, y copia solo lo necesario.
- **Por USB:** `copiar_a_usb.ps1` / `copiar_a_usb.bat` — detecta la unidad USB conectada y copia los archivos allí; luego se copian manualmente al otro equipo.

Ambos métodos requieren que la carpeta compartida en el otro PC exista y tenga permisos de escritura (por red) o que tengas acceso físico al otro equipo (por USB).

## Agregar una empresa nueva

CreditosPro ya es multi-empresa por diseño: todas las empresas conviven en la **misma base de datos y el mismo despliegue**, aisladas entre sí por `empresa_id` (reforzado con Row-Level Security en Postgres — ver [Seguridad](#seguridad)). Para dar de alta una empresa nueva **no hace falta escribir ni una línea de código**:

1. Activa temporalmente el registro público: en `.env` (o en las variables de entorno de Railway), pon `ALLOW_PUBLIC_REGISTRATION=1` y reinicia/redeploy.
2. Entra a `/registro` y llena el formulario: nombre de la empresa, y los datos del primer usuario (queda como `admin` de esa empresa). Esto crea automáticamente la empresa, su configuración por defecto, una "Zona Principal" y el usuario admin — todo en un solo paso, vía formulario web.
3. Vuelve a poner `ALLOW_PUBLIC_REGISTRATION=0` (o quita la variable) y reinicia — así nadie más puede autoregistrarse sin que tú lo decidas.
4. Genera su clave comercial (ver [Activar una empresa](#activar-una-empresa-licenciamiento) abajo) y entrégasela.

Desde el panel de esa empresa, el admin puede crear sus propias zonas, cobradores y clientes — no necesita que tú hagas nada más.

**Alternativa avanzada — instalación separada:** si un cliente necesita su **propia base de datos aislada** (no compartir instancia con las demás empresas), usa en cambio:

```powershell
python scripts\crear_empresa.py --fuente "C:\ruta\al\proyecto" --empresa "Nombre Empresa" --id <id>
```

Esto scaffoldea una carpeta y `.env` completos para un despliegue 100% independiente (su propia base de datos, su propio proceso). Es más trabajo de infraestructura — solo úsalo si de verdad necesitas esa separación física, no para el caso normal de "una empresa más" en el mismo sistema.

## Activar una empresa (licenciamiento)

La activación es **por empresa**, no por equipo — no hay licencias atadas a un hardware específico.

```powershell
python scripts\crear_clave_empresa.py --empresa-id <id>
```

Esto genera una clave (se muestra una sola vez; la base solo guarda su hash) que el cliente ingresa en `/license/activar`. Para rotar una clave ya entregada: agrega `--rotar`.

## Scripts de mantenimiento

Viven en [`scripts/`](scripts/) — se ejecutan con `python scripts\<nombre>.py` desde la raíz del proyecto:

| Script | Para qué sirve |
|---|---|
| `crear_clave_empresa.py` | Genera/rota la clave de activación de una empresa |
| `crear_empresa.py` | Scaffolding de una instalación nueva para otra empresa |
| `crear_indices.py` / `crear_indices.sql` | Crea índices de rendimiento en la base de datos |
| `diagnostico_supabase.py` | Verifica conexión e integridad de datos en Supabase |
| `backup_supabase.py` | Backup lógico (JSON + CSV + manifiesto verificado) de todas las tablas |
| `backup_supabase_cron.py` | Wrapper de `backup_supabase.py` para tareas programadas (comprime, sube a S3/R2 opcionalmente, purga backups viejos) |
| `limpiar_empresas.py` | Elimina todas las empresas excepto la indicada (uso puntual, pide confirmación) |
| `limpiar_elruso_duplicado.py` | Limpieza puntual de un registro duplicado de ElRusso |
| `normalizar_empresa_elrusso.py` | Deja la base en modo una sola empresa (ElRusso) |
| `setup_empresa_elruso.py` | Crea/actualiza los usuarios de la empresa ElRusso |
| `migracion_crear_cuotas.py` | Genera cuotas faltantes para préstamos que no las tengan |
| `prueba_rapida.py` / `simulacion_financiera.py` | Scripts de verificación y simulación, sin efectos en datos reales |

Varios de estos son específicos de la operación de ElRusso (una sola empresa) — no son necesarios para una instalación multi-empresa genérica.

## Backups

```powershell
python scripts\backup_supabase.py
# o, con retención y compresión automática:
python scripts\backup_supabase_cron.py --retention-days 30
```

Genera una carpeta en `backups/` con JSON y CSV por tabla más un `manifest.json` con conteos verificados. Para automatizarlo, programa `backup_supabase_cron.py` en el Programador de tareas de Windows (`schtasks`) o cron en Linux — ver el docstring del script para el comando exacto.

## Despliegue

En producción, CreditosPro corre contra PostgreSQL (Supabase). El contenedor Docker (`Dockerfile`, `start.sh`) expone el puerto 8000 vía `uvicorn app.main:app`, apto para Railway (`Procfile`, `nixpacks.toml`) u otro host compatible con contenedores. Las migraciones de base de datos (`alembic upgrade head`) son un paso manual — no corren automáticamente en cada deploy.

## Seguridad

- El aislamiento entre empresas usa Row-Level Security de PostgreSQL además del filtrado por `empresa_id` en el código — ver `rls_policies.sql` y `DATABASE_URL_APP` en `.env.example`.
- Autenticación con JWT en cookie HttpOnly, 2FA opcional (TOTP + códigos de respaldo), rate limiting por IP y por usuario en el login.
- **Pendiente de tu parte:** varios documentos antiguos (ya eliminados de este repo) tenían contraseñas reales de usuarios en texto plano. Si `julian` o `marcos` siguen usando las contraseñas que aparecían en esos archivos, cámbialas desde el panel de usuarios lo antes posible.
- Para detalles de arquitectura de seguridad (RLS, roles, auditoría), ver [CLAUDE.md](CLAUDE.md).

## Estructura del proyecto

```
CreditosPro/
├── app/                    Código de la aplicación (FastAPI)
├── templates/              Plantillas HTML (Jinja2)
├── static/                 CSS, JS, PWA (manifest, service worker)
├── alembic/                Migraciones de base de datos
├── tests/                  Suite de pruebas (pytest)
├── scripts/                Scripts de mantenimiento (ver arriba)
├── backups/                Backups generados (no versionado)
├── uploads/                Fotos de clientes subidas (no versionado)
├── run.py                  Punto de entrada local (Windows)
├── administrador.py        App de escritorio opcional (ver BUILD.bat)
├── Iniciar CreditosPro.bat Inicio diario sin terminal visible
├── rls_policies.sql        Políticas de aislamiento por empresa (Postgres)
└── README.md / CLAUDE.md   Esta guía / guía técnica para desarrollo
```

## Solución de problemas

**"Python no está instalado"** — instala desde [python.org](https://python.org/downloads) marcando "Add Python to PATH", reinicia el script.

**"Puerto 8000 ya en uso"** — cierra el otro programa, o cambia `PORT=8001` en `.env`.

**El celular no carga la página** — confirma que ambos dispositivos están en la misma red WiFi, que `python run.py` sigue corriendo (debe decir "Uvicorn running on..."), y que escribiste `http://` (no `https://`) seguido de la IP correcta.

**Dashboard en blanco o sin estilos** — refresca con `Ctrl+Shift+R`, revisa la consola del navegador (F12) por errores, y confirma que `static/` se sirve correctamente.

**Error al ejecutar un script de `scripts/`** — todos se ejecutan desde la raíz del proyecto: `python scripts\nombre.py`, no desde dentro de la carpeta `scripts`.
