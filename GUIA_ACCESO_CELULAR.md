# 📱 ACCESO EN CELULAR - CreditosPro v3.0

**Para Cobradores (Marcos o cualquier usuario)**

---

## 🎯 REQUISITOS

✅ PC Admin con CreditosPro ejecutándose (`python run.py`)  
✅ Celular en la **MISMA RED WiFi** que el PC  
✅ Chrome instalado en el celular  

---

## 🚀 PASOS PARA ACCEDER DESDE CELULAR

### PASO 1: Encontrar la IP del PC Admin

**En la PC (donde corre CreditosPro):**

#### Opción A: Por PowerShell
```powershell
ipconfig

# Busca la línea: "Dirección IPv4"
# Típicamente: 192.168.1.XX o 10.0.0.XX
# EJEMPLO: 192.168.1.50
```

#### Opción B: Por Explorador
```
1. Haz click en el icono de Red (abajo a la derecha)
2. Click en "WiFi" → "Propiedades"
3. Busca "Dirección IPv4"
```

#### Opción C: Por el CMD
```cmd
ipconfig /all

# Busca: "Dirección IPv4"
```

**Anota la IP:** ___________________  
(Ejemplo: `192.168.1.50`)

---

### PASO 2: Conectar el Celular al WiFi

1. Abre **Configuración** en el celular
2. **WiFi** → Selecciona la red del hogar
3. Ingresa contraseña
4. **Conectado** ✓

---

### PASO 3: Abrir en Chrome del Celular

1. Abre **Chrome**
2. En la barra de direcciones, escribe:
   ```
   http://192.168.1.50:8000
   ```
   (Reemplaza **192.168.1.50** con tu IP real)

3. Presiona **Enter**

4. ✓ Se abre CreditosPro

---

### PASO 4: Login en el Celular

**Usuario:** `marcos`  
**Contraseña:** `Marcos123`

O si es gerente:  
**Usuario:** `julian`  
**Contraseña:** `197991`

---

### PASO 5: Instalar Como App (Opcional pero Recomendado)

1. Cuando está cargado, ve al menú de Chrome (3 puntos arriba a la derecha)
2. Click en **"Instalar aplicación"** o **"Agregar a pantalla de inicio"**
3. Se descarga como app
4. Aparece en la pantalla principal
5. Abre como app nativa (sin URL)

---

## 📋 RESUMEN RÁPIDO

```
PC Admin:  192.168.1.50  ← Reemplaza con TU IP

Celular:
1. Conectar WiFi
2. Abrir Chrome
3. Escribir: http://192.168.1.50:8000
4. Login: marcos / Marcos123
5. ¡Listo!
```

---

## 🔐 PERMISOS POR ROL

| Usuario | Contraseña | Rol | Acceso |
|---------|-----------|-----|--------|
| **marcos** | Marcos123 | Cobrador | Registrar cobros, ver clientes |
| **julian** | 197991 | Gerente | Todo menos usuarios y configuración |
| **johan** | XXXXXX | Admin | Acceso total |

---

## 🆘 SI NO CONECTA

### "No carga la página"

**Soluciones:**
```
1. Verifica que la IP es correcta
   ipconfig en PowerShell

2. Verifica que ambos están en MISMA RED WiFi
   Menú WiFi del PC y del celular

3. Asegúrate que Python run.py está ejecutándose
   Debería decir: "Uvicorn running on http://..."

4. Intenta esperar 5 segundos y recargar (F5)

5. Si dice "ERR_CONNECTION_REFUSED":
   - Python run.py se cerró
   - Ejecuta de nuevo: python run.py
```

### "Error al descargar"

```
1. Si está usando datos móviles, cambia a WiFi
2. Si carga muy lento, acércate más al router
3. Si dice "HTTPS required", asegúrate que es HTTP (no HTTPS)
```

### "Dashboard vacío o transparente"

```
1. Espera a que cargue (puede tardar unos segundos en WiFi)
2. Presiona F5 para recargar
3. Cierra y abre Chrome de nuevo
4. Si persiste, en PC ejecuta:
   python limpiar_elruso_duplicado.py
   python run.py
```

---

## 💡 TIPS

**Para no olvidar la IP:**
```
Escribe la IP en el celular para próximas veces:
- Historial de Chrome
- Bookmark (click en ⭐)
- Nota en Notas de Google
```

**Si cambia la IP:**
```
Si el PC reinicia, puede cambiar la IP
Usa lo mismo: ipconfig → Dirección IPv4
```

**Velocidad WiFi:**
```
Mejor: Conectado al router con cable ethernet
Bueno: WiFi 5GHz
Aceptable: WiFi 2.4GHz
```

---

## 📞 REFERENCIA

```powershell
# En PC Admin, obtener IP:
ipconfig | findstr "IPv4"

# Resultado típico:
# Dirección IPv4 : 192.168.1.50

# En celular:
# Chrome → http://192.168.1.50:8000
# Login: marcos / Marcos123
```

---

## ✅ CHECKLIST ACCESO CELULAR

- [ ] PC Admin con `python run.py` ejecutándose
- [ ] Celular conectado al mismo WiFi
- [ ] IP obtenida (ipconfig)
- [ ] Chrome abierto con: http://IP:8000
- [ ] Se carga la página
- [ ] Login: marcos / Marcos123
- [ ] Dashboard visible
- [ ] Botones funcionan
- [ ] (Opcional) Instalado como app

---

**¡Listo! Tu cobrador puede trabajar desde cualquier lado con WiFi.**
