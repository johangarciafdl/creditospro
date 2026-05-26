# 🔄 SINCRONIZACIÓN SIMPLE - SIN REDES COMPLICADAS

**Para cuando compartir carpetas no funciona**

---

## 🎯 LA FORMA MÁS SIMPLE: Copiar a Mano (2 archivos)

### En ESTE PC (Admin):

**1. Prepara los archivos en una carpeta temporal**

```
USB o Google Drive:
├── base.html                      ← Copiar desde templates\base.html
└── limpiar_elruso_duplicado.py    ← Copiar desde raíz
```

**2. Método A: Directamente desde Explorador**

```
1. Abre Explorador (Win+E)
2. Navega a: C:\Users\johan\Downloads\CreditosPro_FINAL\CreditosPro_v2_seguro_base\CreditosPro_v2
3. Busca y copia estos 2 archivos:
   
   ✓ templates\base.html
     (Click derecho → Copiar)
   
   ✓ limpiar_elruso_duplicado.py
     (Click derecho → Copiar)

4. Copia a USB o pega en Google Drive
```

**3. Método B: PowerShell (Automático)**

```powershell
# Abre PowerShell EN esta carpeta

# Copia a USB (asumiendo que USB es E:)
Copy-Item "templates\base.html" -Destination "E:\base.html"
Copy-Item "limpiar_elruso_duplicado.py" -Destination "E:\limpiar_elruso_duplicado.py"

# Mensaje de confirmación
Write-Host "✓ Archivos copiados a USB"
Write-Host "  - E:\base.html"
Write-Host "  - E:\limpiar_elruso_duplicado.py"
```

---

## 💾 EN EL OTRO PC (Con el USB o Google Drive):

### **Paso 1: Localiza la carpeta CreditosPro**

```
Típicamente en:
- C:\Users\julia\Desktop\CreditosPro_v2
- C:\Users\julia\Downloads\CreditosPro_v2
- O en D:\CreditosPro_v2
```

Si no la encuentras:

```powershell
# Abre PowerShell
dir C:\Users\julia\Desktop\ /s /b | findstr CreditosPro
# O en Downloads:
dir C:\Users\julia\Downloads\ /s /b | findstr CreditosPro
```

### **Paso 2: Copia los 2 archivos en su lugar**

**Opción A: Copiar desde USB (Más fácil)**

```
1. Conecta USB al otro PC
2. Explorador → USB
3. Ve al archivo "base.html"
4. Click derecho → Copiar
5. Navega a: C:\Users\julia\Downloads\CreditosPro_v2\templates\
6. Click derecho → Pegar
   (Reemplazar cuando pida)

7. De nuevo desde USB:
8. Copia "limpiar_elruso_duplicado.py"
9. Pega en: C:\Users\julia\Downloads\CreditosPro_v2\
   (Reemplazar cuando pida)
```

**Opción B: PowerShell (desde USB)**

```powershell
# En el otro PC, abre PowerShell

# Definir rutas
$RUTA_CREDITOSPRO = "C:\Users\julia\Downloads\CreditosPro_v2"
$RUTA_USB = "E:\"  # O donde esté el USB

# Copiar archivos
Copy-Item "$RUTA_USB\base.html" -Destination "$RUTA_CREDITOSPRO\templates\base.html" -Force
Copy-Item "$RUTA_USB\limpiar_elruso_duplicado.py" -Destination "$RUTA_CREDITOSPRO\limpiar_elruso_duplicado.py" -Force

Write-Host "✓ Archivos actualizados exitosamente"
```

**Opción C: Desde Google Drive**

```
1. Abre navegador → Google Drive
2. Descarga "base.html"
3. Descarga "limpiar_elruso_duplicado.py"
4. Corta (Ctrl+X) los 2 archivos descargados
5. Navega a C:\Users\julia\Downloads\CreditosPro_v2
6. En templates\ pega base.html
7. En la raíz pega limpiar_elruso_duplicado.py
```

---

## ✅ PASO 3: Ejecutar limpieza

```powershell
# En PowerShell EN la carpeta CreditosPro_v2

cd C:\Users\julia\Downloads\CreditosPro_v2

# Ejecuta limpieza (CRÍTICO)
python limpiar_elruso_duplicado.py

# Responde: s
# Espera a que diga: ✅ LIMPIEZA COMPLETADA EXITOSAMENTE
```

## ▶️ PASO 4: Reiniciar servidor

```powershell
python run.py

# Se abre Chrome automáticamente
# Verifica: http://127.0.0.1:8000/dashboard
# ✓ Dashboard VISIBLE (no transparente)
```

---

## 🆘 SI ALGO FALLA

### "No encuentro CreditosPro_v2"
```powershell
# En PowerShell del otro PC, busca:
Get-ChildItem -Path "C:\" -Recurse -Filter "CreditosPro_v2" -ErrorAction SilentlyContinue
```

### "Error al pegar - Acceso denegado"
```
1. Cierra CreditosPro completamente (cierra PowerShell)
2. Intenta pegar de nuevo
3. Si persiste, renombra el archivo antiguo y pega el nuevo
```

### "base.html no se actualiza"
```
1. Verifica que está en: CreditosPro_v2\templates\base.html
2. Hard refresh en Chrome: Ctrl+Shift+R
3. Cierra Chrome completamente
4. Abre de nuevo: python run.py
```

---

## 📋 CHECKLIST FINAL

En el otro PC, verifica:

- [ ] `CreditosPro_v2\templates\base.html` — actualizado (tamaño > 20KB)
- [ ] `CreditosPro_v2\limpiar_elruso_duplicado.py` — copiado
- [ ] Ejecutó: `python limpiar_elruso_duplicado.py` ✓ exitoso
- [ ] Ejecutó: `python run.py` ✓ se abrió Chrome
- [ ] Dashboard visible (no transparente) ✓
- [ ] Menú funciona ✓

---

## 📞 REFERENCIA RÁPIDA

**Este PC:**
```powershell
# Prepara USB
Copy-Item "templates\base.html" -Destination "E:\base.html"
Copy-Item "limpiar_elruso_duplicado.py" -Destination "E:\limpiar_elruso_duplicado.py"
```

**Otro PC:**
```powershell
# Pega desde USB
$USB="E:\" ; $RUTA="C:\Users\julia\Downloads\CreditosPro_v2"
Copy-Item "$USB\base.html" "$RUTA\templates\base.html" -Force
Copy-Item "$USB\limpiar_elruso_duplicado.py" "$RUTA\limpiar_elruso_duplicado.py" -Force

# Ejecuta
python limpiar_elruso_duplicado.py
python run.py
```

---

**¡Así es mucho más simple y sin complicaciones de redes!**
