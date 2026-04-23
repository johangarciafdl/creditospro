"""
CreditosPro v2.0 - Autenticación y Seguridad
Sistema de login con JWT, roles y rate limiting
"""

import os
import datetime
from typing import Optional
from pathlib import Path

from fastapi import Depends, HTTPException, Request, status, Form
from fastapi.responses import RedirectResponse
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from jose import JWTError, jwt
from passlib.context import CryptContext

from app.database import get_db, Usuario

# ── CONFIG ──────────────────────────────────────────────────────────────────
SECRET_KEY = os.getenv("SECRET_KEY", "creditospro-secret-key-cambia-en-produccion-2024!")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 8  # 8 horas

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login", auto_error=False)

# ── PASSWORDS ────────────────────────────────────────────────────────────────

def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


# ── JWT ──────────────────────────────────────────────────────────────────────

def create_access_token(data: dict, expires_delta: Optional[datetime.timedelta] = None):
    to_encode = data.copy()
    expire = datetime.datetime.utcnow() + (expires_delta or datetime.timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def decode_token(token: str) -> Optional[dict]:
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError:
        return None


# ── OBTENER USUARIO ACTUAL ────────────────────────────────────────────────────

def get_token_from_request(request: Request) -> Optional[str]:
    """Obtiene token de cookie o header Authorization"""
    # Primero busca en cookie (web)
    token = request.cookies.get("access_token")
    if token and token.startswith("Bearer "):
        return token[7:]
    if token:
        return token
    # Luego busca en header (API)
    auth = request.headers.get("Authorization")
    if auth and auth.startswith("Bearer "):
        return auth[7:]
    return None


def get_current_user(request: Request, db: Session = Depends(get_db)) -> Optional[Usuario]:
    token = get_token_from_request(request)
    if not token:
        return None
    payload = decode_token(token)
    if not payload:
        return None
    username = payload.get("sub")
    if not username:
        return None
    user = db.query(Usuario).filter(Usuario.username == username, Usuario.activo == True).first()
    return user


def require_login(request: Request, db: Session = Depends(get_db)) -> Usuario:
    """Dependency que requiere login — redirige a /auth/login si no hay sesión"""
    user = get_current_user(request, db)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_303_SEE_OTHER,
            headers={"Location": f"/auth/login?next={request.url.path}"},
        )
    return user


def require_admin(request: Request, db: Session = Depends(get_db)) -> Usuario:
    user = require_login(request, db)
    if user.rol not in ("admin", "superadmin"):
        raise HTTPException(status_code=403, detail="Se requiere rol administrador")
    return user


def get_current_empresa(request: Request, db: Session = Depends(get_db)) -> int:
    """Obtiene el ID de la empresa del usuario actual para multi-tenancy"""
    user = require_login(request, db)
    return user.empresa_id


# ── AUTENTICAR USUARIO ────────────────────────────────────────────────────────

def authenticate_user(username: str, password: str, db: Session) -> Optional[Usuario]:
    user = db.query(Usuario).filter(
        Usuario.username == username,
        Usuario.activo == True
    ).first()
    if not user:
        return None
    if not verify_password(password, user.password_hash):
        return None
    return user
