# Plan de Renovación Anual de Licencias

## 📅 Estado actual

| Campo | Valor |
|-------|-------|
| **Empresa** | ElRusso |
| **Machine ID** | 0C773FA2129C81EDB9E7921A7D421A0C |
| **Licencia actual** | Válida ✅ |
| **Expira** | 2027-08-16 |
| **Días restantes** | 364 |

## 🔄 Cómo renovar cada año

### Paso 1: Una semana antes del vencimiento
Ejecuta este comando para verificar el estado:

```powershell
cd c:\Users\johan\Downloads\CreditosPro_DEPLOY
.\.venv\Scripts\python.exe renewal_license.py --validate "$(python -c 'import os; from dotenv import load_dotenv; load_dotenv(); print(os.getenv("CREDITOSPRO_LICENSE_KEY"))')"
```

### Paso 2: Renovar la licencia (método automático - RECOMENDADO)

```powershell
cd c:\Users\johan\Downloads\CreditosPro_DEPLOY
.\.venv\Scripts\python.exe renewal_license.py --auto
```

**Qué hace:**
- Lee la licencia actual desde `.env`
- Verifica que sea válida
- Genera una nueva licencia con +365 días
- Guarda automáticamente en `.env`
- Registra el cambio en `licencias/empresas.json`

**Salida esperada:**
```
🔄 Modo automático: Renovando licencia actual...
  Empresa: ElRusso (ID: 1)
  Máquina: 0C773FA2129C81EDB9E7921A7D421A0C
  Licencia anterior expiraba: 2027-08-16

✅ Licencia renovada exitosamente:
  Nueva expiración: 2028-08-16
  Validez: 365 días

📝 Cambios guardados en:
  • .env (CREDITOSPRO_LICENSE_KEY)
  • licencias/empresas.json
```

### Paso 3: Reiniciar la aplicación

Después de renovar, reinicia la app para que cargue la nueva licencia:

```powershell
cd c:\Users\johan\Downloads\CreditosPro_DEPLOY
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Verifica en los logs que la licencia se validó correctamente.

## 🛠️ Alternativa: Renovación manual

Si prefieres generar la licencia manualmente (sin cargarla automáticamente):

```powershell
.\.venv\Scripts\python.exe renewal_license.py --machine "0C773FA2129C81EDB9E7921A7D421A0C" --empresa-id 1 --empresa "ElRusso" --dias 365
```

Esto te mostrará la nueva clave y te preguntará si quieres guardarla.

## 📋 Verificación después de renovar

Ejecuta este comando para confirmar que la renovación fue exitosa:

```powershell
.\.venv\Scripts\python.exe -c "import os; from dotenv import load_dotenv; load_dotenv(); import license_manager; print(license_manager.check_license())"
```

Deberías ver:
- `'valid': True`
- La fecha de vencimiento correcta (1 año desde hoy)
- `'days_left': 364` o similar

## ⚠️ En caso de problemas

### Si la renovación falla
1. Verifica que `.env` existe y tiene `CREDITOSPRO_LICENSE_KEY`
2. Verifica que `LICENSE_MASTER_KEY` esté presente en `.env`
3. Intenta con el modo manual para ver el error específico

### Si no reconoce la nueva licencia
1. Asegúrate de que el Machine ID sea el correcto:
   ```powershell
   .\.venv\Scripts\python.exe renewal_license.py --myid
   ```
2. La licencia se genera específicamente para ese Machine ID
3. No se puede usar en otro equipo

## 📅 Calendario de renovaciones

- **Fecha actual de generación**: 2026-08-16
- **Próxima renovación**: 2027-08-01 (15 días antes del vencimiento)
- **Última posible renovación**: 2027-08-16

## 🔐 Backup recomendado

Guarda una copia de la licencia en un lugar seguro:

```powershell
# Copiar .env a una ubicación segura
Copy-Item .env "C:\MisBackups\creditos_pro_license_$(Get-Date -Format 'yyyyMMdd').env"
```

O simplemente anotando:
- Fecha de emisión
- Fecha de expiración
- Machine ID
- Licencia (CPRO-...)

## 📝 Notas importantes

✅ **Buenas prácticas:**
- Renovar siempre 1-2 semanas antes del vencimiento
- Hacer backup de la licencia después de renovar
- Verificar que la app inicia correctamente después de renovar

❌ **Evitar:**
- No dejar que la licencia expire por completo
- No usar la misma licencia para múltiples equipos
- No compartir la licencia por email sin encriptar

---

**Para más detalles**, ver: [licencias/README.md](../licencias/README.md)
