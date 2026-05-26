# 📦 Guía de Instalación de CreditosPro ElRuso en Otro PC

**Tiempo estimado:** 5-10 minutos  
**Requisitos:** Internet durante la instalación

---

## PASO 1: Requisitos en el PC del Cliente

- [ ] Windows 7 o superior
- [ ] Python 3.11 o superior (descargar de [python.org](https://python.org/downloads))
- [ ] Conexión a internet

---

## PASO 2: Obtener la Carpeta de tu PC

### En tu PC (Admin):

1. Copia toda la carpeta:
   ```
   C:\Users\tu_usuario\Downloads\CreditosPro_FINAL\CreditosPro_v2_seguro_base\CreditosPro_v2
   ```

2. Pégala en un USB o sube a Google Drive

3. Entrega al cliente

---

## PASO 3: Instalación en el PC del Cliente

### El cliente hace esto:

**3.1** Instala Python (si no tiene):
```
1. Ve a https://python.org/downloads
2. Descarga Python 3.11 o superior
3. Durante instalación: MARCA ☑️ "Add Python to PATH"
4. Click en "Install Now"
```

**3.2** Abre PowerShell:
```
Win + R → escribe: powershell → Enter
```

**3.3** Navega a la carpeta recibida:
```powershell
cd C:\Users\NOMBRE\Desktop\CreditosPro_v2
```

**3.4** Instala dependencias (primera vez):
```powershell
pip install -r requirements.txt
pip install cryptography
```
⏱️ Espera 2-3 minutos

**3.5** Configura la empresa ElRuso:
```powershell
python setup_empresa_elruso.py
```

**Resultado:**
```
✅ SETUP COMPLETADO EXITOSAMENTE

DATOS DE ACCESO PARA TODOS LOS USUARIOS:

📋 ADMIN/OWNER:
   Usuario:     johan
   Contraseña:  Jo681192
   Rol:         admin (acceso total)

👔 GERENTE:
   Usuario:     julian
   Contraseña:  197991
   Rol:         gerente (todas las funciones)

🚗 COBRADOR:
   Usuario:     marcos
   Contraseña:  Marcos123
   Rol:         cobrador (registrar cobros)
```

**3.6** Ejecuta el programa:
```powershell
python run.py
```

✅ Se abre Chrome automáticamente

**Login con cualquiera de los usuarios:**
- johan / Jo681192 (acceso total)
- julian / 197991 (gerente)
- marcos / Marcos123 (cobrador)

---

## PASO 4: Uso Diario

El cliente solo ejecuta:

```powershell
python run.py
```

O crea un acceso directo en el escritorio:

```powershell
crear_acceso_directo.bat
```

---

## PASO 5: Para Cobradores en Celular

El cobrador abre Chrome en el celular y accede a:

```
http://IP_DEL_PC_ADMIN:8000
```

**Ejemplo:**
```
http://192.168.1.50:8000
```

Aparece: "Agregar a pantalla de inicio" → Toca → Se instala como app

---

## ✅ Checklist de Entrega

- [ ] Python 3.11+ instalado
- [ ] `pip install -r requirements.txt` ✅ completado
- [ ] `python setup_empresa_elruso.py` ✅ completado
- [ ] `python run.py` abre sin errores
- [ ] Login exitoso: johan / Jo681192
- [ ] Datos de cobros visibles

---

## Troubleshooting

### ❌ "Python no está instalado"
```
1. Desinstala Python completamente
2. Descarga de https://python.org/downloads
3. Durante instalación MARCA "Add Python to PATH"
4. Reinicia el PC
5. Intenta nuevamente
```

### ❌ "Puerto 8000 ya en uso"
```
Opción A: Cierra el otro programa
Opción B: Cambia en .env:
  PORT=8001
```

### ❌ "Error en setup_empresa_elruso.py"
```
Verifica:
1. Que hay internet
2. Que DATABASE_URL en .env es correcto
3. Que Supabase está disponible
```

### ❌ "No puedo hacer login"
```
Verifica:
1. Usuario: johan, julian, o marcos (sin espacios)
2. Contraseña: exacta (distingue mayúsculas)
3. Que setup_empresa_elruso.py se ejecutó sin errores
4. Usuarios disponibles:
   - johan / Jo681192 (admin)
   - julian / 197991 (gerente)
   - marcos / Marcos123 (cobrador)
```

---

## Datos de Contacto

```
Usuario Admin (Owner):  johan / Jo681192
Usuario Gerente:        julian / 197991
Usuario Cobrador:       marcos / Marcos123
Empresa:                ElRuso
Empresa ID:             1
```

---

**Versión:** CreditosPro v2.1 - ElRuso  
**Última actualización:** 25 de mayo de 2026

