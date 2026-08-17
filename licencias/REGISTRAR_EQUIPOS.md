# Registrar Equipos Adicionales

Esta guía te muestra cómo agregar nuevas máquinas al sistema de licencias de CreditosPro.

## 🎯 Flujo general

```
1. Nuevo Equipo           →  2. Obtener Machine ID  →  3. Equipo Administrativo
   (PC-OFICINA-02)          .exe/python renewal... → Registrar con register_equipment.py
                                                   → Generar licencia
                                                   
4. Transferir Licencia    →  5. Equipo Nuevo       →  6. Verificar
   (CPRO-...)               Activar con key        →  Funciona ✅
```

## 📋 Paso 1: Obtener el Machine ID del nuevo equipo

En la **nueva máquina**, ejecuta:

```powershell
# Si tienes CreditosPro instalado:
cd c:\Users\johan\Downloads\CreditosPro_DEPLOY
.\.venv\Scripts\python.exe renewal_license.py --myid

# O sin el proyecto:
python -c "import platform, socket, uuid, hashlib; parts = [str(uuid.getnode()), socket.gethostname(), platform.processor(), platform.machine(), platform.system()]; print(hashlib.sha256('|'.join(parts).encode()).hexdigest()[:32].upper())"
```

**Salida esperada:**
```
🖥️  Machine ID de este equipo:

  ABC123DEF456GHI789JKL012MNO345PQR
```

Copia este Machine ID.

## 🔑 Paso 2: Registrar el equipo (en máquina administrativa)

En la **máquina con acceso administrativo** (donde tienes el proyecto), ejecuta:

```powershell
cd c:\Users\johan\Downloads\CreditosPro_DEPLOY
.\.venv\Scripts\python.exe licencias\register_equipment.py register `
  --empresa "ElRusso" `
  --empresa-id 1 `
  --machine "ABC123DEF456GHI789JKL012MNO345PQR" `
  --equipo "PC-OFICINA-02"
```

**Nota:** Reemplaza:
- `ABC123DEF456...` con el Machine ID real
- `"PC-OFICINA-02"` con el nombre de tu equipo
- Si es otra empresa, cambiar empresa e empresa-id

**Salida esperada:**
```
📝 Registrando equipo: PC-OFICINA-02
  Empresa: ElRusso (ID: 1)
  Machine ID: ABC123DEF456GHI789JKL012MNO345PQR

======================================================================
✅ EQUIPO REGISTRADO EXITOSAMENTE
======================================================================

📋 Datos del equipo:
  Nombre: PC-OFICINA-02
  Machine ID: ABC123DEF456GHI789JKL012MNO345PQR
  Licencia válida hasta: 2027-08-16

🔑 LICENCIA (copia y envía al equipo):

CPRO-Z0FBQUFBQnFnbFB2ODJTM2Y1NE1fel81RVBsVUE0YlNrSzVkVzVGQ1o2VEZLLVlyd3djVFNoTl9...

======================================================================

También guardada en: C:\...\licencias\license_PC-OFICINA-02.txt
```

## 📥 Paso 3: Activar la licencia en el nuevo equipo

En el **nuevo equipo**, copia el archivo de licencia (o la clave CPRO-...) y ejecuta:

```powershell
cd c:\Users\johan\Downloads\CreditosPro_DEPLOY
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Luego abre en el navegador: http://127.0.0.1:8000/activar

O por línea de comandos:
```powershell
.\.venv\Scripts\python.exe activar_licencia.py --key "CPRO-..."
```

## ✅ Verificar que la licencia funciona

En el nuevo equipo:
```powershell
.\.venv\Scripts\python.exe -c "import os; from dotenv import load_dotenv; load_dotenv(); import license_manager; print(license_manager.check_license())"
```

Debe mostrar:
```python
{
  'machine_id': 'ABC123DEF456...',
  'empresa_id': 1,
  'empresa_nombre': 'ElRusso',
  'valid': True,
  'days_left': 364,
  ...
}
```

## 📊 Gestionar equipos registrados

### Listar todos los equipos de una empresa

```powershell
.\.venv\Scripts\python.exe licencias\register_equipment.py list --empresa "ElRusso"
```

**Salida:**
```
📊 Equipos de ElRusso:
================================================================================

  📱 PC-OFICINA-01
     Machine ID: 0C773FA2129C81EDB9E7921A7D421A0C
     Vencimiento: 2027-08-16 ✅ Activa
     Registrado: 2026-08-16

  📱 PC-OFICINA-02
     Machine ID: ABC123DEF456GHI789JKL012MNO345PQR
     Vencimiento: 2027-08-16 ✅ Activa
     Registrado: 2026-08-16
```

### Ver estado de un equipo específico

```powershell
.\.venv\Scripts\python.exe licencias\register_equipment.py status `
  --empresa "ElRusso" `
  --equipo "PC-OFICINA-02"
```

**Salida:**
```
📊 Estado de PC-OFICINA-02:
======================================================================
  Empresa: ElRusso
  Machine ID: ABC123DEF456GHI789JKL012MNO345PQR
  Vencimiento: 2027-08-16
  Activa: ✅ Sí
  Registrado: 2026-08-16
  Validación: ✅ VÁLIDA
  Días restantes: 364
```

### Exportar licencias (para backup o distribución)

```powershell
# Ver licencia de un equipo específico
.\.venv\Scripts\python.exe licencias\register_equipment.py export `
  --empresa "ElRusso" `
  --equipo "PC-OFICINA-02"

# Ver todas las licencias de una empresa
.\.venv\Scripts\python.exe licencias\register_equipment.py export `
  --empresa "ElRusso"
```

### Eliminar un equipo del registro

```powershell
.\.venv\Scripts\python.exe licencias\register_equipment.py delete `
  --empresa "ElRusso" `
  --equipo "PC-OFICINA-02"
```

## 📝 Importar licencia actual al registro

Si ya tienes una licencia activa en `.env` pero quieres registrarla en el sistema:

```powershell
.\.venv\Scripts\python.exe licencias\register_equipment.py import-env `
  --empresa "ElRusso" `
  --empresa-id 1 `
  --equipo "PC-PRINCIPAL"
```

## 🛠️ Casos especiales

### Cambiar de equipo (migración de licencia)

1. **En el equipo viejo:** Anotar la licencia (CPRO-...)
2. **En el nuevo equipo:** Obtener su Machine ID
3. **En máquina administrativa:** Registrar como equipo nuevo
4. **En el nuevo equipo:** Activar con la nueva licencia generada

### Múltiples empresas

Para otra empresa (ej: "Empresa2"):
```powershell
.\.venv\Scripts\python.exe licencias\register_equipment.py register `
  --empresa "Empresa2" `
  --empresa-id 2 `
  --machine "ABC123..." `
  --equipo "PC-EMPRESA2-01"
```

### Sin proyecto instalado (solo Machine ID)

Si necesitas el Machine ID sin tener CreditosPro:

**PowerShell:**
```powershell
$parts = @(
  [System.Guid]::NewGuid().ToString().Replace('-', ''),
  [System.Net.Dns]::GetHostName(),
  $env:PROCESSOR_IDENTIFIER,
  $env:PROCESSOR_ARCHITECTURE,
  $env:OS
)
$str = $parts -join '|'
$bytes = [System.Text.Encoding]::UTF8.GetBytes($str)
$hash = [System.Security.Cryptography.SHA256]::Create().ComputeHash($bytes)
[Convert]::ToHexString($hash).Substring(0, 32).ToUpper()
```

**Python puro:**
```python
import platform, socket, uuid, hashlib
parts = [str(uuid.getnode()), socket.gethostname(), 
         platform.processor(), platform.machine(), platform.system()]
print(hashlib.sha256('|'.join(parts).encode()).hexdigest()[:32].upper())
```

## 📂 Archivos generados

Después de registrar equipos, encontrarás:

```
licencias/
  equipos_registro.json          # Registro central de todos los equipos
  license_PC-OFICINA-01.txt      # Copia de la licencia
  license_PC-OFICINA-02.txt      # Copia de la licencia
  register_equipment.py          # Script de gestión
```

## ⚠️ Importante

✅ **Buenas prácticas:**
- Registrar cada equipo con un nombre único (ej: "PC-OFICINA-01", "LAPTOP-VENDEDOR-05")
- Guardar backup de `equipos_registro.json`
- Una máquina = una licencia única (Machine ID específico)
- Renovar todas las licencias juntas (anualmente)

❌ **Evitar:**
- Usar la misma licencia en múltiples equipos
- Perder el Machine ID (es imposible recuperarlo después)
- Compartir licencias sin encriptar
- Eliminar `equipos_registro.json` sin backup

---

Para más detalles sobre renovación anual, ver: [PLAN_RENOVACION_ANUAL.md](../PLAN_RENOVACION_ANUAL.md)
