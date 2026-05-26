# 🔄 SINCRONIZACIÓN RÁPIDA - Archivos Modificados Solamente

**Versión:** v3.0  
**Fecha:** 25 de mayo de 2026  
**Objetivo:** Copiar SOLO los archivos cambiados al otro PC sin recopiar toda la carpeta

---

## 📋 ARCHIVOS QUE CAMBIÓ (Mínimos)

```
✓ templates/base.html            ← CRÍTICO (Interfaz visible)
✓ limpiar_elruso_duplicado.py    ← Script limpieza BD
✓ GUIA_SINCRONIZACION_OTRO_PC.md ← Documentación
✓ RESUMEN_CAMBIOS_v3_0.md        ← Documentación
```

---

## 🚀 OPCIÓN 1: SINCRONIZACIÓN POR RED (Recomendado si están en LAN)

### Paso 1: En el OTRO PC - Compartir la carpeta

1. Abre Explorador (Win+E)
2. Navega a: `C:\Users\USUARIO\Desktop\CreditosPro_v2` (o donde esté)
3. Click derecho → **Propiedades**
4. Tab **Compartir**
5. Click en **Compartir**
6. Agrega el usuario o **"Todos"** con permisos
7. Click **Compartir**
8. Nota la IP de ese PC (cmd → `ipconfig` → busca "IPv4")

### Paso 2: En ESTE PC - Ejecutar script de sincronización

**Opción A: PowerShell (Recomendado - más moderno)**

```powershell
# 1. Abre PowerShell EN ESTA CARPETA
# (Si no estás en la carpeta, navega)
cd C:\Users\johan\Downloads\CreditosPro_FINAL\CreditosPro_v2_seguro_base\CreditosPro_v2

# 2. Ejecuta el script
.\sync_archivos.ps1

# Te pedirá:
# - IP del otro PC (ej: 192.168.1.50)
# - Usuario del otro PC (ej: johan)
# - Ruta en otro PC (ej: C:\Users\johan\Desktop\CreditosPro_v2)

# Luego copia automáticamente solo los archivos necesarios
```

**Opción B: CMD (Si prefieres comando más simple)**

```cmd
# Ejecuta el script batch
sync_archivos.bat
```

---

## 🔌 OPCIÓN 2: USB (Si no está en red)

### En ESTE PC:
1. Conecta USB
2. Copia ESTOS archivos al USB:
   ```
   USB:\
   ├── templates
   │   └── base.html           ← Copiar este
   ├── limpiar_elruso_duplicado.py  ← Copiar este
   └── GUIA_SINCRONIZACION_OTRO_PC.md (opcional)
   ```

### En el OTRO PC:
1. Conecta USB
2. Copia `base.html` → `CreditosPro_v2\templates\`
3. Copia `limpiar_elruso_duplicado.py` → `CreditosPro_v2\`
4. Continúa con paso 3 abajo

---

## ☁️ OPCIÓN 3: Google Drive / OneDrive (Sin red ni USB)

1. Crea carpeta en Google Drive: `CreditosPro_v3_Updates`
2. Sube estos archivos:
   - `templates/base.html`
   - `limpiar_elruso_duplicado.py`

3. En el otro PC: Descárgalos desde Google Drive
4. Cópialos a la carpeta CreditosPro_v2

---

## ✅ PASO 3: En el OTRO PC - Ejecutar actualización

Una vez que los archivos están copiados:

```powershell
# 1. Abre PowerShell en CreditosPro_v2
cd C:\Users\USUARIO\Desktop\CreditosPro_v2

# 2. IMPORTANTE: Ejecuta la limpieza de duplicados
python limpiar_elruso_duplicado.py

# Responde "s" cuando pida confirmación
# Verifica que diga: "✅ LIMPIEZA COMPLETADA EXITOSAMENTE"

# 3. Reinicia el servidor
python run.py

# Se abre Chrome automáticamente
# Abre: http://127.0.0.1:8000/dashboard
```

---

## 🔍 VERIFICACIÓN

En Chrome del otro PC, verifica:

- ✅ **Dashboard VISIBLE** (no transparente)
- ✅ **Menú lateral** con opciones
- ✅ **Tarjetas** de estadísticas
- ✅ **Botones** responden al click
- ✅ **Consola (F12)** sin errores rojos

---

## 🆘 SI ALGO FALLA

### Problema: "No se puede acceder a la red"
```
Soluciones:
1. Verifica que ambos PCs están en la MISMA RED WiFi
2. Verifica la IP del otro PC (debe empezar igual, ej: 192.168.1.xxx)
3. En el otro PC, verifica que la carpeta está compartida
4. Usa USB o Google Drive como alternativa
```

### Problema: "Error al copiar archivo"
```
Soluciones:
1. Cierra CreditosPro en el otro PC (python run.py)
2. Asegúrate que CreditosPro_v2 no está siendo usado
3. Intenta copiar manualmente (arrastrar y soltar)
4. Si persiste, usa USB
```

### Problema: "Dashboard aún transparente"
```
Soluciones:
1. Verifica que copiaste templates/base.html correctamente
2. En Chrome: Presiona Ctrl+Shift+R (hard refresh)
3. Cierra Chrome completamente
4. Ejecuta python run.py de nuevo
5. Si persiste, revisa que base.html tiene ~400+ líneas
```

### Problema: "limpiar_elruso_duplicado.py no se ejecuta"
```
Soluciones:
1. Verifica que copiaste el archivo a la carpeta raíz (CreditosPro_v2\)
2. Verifica que existe .env en la carpeta
3. Ejecuta desde PowerShell EN la carpeta CreditosPro_v2
```

---

## 📊 COMPARACIÓN DE OPCIONES

| Método | Velocidad | Fácil | Requiere |
|--------|-----------|-------|----------|
| **Red LAN** | ⚡⚡⚡ Muy rápida | ✅ Sí | Internet en red |
| **USB** | ⚡⚡ Rápida | ✅ Sí | USB |
| **Google Drive** | ⚡ Lenta | ✅ Sí | Internet en ambos |

**Recomendado:** Red LAN (si está disponible)

---

## 🎯 RESUMEN RÁPIDO

```
ESTE PC                          OTRO PC
────────────────────────────────────────────────────
1. sync_archivos.ps1   ──────→  Copia archivos
2. Espera a terminar   ←───────  Recibe archivos
                                 3. limpiar_elruso_duplicado.py
                                 4. python run.py
                                 5. ¡Listo!
```

---

## 📞 REFERENCIA RÁPIDA

**Red:**
```powershell
.\sync_archivos.ps1
# IP: 192.168.1.XX  | Usuario: johan | Ruta: C:\Users\johan\Desktop\CreditosPro_v2
```

**Otro PC (después de copiar):**
```powershell
python limpiar_elruso_duplicado.py
python run.py
```

---

**¡LISTO! Tu otro PC tendrá v3.0 con interfaz visible y BD limpia.**
