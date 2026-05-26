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
        print(f"[CreditosPro] Variables cargadas desde {_dotenv_path}")
    except ImportError:
        pass

from fastapi import FastAPI, Request, Depends, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse, FileResponse
from starlette.middleware.sessions import SessionMiddleware

from app.database import init_db, IS_SQLITE, get_db, Cliente
from app.routers import clientes, prestamos, cobros, zonas, reportes, whatsapp, dashboard, registro, pwa, selector
from app.routers import license_router
from app.utils.license_middleware import LicenseMiddleware
from app.routers import auth
from app.services.scheduler import iniciar_scheduler
from app.utils.seed import seed_data_demo
from app.utils.csrf import CSRFMiddleware
from app.utils.rate_limit import InMemoryRateLimitMiddleware
from app.utils.settings import settings
from app.utils.zone_permissions import require_zone_access

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).parent.parent


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Check license
    try:
        import license_manager as lm
        _lic = lm.check_license()
        app.state.license_valid = _lic.get("valid", False)
        app.state.license_info = _lic
    except Exception:
        dev_mode = settings.ENVIRONMENT == "development"
        app.state.license_valid = dev_mode
        app.state.license_info = {"valid": dev_mode, "dev_mode": dev_mode}
    """Inicialización segura de la aplicación con manejo de errores."""
    logger.info("Iniciando CreditosPro...")

    # Verificar variables de entorno críticas
    required_vars = ["DATABASE_URL", "SECRET_KEY"]
    missing = [v for v in required_vars if not os.getenv(v)]
    if missing:
        logger.error(f"Faltan variables de entorno requeridas: {', '.join(missing)}")
        logger.error("Crea un archivo .env a partir de .env.example")
        sys.exit(1)

    # Conexión a base de datos con timeout y fallback informativo
    try:
        logger.info("Conectando a la base de datos...")
        init_db()
        logger.info("✅ Base de datos conectada correctamente")
    except Exception as e:
        logger.error(f"❌ Error conectando a la base de datos: {e}")
        if not IS_SQLITE:
            logger.error(
                "No se pudo conectar a PostgreSQL. Verifica tu DATABASE_URL en .env\n"
                "Para desarrollo local, usa: sqlite:///./creditospro.db"
            )
        sys.exit(1)

    # Seed data (solo en desarrollo con ENABLE_SEED_DATA=1)
    try:
        seed_data_demo()
    except Exception as e:
        logger.warning(f"Warning al cargar datos demo: {e}")

    # Iniciar scheduler
    try:
        iniciar_scheduler()
        logger.info("✅ Scheduler iniciado")
    except Exception as e:
        logger.error(f"Error iniciando scheduler: {e}")

    yield
    logger.info("CreditosPro finalizado")


app = FastAPI(
    redirect_slashes=False,
    title="CreditosPro v2.1",
    description="Sistema de gestión de créditos y cobros",
    version="2.1.0",
    lifespan=lifespan,
    docs_url="/api/docs",
)

# Middleware de sesiones (necesario para Starlette sessions)
session_secret = os.getenv("SESSION_SECRET_KEY") or os.getenv("SECRET_KEY")
if not session_secret:
    raise RuntimeError("SESSION_SECRET_KEY o SECRET_KEY es obligatoria")
app.add_middleware(
    SessionMiddleware,
    secret_key=session_secret
)
app.add_middleware(LicenseMiddleware)
app.add_middleware(CSRFMiddleware)
app.add_middleware(InMemoryRateLimitMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

# Static files
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")

templates = Jinja2Templates(directory="templates")


def get_license_info() -> dict:
    try:
        import license_manager as lm
        return lm.check_license()
    except Exception:
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
    from app.database import SessionLocal
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
    return {"status": "healthy", "version": "2.1.0"}


def abrir_navegador():
    time.sleep(1.5)
    webbrowser.open("http://127.0.0.1:8000")


def run():
    t = threading.Thread(target=abrir_navegador, daemon=True)
    t.start()

    port = int(os.getenv("PORT", "8000"))
    no_browser = os.getenv("CREDITOSPRO_NO_BROWSER", "0") == "1"
    if no_browser:
        t.join(timeout=0.1)

    uvicorn.run(
        "app.main:app",
        host="127.0.0.1",
        port=port,
        log_level="warning",
        reload=False,
    )


if __name__ == "__main__":
    run()
