# -*- coding: utf-8 -*-
"""
CreditosPro Cloud - Autenticación
Usa bcrypt directamente sin passlib para mayor compatibilidad
"""

import os
import datetime
import bcrypt
from typing import Optional

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from jose import JWTError, jwt

from app.database import get_db, Usuario

SECRET_KEY = os.getenv("SECRET_KEY", "creditospro-cloud-secret-2024!")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 8

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login", auto_error=False)


def hash_password(password: str) -> str:
    """Hash una contraseña usando bcrypt"""
    salt = bcrypt.gensalt(rounds=10)
    hashed = bcrypt.hashpw(password.encode('utf-8'), salt)
    return hashed.decode('utf-8')


def verify_password(plain: str, hashed: str) -> bool:
    """Verifica una contraseña contra su hash"""
    try:
        # Asegurar que el hashed es string (en caso de venir como bytes)
        if isinstance(hashed, bytes):
            hashed = hashed.decode('utf-8')
        return bcrypt.checkpw(plain.encode('utf-8'), hashed.encode('utf-8'))
    except Exception as e:
        # Loguear el error si es necesario en producción
        return False


def create_access_token(data: dict, expires_delta=None):
    to_encode = data.copy()
    expire = datetime.datetime.utcnow() + (
        expires_delta or datetime.timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def decode_token(token: str) -> Optional[dict]:
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError:
        return None


def get_token_from_request(request: Request) -> Optional[str]:
    token = request.cookies.get("access_token")
    if token and token.startswith("Bearer "):
        return token[7:]
    if token:
        return token
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
    return db.query(Usuario).filter(
        Usuario.username == username,
        Usuario.activo == True
    ).first()


def require_login(request: Request, db: Session = Depends(get_db)) -> Usuario:
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
    user = require_login(request, db)
    return user.empresa_id


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