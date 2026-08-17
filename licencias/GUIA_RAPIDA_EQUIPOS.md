# 🚀 Guía Rápida: Registrar Equipos Adicionales

## En 3 pasos

### 1️⃣ Nuevo equipo → Obtener Machine ID

```powershell
.\.venv\Scripts\python.exe renewal_license.py --myid
```

**Copia el resultado**

### 2️⃣ Máquina administrativa → Registrar

```powershell
.\.venv\Scripts\python.exe licencias\register_equipment.py register `
  --empresa "ElRusso" --empresa-id 1 `
  --machine "ABC123..." --equipo "LAPTOP-VENDEDOR-01"
```

**Copia la licencia (CPRO-...)**

### 3️⃣ Nuevo equipo → Activar

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Luego: http://127.0.0.1:8000/activar → pega CPRO-...

---

## 📊 Ver equipos registrados

```powershell
# Listar todos
.\.venv\Scripts\python.exe licencias\register_equipment.py list --empresa "ElRusso"

# Estado de uno
.\.venv\Scripts\python.exe licencias\register_equipment.py status --empresa "ElRusso" --equipo "PC-OFICINA-01"

# Exportar licencias
.\.venv\Scripts\python.exe licencias\register_equipment.py export --empresa "ElRusso"
```

---

## 📋 Estado actual

**Empresa ElRusso:**
- ✅ PC-OFICINA-01 (0C773FA2129C81EDB9E7921A7D421A0C) → Vence 2027-08-16
- ✅ LAPTOP-VENDEDOR-01 (LAPTOP123ABC456DEF789GHI012JKLM) → Vence 2027-08-16

---

**Para más detalles:** Ver [REGISTRAR_EQUIPOS.md](REGISTRAR_EQUIPOS.md)
