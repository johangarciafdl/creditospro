"""
CreditosPro Cloud — Main Application
FastAPI + PostgreSQL (Supabase) + Multi-tenant
"""

import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request, Depends
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from fastapi.exceptions import HTTPException as FastAPIHTTPException
from starlette.middleware.sessions import SessionMiddleware

from app.database import init_db, get_db, Empresa
from app.auth import get_current_user, require_login
from app.routers import (
    auth as auth_router, dashboard, clientes, prestamos,
    cobros, zonas, reportes, usuarios, setup, app_cobrador
)

BASE_DIR = Path(__file__).parent.parent


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(
    title="CreditosPro Cloud",
    version="3.0.0",
    lifespan=lifespan,
    docs_url="/api/docs",
)

# ── MIDDLEWARE ────────────────────────────────────────────────────────────────
app.add_middleware(
    SessionMiddleware,
    secret_key=os.getenv("SECRET_KEY", "creditospro-cloud-secret-2024!")
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── AUTH MIDDLEWARE ───────────────────────────────────────────────────────────
@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    path = request.url.path
    publicas = ["/auth/", "/static/", "/uploads/", "/setup", "/favicon.ico", "/api/"]
    if any(path.startswith(p) for p in publicas):
        return await call_next(request)
    token = request.cookies.get("access_token")
    if not token:
        return RedirectResponse(url=f"/auth/login?next={path}", status_code=303)
    return await call_next(request)

# ── STATIC & TEMPLATES ───────────────────────────────────────────────────────
static_dir = BASE_DIR / "static"
static_dir.mkdir(exist_ok=True)
uploads_dir = BASE_DIR / "uploads"
uploads_dir.mkdir(exist_ok=True)

app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")
app.mount("/uploads", StaticFiles(directory=str(uploads_dir)), name="uploads")
templates = Jinja2Templates(directory="templates")

# ── ROUTERS ──────────────────────────────────────────────────────────────────
app.include_router(setup.router,         prefix="/setup",    tags=["Setup"])
app.include_router(auth_router.router,   prefix="/auth",     tags=["Auth"])
app.include_router(dashboard.router,     tags=["Dashboard"])
app.include_router(clientes.router,      prefix="/clientes", tags=["Clientes"])
app.include_router(prestamos.router,     prefix="/prestamos",tags=["Préstamos"])
app.include_router(cobros.router,        prefix="/cobros",   tags=["Cobros"])
app.include_router(zonas.router,         prefix="/zonas",    tags=["Zonas"])
app.include_router(reportes.router,      prefix="/reportes", tags=["Reportes"])
app.include_router(usuarios.router,      prefix="/usuarios", tags=["Usuarios"])
app.include_router(app_cobrador.router,  prefix="/app",      tags=["App Cobrador"])


@app.get("/")
async def root(request: Request, db=Depends(get_db)):
    # Si no hay empresas configuradas → pantalla de setup
    empresa = db.query(Empresa).filter(Empresa.setup_completo == True).first()
    if not empresa:
        return RedirectResponse(url="/setup", status_code=303)
    return RedirectResponse(url="/dashboard", status_code=303)


# ── EXCEPTION HANDLERS ───────────────────────────────────────────────────────
@app.exception_handler(FastAPIHTTPException)
async def http_exception_handler(request: Request, exc: FastAPIHTTPException):
    if exc.status_code in (303, 307) and exc.headers.get("Location"):
        return RedirectResponse(url=exc.headers["Location"], status_code=exc.status_code)
    if exc.status_code == 401:
        return RedirectResponse(url="/auth/login", status_code=303)
    return templates.TemplateResponse("error.html", {
        "request": request,
        "codigo": exc.status_code,
        "mensaje": exc.detail,
    }, status_code=exc.status_code)
