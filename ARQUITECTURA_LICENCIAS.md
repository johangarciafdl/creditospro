# 🎯 Arquitectura completa de Licencias y Equipos

## 📊 Diagrama del Sistema Actual

```
┌─────────────────────────────────────────────────────────────────┐
│                   GESTIÓN DE LICENCIAS CREDITOSPRO              │
│                     (3 Capas Funcionales)                        │
└─────────────────────────────────────────────────────────────────┘

CAPA 1: GENERACIÓN Y VALIDACIÓN (license_manager.py, owner_tool.py)
═══════════════════════════════════════════════════════════════════
  Machine ID           Master Key           License Payload
     ↓                    ↓                      ↓
  [Fingerprint]  +  [SECRET_KEY]  +  [JSON cifrado]
     │                 │                   │
     └─────────────────┴───────────────────┘
              ↓
         [Fernet Encryption]
              ↓
        CPRO-Z0FBQUFBQnFnbF...
        (Licencia Cifrada)


CAPA 2: RENOVACIÓN ANUAL (renewal_license.py)
═════════════════════════════════════════════════
  License Actual        Validación         Nueva Licencia
     ↓                      ↓                    ↓
  [CPRO-...]  ──→  check_license()  ──→  renewal_license.py --auto
                                                ↓
                                        [+365 días]
                                                ↓
                                        Guardar en .env


CAPA 3: REGISTRO DE EQUIPOS (register_equipment.py)
════════════════════════════════════════════════════════
  Machine ID        Empresa + Equipo       Licencia
     ↓                    ↓                   ↓
  [ABC123...]  +  [ElRusso, PC-01]  +  [CPRO-...]
     │                    │                 │
     └────────────────────┴─────────────────┘
              ↓
      equipos_registro.json
      ├─ ElRusso
      │  ├─ PC-OFICINA-01 → CPRO-...
      │  ├─ LAPTOP-VENDEDOR-01 → CPRO-...
      │  └─ [más equipos...]
      └─ OtraEmpresa
         └─ [equipos...]
```

---

## 🔄 Flujos de trabajo

### FLUJO A: Activar equipo nuevo

```
NUEVO EQUIPO                    EQUIPO ADMINISTRATIVO          NUEVO EQUIPO (ACTIVAR)
═════════════════════════════════════════════════════════════════════════════════════════

1. Obtener Machine ID
   .\.venv\Scripts\python.exe renewal_license.py --myid
   └─→ ABC123DEF456GHI789...
       (anotar)


                            2. Registrar equipo
                               register_equipment.py register \
                               --empresa "ElRusso" \
                               --machine "ABC123DEF456..." \
                               --equipo "LAPTOP-VENDEDOR-01"
                               
                               └─→ Genera CPRO-Z0FBQUFBQnFn...
                                   (copiar)


                                                        3. Activar licencia
                                                           activar_licencia.py --key "CPRO-..."
                                                           
                                                           └─→ Escribe en .env
                                                               Inicia app
                                                               ✅ Funciona
```

### FLUJO B: Renovar licencia anualmente

```
PRÓXIMA RENOVACIÓN (2027-08-01)
═══════════════════════════════════════════════════════════════════════════════════════════

Ejecutar una vez:
  .\.venv\Scripts\python.exe renewal_license.py --auto
  
  ├─→ Lee: CREDITOSPRO_LICENSE_KEY desde .env
  ├─→ Valida: check_license() ✅
  ├─→ Genera: nueva licencia con +365 días
  ├─→ Guarda: actualiza CREDITOSPRO_LICENSE_KEY en .env
  └─→ Registra: equipos_registro.json actualizado
  
✅ App sigue funcionando sin cambios
✅ Validez extendida 365 días más
✅ Registrado en equipos_registro.json

Repetir anualmente...
```

### FLUJO C: Consultar equipos

```
LISTAR EQUIPOS                   VER ESTADO                    EXPORTAR LICENCIAS
═════════════════════════════════════════════════════════════════════════════════════════

register_equipment.py list \    register_equipment.py status \ register_equipment.py export \
  --empresa "ElRusso"             --empresa "ElRusso" \         --empresa "ElRusso"
                                  --equipo "PC-OFICINA-01"
  ↓                               ↓                             ↓
  
📊 Equipos de ElRusso:          📊 Estado de PC-OFICINA-01:   📊 Licencias de ElRusso:
├─ PC-OFICINA-01 ✅             ├─ Machine ID: 0C77...       ├─ Equipo | Machine | Expira
├─ LAPTOP-VENDEDOR-01 ✅        ├─ Vencimiento: 2027-08-16   ├─ PC-01 | 0C77... | 2027-08
│                               ├─ Validación: ✅ VÁLIDA      └─ LAP-01 | LAPT... | 2027-08
└─ [+ equipos]                  └─ Días restantes: 364
```

---

## 🗂️ Estructura de archivos

```
CreditosPro_DEPLOY/
│
├── 🔑 LICENCIAS (Nivel principal)
│   ├── license_manager.py           ← Valida licencias
│   ├── owner_tool.py                ← Genera licencias (dueño)
│   ├── renewal_license.py           ← Renueva anualmente
│   ├── activar_licencia.py          ← Activa licencia en equipo
│   ├── PLAN_RENOVACION_ANUAL.md     ← Guía de renovación
│   ├── GESTION_EQUIPOS_COMPLETA.md  ← Visión general
│   └── .env                         ← CREDITOSPRO_LICENSE_KEY
│
├── 📁 licencias/ (Nivel equipos)
│   ├── register_equipment.py        ← Gestiona equipos
│   ├── equipos_registro.json        ← Base de datos
│   │   └── ElRusso
│   │       ├── PC-OFICINA-01
│   │       └── LAPTOP-VENDEDOR-01
│   ├── REGISTRAR_EQUIPOS.md         ← Guía completa
│   ├── GUIA_RAPIDA_EQUIPOS.md       ← 3 pasos
│   ├── README.md                    ← Documentación
│   ├── license_PC-OFICINA-01.txt
│   └── license_LAPTOP-VENDEDOR-01.txt
│
└── 📁 app/ (Aplicación)
    ├── main.py
    ├── routers/
    │   ├── license_router.py        ← Endpoints /machine-id, /activate
    │   └── ...
    └── ...
```

---

## 🔐 Flujo de seguridad (criptografía)

```
GENERACIÓN DE LICENCIA
═════════════════════════════════════════════════════════════════════════════════════════

1. Datos originales:
   {
     "machine_id": "0C773FA2129C81EDB9E7921A7D421A0C",
     "empresa_id": 1,
     "empresa_nombre": "ElRusso",
     "issued_at": "2026-08-16T19:21:03.623348",
     "expires_at": "2027-08-16T19:21:03.624938",
     "version": "3.0"
   }

2. Derivar clave de cifrado:
   LICENSE_MASTER_KEY (desde .env)
     ↓
   SHA256(key)
     ↓
   Base64-encode
     ↓
   Fernet_Key

3. Cifrar con Fernet:
   Fernet(key).encrypt(JSON_bytes)
     ↓
   token_bytes

4. Codificar para transportar:
   Base64(token_bytes)
     ↓
   "Z0FBQUFBQnFnbFB2ODJTM2Y1NE1fel81RVBsVUE0YlNr..."

5. Agregar prefijo:
   "CPRO-" + base64_string
     ↓
   CPRO-Z0FBQUFBQnFnbFB2ODJTM2Y1NE1fel81RVBsVUE0YlNrSzV...


VALIDACIÓN DE LICENCIA
═════════════════════════════════════════════════════════════════════════════════════════

1. Licencia recibida:
   CPRO-Z0FBQUFBQnFnbFB2ODJTM2Y1NE1fel81RVBsVUE0YlNrSzV...

2. Remover prefijo:
   Z0FBQUFBQnFnbFB2ODJTM2Y1NE1fel81RVBsVUE0YlNrSzV...

3. Descodificar Base64:
   token_bytes

4. Descifrar con Fernet(key):
   JSON_bytes

5. Validar:
   ├─ machine_id == get_fingerprint() ✅
   ├─ expires_at > now() ✅
   └─ version == "3.0" ✅

6. Resultado:
   {'valid': True, 'dias_left': 364, ...}
```

---

## 📈 Escala: De 1 equipo a 1000+

### ACTUAL (hasta 100 equipos)
```
Almacenamiento: equipos_registro.json (JSON simple)
Gestión: Scripts Python (register_equipment.py)
Respaldo: Copias manuales
Auditoría: Básica (fecha registro en JSON)
```

### FUTURO (1000+ equipos)
```
Almacenamiento: Tabla SQL (licenses.equipos)
Gestión: Panel web + API /equipos
Respaldo: DB backups automáticos
Auditoría: Logs completos (quién, cuándo, qué cambió)
```

### Migración (cuando sea necesario)
1. Exportar `equipos_registro.json`
2. Crear tabla SQL: `CREATE TABLE equipos (...)`
3. Importar datos desde JSON
4. Cambiar `register_equipment.py` para usar SQLAlchemy
5. Crear endpoints en FastAPI

---

## 🎯 Resumen de capacidades

| Capacidad | Antes | Ahora |
|-----------|-------|-------|
| Equipos simultáneos | 1 | ∞ (sin límite técnico) |
| Renovación | Manual | Automática |
| Registro | Ninguno | equipos_registro.json |
| Consultas | Ninguna | 5 comandos |
| Exportación | No | Sí (CSV) |
| Multi-empresa | No | Sí |
| Backup | Manual .env | + equipos_registro.json |

---

## 🚀 Próximos pasos opcionales

1. **Automatizar renovación**
   - Windows Task Scheduler ejecuta `renewal_license.py --auto` anualmente
   
2. **Sincronizar en nube**
   - Guardar `equipos_registro.json` en OneDrive/Google Drive
   
3. **Panel web**
   - Interfaz para ver/registrar/renovar equipos
   
4. **Auditoría completa**
   - Log de cada actividad (activación, renovación, cambios)
   
5. **Integración WhatsApp**
   - Enviar recordatorio de renovación por WhatsApp

---

**Documento técnico generado**: 2026-08-16
**Versión del sistema**: 3.0
**Última actualización**: Implementación de registro de equipos
