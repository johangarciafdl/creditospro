# CreditosPro v2.0 — Guía de Despliegue en la Nube

## Arquitectura recomendada

```
┌─────────────────────────────────────────────────────────────┐
│                    SERVIDOR CLOUD (Railway)                  │
│                                                             │
│   FastAPI + SQLite  →  https://creditospro.railway.app      │
│   ┌──────────────────────────────────────────────────┐      │
│   │  /dashboard  /clientes  /cobros  /prestamos      │      │
│   │  /auth/login  /whatsapp  /reportes               │      │
│   └──────────────────────────────────────────────────┘      │
└─────────────────────────────────────────────────────────────┘
         ▲                              ▲
         │ HTTPS                        │ HTTPS
         │                              │
┌────────────────┐            ┌─────────────────────────┐
│  .exe Admin    │            │  Cobradores (celular)   │
│  (Windows PC)  │            │  Navegador / PWA        │
│                │            │                         │
│  CreditosProAdmin.exe       │  cualquier navegador    │
│  --url https://...          │  Chrome / Firefox       │
└────────────────┘            └─────────────────────────┘
```

## Paso 1: Preparar el proyecto

```bash
# Instalar Railway CLI
npm install -g @railway/cli

# Login
railway login
```

## Paso 2: Crear Procfile

```
# Procfile
web: uvicorn app.main:app --host 0.0.0.0 --port $PORT
```

## Paso 3: Configurar variables de entorno en Railway

```
CREDITOSPRO_SECRET=tu-clave-secreta-de-produccion-muy-larga
CREDITOSPRO_PORT=8000
```

## Paso 4: Subir a Railway

```bash
railway init
railway up
```

## Paso 5: Usar el .exe en modo remoto

Una vez desplegado, el administrador en su PC usa:

```
CreditosProAdmin.exe --url https://creditospro.railway.app
```

Los cobradores abren en su celular:
```
https://creditospro.railway.app
```

Ambos acceden a la misma base de datos → sincronización total.

## Alternativas de hosting gratuito

| Plataforma | Límite gratis | Comando |
|------------|--------------|---------|
| Railway | 500 hrs/mes | `railway up` |
| Render | Suspende tras 15min inactivo | `render deploy` |
| Fly.io | 3 VMs gratis | `fly launch` |

## Notas de seguridad para producción

1. Cambiar `SECRET_KEY` en `app/utils/security.py`
2. Cambiar contraseñas demo (`admin123`) desde el panel de usuarios
3. Habilitar HTTPS (Railway lo hace automático)
4. Configurar backup automático de `data/creditospro.db`

## PWA para cobradores (opcional)

Agrega este `manifest.json` en `/static/` para que los cobradores
puedan instalar la web como app en su celular:

```json
{
  "name": "CreditosPro Cobrador",
  "short_name": "Cobros",
  "start_url": "/cobros",
  "display": "standalone",
  "background_color": "#0f3d28",
  "theme_color": "#2d9e6e",
  "icons": [{"src": "/static/img/icon.png", "sizes": "192x192"}]
}
```
