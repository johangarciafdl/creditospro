"""
CreditosPro v2.0 — Sistema de Gestión de Créditos y Cobros
FastAPI + SQLite + Autenticación JWT + WhatsApp Bot
"""
import uvicorn
import threading
import webbrowser
import time
from pathlib import Path
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from starlette.middleware.sessions import SessionMiddleware

from app.database import init_db
from app.routers import clientes, prestamos, cobros, zonas, reportes, whatsapp, dashboard, registro
from app.routers import auth
from app.services.scheduler import iniciar_scheduler
from app.utils.seed import seed_data_demo

BASE_DIR = Path(__file__).parent.parent


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    seed_data_demo()
    iniciar_scheduler()
    yield


app = FastAPI(
    redirect_slashes=False,
    title="CreditosPro v2.0",
    description="Sistema de gestión de créditos y cobros",
    version="2.0.0",
    lifespan=lifespan,
    docs_url="/api/docs",
)

# Middleware de sesiones (necesario para Starlette sessions)
app.add_middleware(
    SessionMiddleware,
    secret_key="creditospro-session-secret-2025"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:8000", "http://localhost:8000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Static files
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")
app.mount("/uploads", StaticFiles(directory=str(BASE_DIR / "uploads")), name="uploads")

templates = Jinja2Templates(directory="templates")

# Routers
app.include_router(auth.router, prefix="/auth", tags=["Auth"])
app.include_router(registro.router, prefix="/registro", tags=["Registro"])
app.include_router(dashboard.router, tags=["Dashboard"])
app.include_router(clientes.router, prefix="/clientes", tags=["Clientes"])
app.include_router(prestamos.router, prefix="/prestamos", tags=["Préstamos"])
app.include_router(cobros.router, prefix="/cobros", tags=["Cobros"])
app.include_router(zonas.router, prefix="/zonas", tags=["Zonas"])
app.include_router(reportes.router, prefix="/reportes", tags=["Reportes"])
app.include_router(whatsapp.router, prefix="/whatsapp", tags=["WhatsApp Bot"])


@app.get("/")
async def root(request: Request):
    # Verificar si hay sesión
    from app.routers.auth import get_current_user
    from app.database import SessionLocal
    db = SessionLocal()
    try:
        user = get_current_user(request, db)
    finally:
        db.close()
    if not user:
        return RedirectResponse(url="/auth/login", status_code=302)
    return RedirectResponse(url="/dashboard", status_code=302)


def abrir_navegador():
    time.sleep(1.5)
    webbrowser.open("http://127.0.0.1:8000")


def run():
    t = threading.Thread(target=abrir_navegador, daemon=True)
    t.start()
    uvicorn.run(
        "app.main:app",
        host="127.0.0.1",
        port=8000,
        log_level="warning",
        reload=False,
    )


if __name__ == "__main__":
    run()
