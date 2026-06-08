# 🔄 GUIA: Sincronizar CreditosPro al Otro PC

**Fecha:** 25 de mayo de 2026  
**Versión:** CreditosPro v3.0  
**Cambios:** Limpieza de duplicado ElRuso + Correcciones CSS/JavaScript

---

## 📋 RESUMEN DE CAMBIOS REALIZADOS

### ✅ Cambios en PC Admin (ESTE PC)

1. **Limpieza de Base de Datos**
   - Script: `limpiar_elruso_duplicado.py`
   - Elimina empresa ElRuso ID 20 (duplicada)
   - Mantiene solo ID 1 (original)

2. **Correcciones de Interfaz Gráfica**
   - Archivo: `templates/base.html`
   - Problema: CSS/JavaScript no se cargaban, interfaz transparente
   - Solución:
     - Mejorado polyfill de Anime.js
     - Agregados fallbacks para animaciones
     - Agregado timeout de seguridad (1.5s)
     - Arreglados errores de modalesy toasts

---

## 🚀 PASOS PARA SINCRONIZAR AL OTRO PC

### OPCIÓN 1: SINCRONIZACIÓN COMPLETA (Recomendado para primer PC)

**En este PC (ADMIN):**

```powershell
# 1. Limpiar duplicados de BD (IMPORTANTE - hacer una sola vez)
python limpiar_elruso_duplicado.py

# Responder "s" cuando pida confirmación
# Verificar que dice "LIMPIEZA COMPLETADA EXITOSAMENTE"

# 2. Hacer backup de la carpeta (opcional pero recomendado)
# (La carpeta se puede copiar completa a USB o Google Drive)
```

**Copiar carpeta al otro PC:**

```
Opción A: USB
1. Conecta USB a este PC
2. Copia toda la carpeta:
   C:\Users\johan\Downloads\CreditosPro_FINAL\CreditosPro_v2_seguro_base\CreditosPro_v2
3. Cópiala a la raíz del USB (ejemplo: E:\CreditosPro_v2\)
4. Lleva el USB al otro PC

Opción B: Google Drive / OneDrive
1. Sube la carpeta a tu nube
2. En el otro PC, descárgala
3. Extrae en una ubicación cómoda (ej: Desktop o Downloads)
```

**En el OTRO PC:**

```powershell
# 1. Abre PowerShell
Win + R → escribe: powershell → Enter

# 2. Navega a la carpeta
cd C:\Users\NOMBRE_USUARIO\Downloads\CreditosPro_v2
# O donde sea que la pegaste

# 3. Actualiza requirements.txt (solo por si hay cambios)
pip install -r requirements.txt --upgrade

# 4. Configura la empresa ElRuso
python setup_empresa_elruso.py

# 5. Inicia el programa
python run.py

# ✅ Se abre Chrome automáticamente
# Accede con: johan / XXXXXX
```

**Verificación en otro PC:**
```powershell
# Dashboard debe mostrar contenido (no transparente)
# Menú lateral visible
# Botones funcionales
# Sin errores de consola (F12)
```

---

### OPCIÓN 2: ACTUALIZACIÓN MÍNIMA (Si ya existe CreditosPro)

Si el otro PC ya tiene CreditosPro instalado y funcionando:

**En este PC (ADMIN):**

```powershell
# Copia solo los archivos modificados
# Copiar estos archivos:
# - templates/base.html  ← Principal cambio
# - limpiar_elruso_duplicado.py  ← Script nuevo
```

**En el otro PC:**

```powershell
# 1. Reemplaza el archivo templates\base.html

# 2. Copia limpiar_elruso_duplicado.py a la carpeta CreditosPro_v2

# 3. Ejecuta la limpieza de duplicados
python limpiar_elruso_duplicado.py

# 4. Reinicia el programa
# (Cierra Chrome o powershell, luego: python run.py)
```

---

## 🔍 VERIFICACIÓN DE CAMBIOS

### En el Otro PC, Verifica:

**1. Interfaz Gráfica:**
- ✅ Dashboard visible (no transparente)
- ✅ Menú lateral ve las opciones
- ✅ Tarjetas de estadísticas con datos
- ✅ Botones responden al click

**2. Base de Datos:**
- ✅ Solo UNA empresa "ElRuso" (ID: 1)
- ✅ Usuarios: johan, julian, marcos presentes

**Verificar desde PowerShell:**
```powershell
# Abre SQLite si usas BD local
# o conecta a tu BD PostgreSQL

# Comando para verificar empresas:
# python -c "from app.database import SessionLocal, Empresa; db=SessionLocal(); empresas=db.query(Empresa).all(); print([f'ID {e.id}: {e.nombre}' for e in empresas])"
```

**3. Console del navegador (F12):**
- ✅ Sin errores rojos
- ✅ Anime.js cargado correctamente
- ✅ CSS aplicado correctamente

---

## 🐛 TROUBLESHOOTING

### Problema: "Interfaz aún transparente después de actualizar"

**Solución:**
```powershell
# 1. Borra el caché del navegador
# Chrome: Ctrl+Shift+Delete → Limpiar todo

# 2. Recarga la página
# F5 o Ctrl+Shift+R (hard refresh)

# 3. Si persiste, reinicia el servidor
# Cierra PowerShell (Ctrl+C)
# Ejecuta nuevamente: python run.py
```

### Problema: "Error al ejecutar limpiar_elruso_duplicado.py"

**Solución:**
```powershell
# Asegúrate que está en la carpeta correcta
cd C:\Users\NOMBRE\...\CreditosPro_v2

# Verifica que existe el archivo .env
dir .env

# Si falta, cópialo desde este PC o crea uno basado en .env.example

# Intenta de nuevo
python limpiar_elruso_duplicado.py
```

### Problema: "Las animaciones no funcionan aunque actualizó base.html"

**Solución:**
```powershell
# El fallback debe mostrar contenido después de 1.5s
# Si no aparece, hay otro problema

# 1. Abre F12 (Herramientas de Desarrollador)
# 2. Ve a Console
# 3. Busca errores de JavaScript

# 4. Si dice "anime is not defined":
#    - Anime.js no cargó desde CDN
#    - Problema de internet o CDN caído
#    - El fallback debería funcionar igual

# 5. Si dice otro error, copia y envía el error completo
```

---

## 📝 ARCHIVOS MODIFICADOS

```
✓ templates/base.html
  ├─ Mejorado polyfill de Anime.js
  ├─ Agregados fallbacks de seguridad
  ├─ Arregladas animaciones de modales
  └─ Mejorado toast con manejo de errores

✓ limpiar_elruso_duplicado.py (NUEVO)
  ├─ Script para limpiar duplicados
  ├─ Confirmación antes de ejecutar
  └─ Reporte detallado de cambios
```

---

## ✅ CHECKLIST FINAL

Antes de considerar la sincronización completada:

- [ ] Ejecutaste `limpiar_elruso_duplicado.py` en este PC
- [ ] Copiaste la carpeta al otro PC (USB o nube)
- [ ] En el otro PC ejecutaste `setup_empresa_elruso.py`
- [ ] En el otro PC ejecutaste `python run.py` exitosamente
- [ ] El dashboard del otro PC es visible (no transparente)
- [ ] Accediste con johan / XXXXXX
- [ ] Los botones funcionan
- [ ] No hay errores en F12 Console

---

## 📞 SOPORTE

Si algo no funciona:

1. Verifica los logs en PowerShell (errores en rojo)
2. Abre F12 en Chrome y mira Console
3. Ejecuta con más verbosidad:
   ```powershell
   python run.py 2>&1 | Tee-Object -FilePath debug.log
   ```
4. Comparte el archivo `debug.log` para analizar

---

**Versión de esta guía:** 1.0  
**Última actualización:** 25 de mayo de 2026  
**Estado:** ✅ Listo para producción
