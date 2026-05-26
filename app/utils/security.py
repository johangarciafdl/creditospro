"""
CreditosPro v2.1 - Seguridad
bcrypt directo (compatible con bcrypt >= 4.0) + JWT con python-jose
"""
import os
import datetime
from typing import Optional

from app.utils.settings import settings

ALGORITHM = "HS256"

# bcrypt directo, sin passlib (compatible con Python 3.12+ y bcrypt 4.x)
import bcrypt


def get_password_hash(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except Exception:
        return False


from jose import JWTError, jwt


def create_access_token(data: dict) -> str:
    to_encode = data.copy()
    expire = datetime.datetime.utcnow() + datetime.timedelta(hours=settings.ACCESS_TOKEN_EXPIRE_HOURS)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=ALGORITHM)


def decode_token(token: str) -> Optional[dict]:
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except JWTError:
        return None