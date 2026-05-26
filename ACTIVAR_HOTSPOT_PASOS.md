# 🔧 ACTIVAR HOTSPOT WiFi - Paso a Paso

**Solución 1: Hotspot del PC para cobrador en la calle**

---

## 🎯 QUÉ LOGRAREMOS

✅ PC crea una red WiFi propia  
✅ Cobrador se conecta desde el celular  
✅ Accede a CreditosPro desde cualquier lugar  
✅ Datos en tiempo real  

---

## 📱 OPCIÓN A: Windows 11 (Lo que vemos en la imagen)

### Paso 1: Abre Configuración

```
1. Presiona: Win + I
2. O click en icono de engranaje (abajo a la derecha)
```

### Paso 2: Ve a Red e Internet

```
Configuración → Red e Internet
```

### Paso 3: Baja hasta "Acceso telefónico"

```
En la columna izquierda, busca:
"Acceso telefónico" (está debajo de WiFi)
O "Punto de acceso móvil"

Click en ella
```

### Paso 4: Configurar el Hotspot

```
1. Click en "Configura un nuevo conexión o red"
2. O si ya existe, click en "Editar"
3. Escribe:
   - Nombre (SSID): CreditosPro
   - Contraseña: (inventa una fuerte, ej: ElRuso2024!)
4. Click en "Siguiente" o "Guardar"
```

### Paso 5: Activar el Hotspot

```
1. Vuelves a "Acceso telefónico"
2. Ves un toggle "Acceso telefónico"
3. Click para ACTIVAR (azul)
4. Debe decir: "Conectado a X dispositivos"
```

---

## 📱 OPCIÓN B: Windows 10

### Paso 1: Configuración

```
Win + I
```

### Paso 2: Red e Internet

```
Configuración → Red e Internet
```

### Paso 3: Hotspot Móvil

```
En la izquierda:
"Hotspot móvil"

Si no ves, baja más en las opciones
```

### Paso 4: Configurar y Activar

```
1. "Editar" (si quieres cambiar nombre/contraseña)
   - Nombre: CreditosPro
   - Contraseña: ElRuso2024!
2. Toggle "Hotspot móvil" → ACTIVADO
```

---

## ✅ VERIFICAR QUE FUNCIONA

### En el PC:

```powershell
# Abre PowerShell
ipconfig

# Busca la línea: "Dirección IPv4"
# Ejemplo: 192.168.1.50

# Copia esa IP
```

### En el celular del cobrador:

```
1. WiFi → Busca "CreditosPro"
2. Click para conectar
3. Ingresa contraseña: ElRuso2024!
4. Espera a conectado ✓

5. Abre Chrome
6. Escribe en la barra: http://192.168.1.50:8000
7. (Reemplaza 192.168.1.50 con tu IP)

8. Se abre CreditosPro
9. Login: marcos / Marcos123
10. ¡Funciona!
```

---

## 🔐 CONTRASEÑAS SUGERIDAS

```
Fuerte:
- ElRuso2024!
- CreditosPro#2026
- Cobros@Seguro

Media:
- CreditosPro123
- ElRuso2024
```

---

## 🆘 SI NO FUNCIONA

### "No veo Acceso telefónico"

```
Windows 10:
1. Ve a Configuración → Red e Internet
2. Baja y busca "Hotspot móvil"
3. Si no está, es versión muy antigua
   (Actualiza Windows)
```

### "No me deja activar"

```
Causas:
1. No hay adaptador WiFi
   → Pc debe tener WiFi integrado
   
2. El PC no tiene internet
   → Conecta PC a internet primero
   (Wi-Fi o cable ethernet)
   
3. Drivers desactualizados
   → Actualiza Windows Update
```

### "El celular no encuentra la red"

```
1. Verifica que Hotspot está ACTIVADO (azul)
2. Apaga y enciende el WiFi del celular
3. Busca de nuevo la red
4. Si aún no aparece:
   - Reinicia el PC
   - Activa Hotspot de nuevo
```

### "Se conecta pero no carga http://IP:8000"

```
Verificar:
1. En PowerShell: python run.py debe estar ejecutándose
2. IP es correcta (ipconfig)
3. Escribe bien: http://IP:8000 (no https)
4. Espera 5 segundos para que cargue
5. Si no, presiona F5 para recargar
```

---

## 📋 CHECKLIST FINAL

En el PC:
- [ ] Windows 11 o 10 actualizado
- [ ] PC conectado a internet (WiFi o cable)
- [ ] Configuración → Acceso telefónico/Hotspot
- [ ] Nombre: CreditosPro
- [ ] Contraseña: ElRuso2024!
- [ ] ACTIVADO (azul)
- [ ] `python run.py` ejecutándose
- [ ] Obtuvo IP con `ipconfig`

En el celular:
- [ ] WiFi activado
- [ ] Ve red "CreditosPro"
- [ ] Conectado con contraseña
- [ ] Chrome abierto
- [ ] Escribe: http://IP:8000
- [ ] CreditosPro carga
- [ ] Login: marcos / Marcos123
- [ ] Dashboard visible

---

## 💡 TIPS

**Para el futuro:**
```
Nota en el celular:
- SSID (Nombre): CreditosPro
- Contraseña: ElRuso2024!
- URL: http://192.168.1.50:8000
- Usuario: marcos
- Contraseña: Marcos123
```

**Si cambias la IP:**
```
El Hotspot siempre es 192.168.x.x
Si cambia, abre PowerShell y:
ipconfig
Busca la nueva IP
```

**Seguridad:**
```
La red Hotspot es local (no sale a internet)
Solo quien esté cerca puede conectarse
```

---

**¿Listo? Cuéntame cuando lo hayas activado y te digo cómo conectar el celular** ✅
