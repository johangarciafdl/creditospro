# 🚀 Guía: Instalación y Uso Diario de CreditosPro

## Para el Admin — Iniciar sin terminal

### Opción 1: Acceso directo en el escritorio (recomendado)

1. **Ejecuta `crear_acceso_directo.bat`**
   - Haz doble clic en el archivo `crear_acceso_directo.bat`
   - Se creará un acceso directo en tu escritorio llamado `CreditosPro`

2. **Desde ahora, para iniciar:**
   - Doble clic en el ícono `CreditosPro` del escritorio
   - Se abre Chrome automáticamente
   - **Sin terminal visible** — limpio y profesional

---

### Opción 2: Inicio automático al encender el PC

Si quieres que CreditosPro se inicie **solo** cada vez que enciendas la máquina:

1. **Ejecuta `setup_inicio_automatico.bat`**
   - Crea un acceso directo en la carpeta de Inicio
   - CreditosPro arrancará automáticamente

2. **Para desactivarlo después:**
   - Presiona `Win + R`
   - Escribe `shell:startup`
   - Borra el acceso directo `CreditosPro`

---

### Opción 3: Manual — Crear el `.bat` tú mismo

Si prefieres hacer el archivo manualmente:

1. Click derecho en el escritorio → Nuevo → Documento de texto
2. Copia esto:

```batch
@echo off
cd /d "C:\ruta\a\CreditosPro_NombreEmpresa"
python run.py
```

3. Guarda como: `Iniciar CreditosPro.bat` (cambiar extensión de .txt a .bat)
4. Doble clic para ejecutar

---

## Para los cobradores — PWA en celular (sin instalar nada)

### ¿Qué es una PWA?
Una **Progressive Web App** que se ve y funciona como una aplicación nativa en el celular, pero sin necesidad de instalar nada.

### Requisitos
- Ambos (admin y cobradores) en la **misma WiFi**
- El servidor corriendo en el PC del admin

### Pasos para el cobrador

1. **Abre Chrome en el celular**

2. **Accede a:**
   ```
   http://IP_DEL_PC_ADMIN:8000
   ```
   - Reemplaza `IP_DEL_PC_ADMIN` por la IP que se muestra cuando ejecutas el `.bat`
   - Ejemplo: `http://192.168.1.50:8000`

3. **Chrome muestra un banner:** "Agregar a pantalla de inicio"
   - Toca en ese banner
   - Se instala como app nativa

4. **Listo** 🎉
   - El cobrador abre CreditosPro desde el icono de su celular
   - Funciona como cualquier app
   - Puede registrar cobros offline y sincroniza automáticamente

---

## IPs y Conexiones

Cuando ejecutas `Iniciar CreditosPro.bat`, ves:

```
[✓] Acceso local:        http://127.0.0.1:8000
[✓] Desde otros PCs:     http://192.168.1.50:8000
[✓] Celular en WiFi:     http://192.168.1.50:8000
```

- **127.0.0.1** → Solo tu PC (localhost)
- **192.168.x.x** → Tu PC desde otros dispositivos en la misma WiFi

---

## Si el cobrador está en la calle

**Problema:** El celular no está en la misma WiFi

**Solución:** Usar Railway (servidor en la nube)

- Despliega CreditosPro en Railway
- El cobrador accede a: `https://creditospro-tu-empresa.up.railway.app`
- Funciona desde cualquier lugar con internet

---

## Troubleshooting

### ❌ "Python no está instalado"
- Descarga Python 3.11+ desde [python.org](https://python.org)
- **IMPORTANTE:** marca "Add Python to PATH" durante la instalación
- Reinicia el script

### ❌ "Puerto 8000 ya en uso"
- Otro programa usa ese puerto
- Opción 1: Cierra el otro programa
- Opción 2: Cambia el puerto en el `.env`
  ```
  PORT=8001
  ```

### ❌ El celador no ve la pantalla de activación
- Verifica que ambos están en la **misma WiFi**
- Prueba con la IP que se muestra en el `.bat`
- Si no funciona, usa Railway (servidor en la nube)

---

## Archivos principales

```
CreditosPro_v2/
├── Iniciar CreditosPro.bat           ← Ejecutar diariamente
├── crear_acceso_directo.bat          ← Crear icono en escritorio (una sola vez)
├── setup_inicio_automatico.bat       ← Inicio automático al encender PC
└── GUIA_USO_DIARIO.md               ← Este archivo
```

---

**Creado:** 25 de mayo de 2026  
**Sistema:** CreditosPro v2.1  
**Autor:** Johan Garcia
