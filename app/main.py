"""
CreditosPro v2.1 — Sistema de Gestión de Créditos y Cobros
FastAPI + PostgreSQL/SQLite + Autenticación JWT + WhatsApp Bot
"""
import sys
import os
import uvicorn
import threading
import webbrowser
import time
import logging
from pathlib import Path
from contextlib import asynccontextmanager

# Cargar .env temprano para que los imports de settings funcionen
_base_dir = Path(__file__).resolve().parent.parent
_dotenv_path = _base_dir / ".env"
if _dotenv_path.exists():
    try:
        from dotenv import load_dotenv
        load_dotenv(_dotenv_path)
        logging.getLogger(__name__).info("Variables cargadas desde %s", _dotenv_path)
    except ImportError:
        pass

from fastapi import FastAPI, Request, Depends, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import RedirectResponse, FileResponse, JSONResponse
from sqlalchemy import text
from starlette.middleware.sessions import SessionMiddleware

from app.database import init_db, IS_SQLITE, get_db, Cliente, SessionLocal
from app.routers import clientes, prestamos, cobros, zonas, reportes, whatsapp, dashboard, registro, pwa, selector
from app.routers import license_router
from app.utils.license_middleware import LicenseMiddleware
from app.routers import auth
from app.services.scheduler import iniciar_scheduler
from app.utils.seed import seed_data_demo
from app.utils.csrf import CSRFMiddleware
from app.utils.rate_limit import InMemoryRateLimitMiddleware, init_middleware as init_rate_limit
from app.utils.security_headers import SecurityHeadersMiddleware
from app.utils.request_id import RequestIDMiddleware
from app.utils.body_size_limit import BodySizeLimitMiddleware
from app.utils.settings import settings
from app.utils.zone_permissions import require_zone_access

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [%(request_id)s] %(name)s: %(message)s",
)
# Inyectar filtro que agrega request_id a cada LogRecord
from app.utils.request_id import RequestIDFilter
for h in logging.getLogger().handlers:
    h.addFilter(RequestIDFilter())
logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).parent.parent


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 1) Check license rapido: archivo → env var
    try:
        import license_manager as lm
        _lic = lm.check_license()
        app.state.license_valid = _lic.get("valid", False)
        app.state.license_info = _lic
    except Exception:
        logger.warning("license_manager no disponible al arrancar", exc_info=True)
        dev_mode = settings.ENVIRONMENT == "development"
        app.state.license_valid = dev_mode
        app.state.license_info = {"valid": dev_mode, "dev_mode": dev_mode}

    logger.info("Iniciando CreditosPro...")

    # Verificar variables de entorno críticas
    required_vars = ["DATABASE_URL", "SECRET_KEY"]
    missing = [v for v in required_vars if not os.getenv(v)]
    if missing:
        logger.error("Faltan variables de entorno requeridas: %s", ", ".join(missing))
        logger.error("Crea un archivo .env a partir de .env.example")
        sys.exit(1)

    if settings.IS_PRODUCTION and not os.getenv("SESSION_SECRET_KEY", "").strip():
        logger.warning(
            "SESSION_SECRET_KEY no esta definida; se usara SECRET_KEY como respaldo. "
            "Configura ambas variables por separado en produccion."
        )

    # Conexión a base de datos con manejo de errores
    try:
        logger.info("Conectando a la base de datos...")
        init_db()
        logger.info("Base de datos conectada correctamente")
    except Exception as e:
        logger.exception("Error conectando a la base de datos: %s", e)
        if not IS_SQLITE:
            logger.error(
                "No se pudo conectar a PostgreSQL. Verifica tu DATABASE_URL en .env\n"
                "Para desarrollo local, usa: sqlite:///./creditospro.db"
            )
        sys.exit(1)

    # 2) Si la licencia no es valida por archivo/env, buscar en la DB
    #    (la tabla ya existe porque init_db() ya corrió)
    if not app.state.license_valid:
        try:
            import license_manager as lm
            from app.database import SessionLocal, LicenciaActivada
            db = SessionLocal()
            try:
                fp = lm.get_fingerprint()
                db_lic = db.query(LicenciaActivada).filter(
                    LicenciaActivada.machine_id == fp,
                    LicenciaActivada.activa == True,
                ).first()
                if db_lic:
                    _lic = lm.validate_license(db_lic.license_key)
                    app.state.license_valid = _lic.get("valid", False)
                    app.state.license_info = _lic
                    logger.info("Licencia cargada desde DB para machine %s", fp[:8])
            finally:
                db.close()
        except Exception:
            logger.debug("No se pudo consultar licencias en DB", exc_info=True)

    # Seed data (solo en desarrollo con ENABLE_SEED_DATA=1)
    try:
        seed_data_demo()
    except Exception:
        logger.warning("Warning al cargar datos demo", exc_info=True)

    # Iniciar scheduler
    try:
        iniciar_scheduler()
        logger.info("Scheduler iniciado")
    except Exception:
        logger.exception("Error iniciando scheduler")

    yield
    logger.info("CreditosPro finalizado")


app = FastAPI(
    redirect_slashes=False,
    title="CreditosPro v2.1",
    description="Sistema de gestión de créditos y cobros",
    version="2.1.0",
    lifespan=lifespan,
    docs_url="/api/docs" if settings.ENVIRONMENT != "production" else None,
    redoc_url=None,
    openapi_url="/api/openapi.json" if settings.ENVIRONMENT != "production" else None,
)

# Middleware de sesiones (clave separada de la SECRET_KEY de JWT cuando sea posible)
session_secret = os.getenv("SESSION_SECRET_KEY") or os.getenv("SECRET_KEY")
if not session_secret:
    raise RuntimeError("SESSION_SECRET_KEY o SECRET_KEY es obligatoria")
app.add_middleware(
    SessionMiddleware,
    secret_key=session_secret,
    https_only=settings.IS_PRODUCTION,
    same_site="strict",
)

# El orden importa: ultimo en agregar = primero en ejecutar.
# 1) RequestID: debe ser el PRIMERO que corre para que todos los demas
#    puedan correlacionar logs por request_id.
app.add_middleware(RequestIDMiddleware)
# 2) BodySize: antes que el resto para rechazar payloads grandes rapido.
app.add_middleware(BodySizeLimitMiddleware)
app.add_middleware(LicenseMiddleware)
app.add_middleware(CSRFMiddleware)
app.add_middleware(InMemoryRateLimitMiddleware)
app.add_middleware(SecurityHeadersMiddleware, is_production=settings.IS_PRODUCTION, use_strict_csp=False)
app.add_middleware(GZipMiddleware, minimum_size=1024)

# CORS endurecido: lista blanca de headers, sin wildcard cuando se usan credenciales.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=[
        "Authorization",
        "Content-Type",
        "X-CSRF-Token",
        "X-Requested-With",
    ],
    max_age=600,
)

# Static files
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")

templates = Jinja2Templates(directory="templates")

# Inyectar el nonce CSP en cada render: los templates pueden usar
# {{ csp_nonce }} dentro de <script> y <style> inline legitimos.
from app.utils.security_headers import _csp_nonce_var
templates.env.globals["csp_nonce"] = lambda: _csp_nonce_var.get() or ""


def get_license_info() -> dict:
    try:
        import license_manager as lm
        return lm.check_license()
    except Exception:
        logger.warning("get_license_info: license_manager no disponible", exc_info=True)
        dev_mode = settings.ENVIRONMENT == "development"
        return {"valid": dev_mode, "dev_mode": dev_mode}


# Routers
app.include_router(auth.router, prefix="/auth", tags=["Auth"])
app.include_router(registro.router, prefix="/registro", tags=["Registro"])
app.include_router(selector.router, tags=["Selector"])
app.include_router(license_router.router, prefix="/license", tags=["License"])
app.include_router(dashboard.router, tags=["Dashboard"])
app.include_router(clientes.router, prefix="/clientes", tags=["Clientes"])
app.include_router(prestamos.router, prefix="/prestamos", tags=["Préstamos"])
app.include_router(cobros.router, prefix="/cobros", tags=["Cobros"])
app.include_router(zonas.router, prefix="/zonas", tags=["Zonas"])
app.include_router(reportes.router, prefix="/reportes", tags=["Reportes"])
app.include_router(whatsapp.router, prefix="/whatsapp", tags=["WhatsApp Bot"])
app.include_router(pwa.router, tags=["PWA"])


@app.get("/")
async def root(request: Request):
    from app.routers.auth import get_current_user
    license_info = getattr(request.app.state, "license_info", None) or get_license_info()
    request.app.state.license_valid = license_info.get("valid", False)
    request.app.state.license_info = license_info

    db = SessionLocal()
    try:
        user = get_current_user(request, db)
    finally:
        db.close()

    if user and license_info.get("valid"):
        return RedirectResponse(url="/dashboard", status_code=302)

    license_valid = bool(license_info.get("valid"))
    return templates.TemplateResponse(request, "inicio.html", {
        "software_name": settings.SOFTWARE_NAME,
        "software_owner": settings.SOFTWARE_OWNER,
        "license_valid": license_valid,
        "start_url": "/seleccionar-empresa" if license_valid else "/license/activar",
        "start_label": "Iniciar" if license_valid else "Activar",
    })


@app.get("/inicio")
async def inicio(request: Request):
    return await root(request)


@app.get("/uploads/fotos/{filename}")
async def foto_cliente(filename: str, request: Request, db=Depends(get_db)):
    user = auth.get_current_user(request, db)
    if not user:
        raise HTTPException(status_code=404)

    # Bloquear path traversal explicitamente (separadores y secuencias relativas)
    if "/" in filename or "\\" in filename or ".." in filename or filename.startswith("."):
        raise HTTPException(status_code=404)

    cliente = db.query(Cliente).filter(
        Cliente.empresa_id == user.empresa_id,
        Cliente.foto_path == f"fotos/{filename}",
        Cliente.activo == True,
    ).first()
    if not cliente or not require_zone_access(db, user, cliente.zona_id):
        raise HTTPException(status_code=404)

    base = (BASE_DIR / "uploads" / "fotos").resolve()
    ruta = (base / filename).resolve()
    if base not in ruta.parents or not ruta.is_file():
        raise HTTPException(status_code=404)
    return FileResponse(str(ruta))


@app.get("/health")
async def health_check():
    """Healthcheck que verifica DB y licencia. Devuelve 503 si algo falla."""
    db_ok = False
    db_error = None
    db = SessionLocal()
    try:
        db.execute(text("SELECT 1"))
        db_ok = True
    except Exception as e:
        db_error = str(e)[:200]
        logger.warning("Healthcheck DB fallo: %s", db_error)
    finally:
        db.close()

    license_valid = bool(getattr(app.state, "license_valid", False))
    payload = {
        "status": "healthy" if db_ok else "unhealthy",
        "version": "2.1.0",
        "database": "ok" if db_ok else "error",
        "license_valid": license_valid,
    }
    if db_error:
        payload["database_error"] = db_error
    return JSONResponse(payload, status_code=200 if db_ok else 503)


def abrir_navegador(url: str = "http://127.0.0.1:8000"):
    time.sleep(1.5)
    webbrowser.open(url)


def run():
    port = int(os.getenv("PORT", "8000"))
    host = os.getenv("HOST", "127.0.0.1")
    no_browser = os.getenv("CREDITOSPRO_NO_BROWSER", "0") == "1"

    if not no_browser:
        url = f"http://127.0.0.1:{port}"
        threading.Thread(target=abrir_navegador, args=(url,), daemon=True).start()

    uvicorn.run(
        "app.main:app",
        host=host,
        port=port,
        log_level="warning",
        reload=False,
    )


if __name__ == "__main__":
    run()
