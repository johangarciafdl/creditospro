# 🚀 Guía de Deployment - CreditosPro Cloud

## Configuración en Railway

Para que la aplicación funcione correctamente en Railway, asegúrate de tener estas variables de entorno configuradas:

### Variables Críticas

#### 1. **SECRET_KEY** ⚠️ OBLIGATORIO
```
SECRET_KEY=tu-secreto-aleatorio-super-seguro-aqui
```

**Importancia:** Esta variable es **CRÍTICA** para que las sesiones persistan entre reinicios.

**Problema sin configurar:** Las sesiones se pierden cada vez que Railway reinicia el contenedor.

**Cómo generarla:**
```python
import secrets
print(secrets.token_urlsafe(32))
```

O usa un generador en línea: https://generate-secret.vercel.app/

**Pasos para configurar en Railway:**
1. Ve a tu proyecto en Railway: https://railway.app
2. Abre el servicio de tu app
3. Ve a **Variables** tab
4. Click en **+ New Variable**
5. Nombre: `SECRET_KEY`
6. Valor: `tu-secreto-aleatorio` (ej: `abc123xyz789...`)
7. Click **Deploy**

---

#### 2. **DATABASE_URL** 
Ya configurado desde Supabase. Formato:
```
postgresql://user:password@host:port/database
```

Verifica que esté en Variables de Railway.

---

### Ejemplo de configuración completa en Railway

```
DATABASE_URL=postgresql://postgres:Jo681192*creditos@db.ivhcmdxwmeabwmnmjuhm.supabase.co:5432/postgres
SECRET_KEY=SuPerSecureRandomString123456789XYZ
PORT=8000
```

---

## Pasos de Deployment

### 1. Primer Deploy
```bash
# Desde tu repo con railway.toml
railway up
```

### 2. Configurar Variables de Entorno
- Railway detecta automáticamente las variables en el código
- Agrega `SECRET_KEY` manualmente en el dashboard

### 3. Verificar Logs
```bash
railway logs
```

Busca líneas como:
```
INFO:     Application startup complete
```

### 4. Probar la Sesión
1. Login en la app
2. Nota la cookie `access_token` en DevTools
3. Causa un reinicio (o espera a que Railway reinicie)
4. Verifica que sigues autenticado

---

## Troubleshooting

### ❌ "Sesión se pierde después de reinicio"
**Causa:** `SECRET_KEY` no configurado o diferente en cada reinicio
**Solución:** Agrega `SECRET_KEY` fija a las variables de Railway

### ❌ "Error 422 al guardar cliente"
**Causa:** Falta validación de zona_id
**Solución:** ✅ Ya corregido (v2.1+)
- Asegúrate de crear una zona primero
- O recarga la app después del deployment

### ❌ "Contraseña no funciona en setup"
**Causa:** Hash mismatch en bcrypt
**Solución:** ✅ Ya corregido (v2.1+)
- El endpoint `/debug-hash` fue eliminado por seguridad
- Las funciones de hash/verify fueron optimizadas

### ❌ "Caracteres acentuados causan error 500"
**Causa:** Encoding UTF-8 no declarado
**Solución:** ✅ Ya corregido (v2.1+)
- Se agregó `# -*- coding: utf-8 -*-` a todos los routers

---

## Redeployment después de correcciones

Después de aplicar estos fixes, ejecuta:

```bash
git add .
git commit -m "Fix: corregir bugs críticos v2.1"
git push origin main
```

Railway automáticamente detectará los cambios y hará deploy.

---

## Checklist de Go-Live

- [ ] ✅ SECRET_KEY configurada en Railway
- [ ] ✅ DATABASE_URL conectada a Supabase
- [ ] ✅ Crear zona inicial desde panel admin
- [ ] ✅ Crear cliente de prueba
- [ ] ✅ Crear préstamo de prueba
- [ ] ✅ Probar login/logout
- [ ] ✅ Probar cobros en celular
- [ ] ✅ Verificar PWA setup en Android

---

**Última actualización:** Abril 2026  
**Versión:** 3.0.0 (bugfixes aplicados)
