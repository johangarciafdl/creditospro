# Gestión Completa de Equipos y Licencias

## ✅ Sistema implementado

Se ha creado un sistema completo de gestión de licencias por empresa y equipo que te permite:

### 🎯 Funcionalidades principales

1. **Renovación Anual Automática** (`renewal_license.py`)
   - Renovar licencia con un solo comando: `renewal_license.py --auto`
   - Validar estado antes de renovar: `renewal_license.py --validate`
   - Generar licencias manuales para equipos específicos

2. **Registro de Múltiples Equipos** (`register_equipment.py`)
   - Registrar nuevos equipos: `register_equipment.py register`
   - Listar equipos: `register_equipment.py list`
   - Ver estado: `register_equipment.py status`
   - Exportar licencias: `register_equipment.py export`
   - Eliminar equipos: `register_equipment.py delete`

3. **Almacenamiento Centralizado** (`equipos_registro.json`)
   - Registro central de todos los equipos y licencias
   - Fácil de respaldar y transferir
   - Estructura clara para múltiples empresas

---

## 📁 Archivos creados

```
licencias/
├── register_equipment.py       ← Script principal de gestión de equipos
├── equipos_registro.json       ← Base de datos de equipos
├── REGISTRAR_EQUIPOS.md        ← Guía completa detallada
├── GUIA_RAPIDA_EQUIPOS.md      ← Guía de 3 pasos
├── README.md                   ← Documentación general (actualizado)
└── license_*.txt               ← Copias de licencias generadas
```

En raíz del proyecto:
```
├── renewal_license.py          ← Script de renovación anual
└── PLAN_RENOVACION_ANUAL.md    ← Guía de renovación anual
```

---

## 🔄 Flujos de trabajo

### Flujo 1: Agregar un equipo nuevo

```powershell
# 1. En el nuevo equipo
.\.venv\Scripts\python.exe renewal_license.py --myid
# Copia: ABC123DEF456...

# 2. En máquina administrativa
.\.venv\Scripts\python.exe licencias\register_equipment.py register `
  --empresa "ElRusso" --empresa-id 1 `
  --machine "ABC123DEF456..." --equipo "LAPTOP-VENDEDOR-01"
# Copia: CPRO-...

# 3. En el nuevo equipo (activar)
.\.venv\Scripts\python.exe activar_licencia.py --key "CPRO-..."
```

### Flujo 2: Renovar licencia cada año

```powershell
# Una vez al año (antes del vencimiento)
.\.venv\Scripts\python.exe renewal_license.py --auto

# La app sigue funcionando sin cambios
```

### Flujo 3: Consultar estado de equipos

```powershell
# Listar todos los equipos
.\.venv\Scripts\python.exe licencias\register_equipment.py list --empresa "ElRusso"

# Ver estado detallado
.\.venv\Scripts\python.exe licencias\register_equipment.py status --empresa "ElRusso" --equipo "PC-OFICINA-01"

# Exportar para respaldar
.\.venv\Scripts\python.exe licencias\register_equipment.py export --empresa "ElRusso"
```

---

## 📊 Estado actual del sistema

### Licencias activas

| Equipo | Machine ID | Expira | Estado |
|--------|-----------|--------|--------|
| PC-OFICINA-01 | 0C773FA2129C81EDB9E7921A7D421A0C | 2027-08-16 | ✅ Válida |
| LAPTOP-VENDEDOR-01 | LAPTOP123ABC456DEF789GHI012JKLM | 2027-08-16 | ✅ Válida |

### Próximas acciones

| Fecha | Acción |
|-------|--------|
| 2027-08-01 | Ejecutar: `renewal_license.py --auto` |
| 2027-08-16 | VENCE licencia anterior |
| Anualmente | Repetir renovación |

---

## 🛡️ Seguridad y respaldos

### Archivos críticos a respaldar

```
.env                              ← Contiene CREDITOSPRO_LICENSE_KEY
licencias/equipos_registro.json   ← Registro de todos los equipos
licencias/license_*.txt           ← Copias de licencias
```

**Comando de respaldo:**
```powershell
Copy-Item .env, "licencias\equipos_registro.json" -Destination "C:\MisBackups\creditospro_$(Get-Date -Format 'yyyyMMdd')"
```

### En caso de perder equipos_registro.json

Las licencias se regeneran automáticamente, pero el registro histórico se pierde. Por eso:
- ✅ Hacer backup semanal de `equipos_registro.json`
- ✅ Guardar copias de `license_*.txt`
- ✅ Documentar Machine IDs en lugar seguro

---

## 📚 Documentación disponible

- **PLAN_RENOVACION_ANUAL.md** - Cómo renovar cada año
- **licencias/REGISTRAR_EQUIPOS.md** - Guía completa de equipos
- **licencias/GUIA_RAPIDA_EQUIPOS.md** - Resumen de 3 pasos
- **licencias/README.md** - Documentación general
- **licencias/equipos_registro.json** - Estado actual

---

## ⚙️ Comandos más frecuentes

```powershell
# Ver Machine ID de este equipo
.\.venv\Scripts\python.exe renewal_license.py --myid

# Validar licencia actual
.\.venv\Scripts\python.exe renewal_license.py --validate "CPRO-..."

# Registrar nuevo equipo
.\.venv\Scripts\python.exe licencias\register_equipment.py register --empresa "ElRusso" --empresa-id 1 --machine "..." --equipo "..."

# Listar equipos
.\.venv\Scripts\python.exe licencias\register_equipment.py list --empresa "ElRusso"

# Ver estado de equipo
.\.venv\Scripts\python.exe licencias\register_equipment.py status --empresa "ElRusso" --equipo "PC-OFICINA-01"

# Renovar licencia anualmente
.\.venv\Scripts\python.exe renewal_license.py --auto

# Verificar que app está funcionando con licencia válida
.\.venv\Scripts\python.exe -c "import os; from dotenv import load_dotenv; load_dotenv(); import license_manager; print(license_manager.check_license())"
```

---

## 🎯 Próximos pasos opcionales

1. **Base de datos para muchas empresas** - Si tienes 100+ equipos, migrar a tabla SQL
2. **Sincronización en nube** - Respaldar automáticamente `equipos_registro.json`
3. **Panel administrativo** - Interfaz web para gestionar equipos (futuro)
4. **Auditoría de licencias** - Logs de cuándo se activó cada equipo

---

**¿Preguntas o necesitas modificaciones?** Usa los scripts con `--help` para ver todas las opciones.
