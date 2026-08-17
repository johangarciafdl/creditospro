# Licencias por empresa y equipo

Esta carpeta está pensada para guardar la información de licencias por empresa y por equipo, sin mezclar todo en un único `.env`.

## Estructura recomendada

```text
licencias/
  ElRusso/
    PC-OFICINA-01/
      machine_id.txt
      licencia.txt
      vencimiento.txt
      metadata.json
    PC-OFICINA-02/
      machine_id.txt
      licencia.txt
      vencimiento.txt
      metadata.json
  Empresa2/
    Equipo-A/
      machine_id.txt
      licencia.txt
      vencimiento.txt
      metadata.json
```

## Flujo: Crear una licencia nueva

1. En el equipo destino, obtener el Machine ID:
   ```powershell
   .\.venv\Scripts\python.exe owner_tool.py myid
   ```
2. Generar la licencia para esa máquina y empresa:
   ```powershell
   .\.venv\Scripts\python.exe licencias\gestion_licencias.py generar --empresa "ElRusso" --equipo "PC-OFICINA-01" --empresa-id 1 --dias 365
   ```
3. La herramienta guarda la licencia y el Machine ID en la carpeta correspondiente.
4. Activar la licencia en la máquina:
   ```powershell
   .\.venv\Scripts\python.exe activar_licencia.py --key "CPRO-..."
   ```
5. Validar que el equipo coincida con la licencia:
   ```powershell
   .\.venv\Scripts\python.exe licencias\gestion_licencias.py validar --empresa "ElRusso" --equipo "PC-OFICINA-01"
   ```

## Flujo: Renovar licencia anualmente

La renovación es automática y simple. Tienes dos opciones:

### Opción 1: Renovación automática (recomendado)

Ejecuta en el equipo que ya tiene la licencia activa:

```powershell
.\.venv\Scripts\python.exe renewal_license.py --auto
```

Esto:
- Lee la licencia actual desde `.env` (CREDITOSPRO_LICENSE_KEY)
- Genera una nueva licencia con +365 días de validez
- Guarda la nueva licencia en `.env`
- Registra el cambio en `licencias/empresas.json`

### Opción 2: Renovación manual

Si necesitas generar una licencia para un equipo específico:

```powershell
.\.venv\Scripts\python.exe renewal_license.py --machine "ABC123DEF456..." --empresa-id 1 --empresa "ElRusso" --dias 365
```

Te dará la opción de guardar automáticamente en `.env` y en el registro de licencias.

### Validar una licencia antes de renovar

Para revisar cuántos días quedan antes de que expire:

```powershell
.\.venv\Scripts\python.exe renewal_license.py --validate "CPRO-..."
```

Muestra el estado actual, la empresa, el Machine ID y los días restantes.

## Planificación de renovaciones

**Recomendación**: Ejecuta `renewal_license.py --auto` **una vez al año** antes de que expire la licencia actual.

Para automatizar, puedes:
1. Crear una tarea programada en Windows (Task Scheduler) que ejecute el script anualmente
2. Configurar un recordatorio en tu calendario

## Importante

- Esta carpeta contiene información sensible y debe quedar fuera del repositorio público.
- La app valida la licencia en función del `Machine ID` real del equipo.
- No se debe reutilizar la misma licencia para equipos distintos.
- Guarda un backup de la licencia en un lugar seguro (ej: en contraseña maestra o nube personal).
