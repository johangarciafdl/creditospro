"""
validators.py — Validadores y helpers compartidos entre routers.
Centraliza la validación de inputs para evitar duplicación.
"""
import re
from io import BytesIO
from pathlib import Path
from typing import Optional
from fastapi import HTTPException
from PIL import Image, ImageOps, UnidentifiedImageError


# ── Expresiones regulares ──────────────────────────────────────────────────────
CEDULA_RE = re.compile(r'^[0-9A-Za-z\-]{3,20}$')
NOMBRE_RE = re.compile(r'^[A-Za-záéíóúÁÉÍÓÚñÑüÜ\s\.\-]{2,200}$')
TEL_RE = re.compile(r'^[\d\+\-\s\(\)]{7,20}$')


def limpiar_texto(s: str, max_len: int = 200) -> str:
    """Strip y limitar longitud — previene payloads gigantes."""
    return (s or "").strip()[:max_len]


def validar_cedula(cedula: str) -> str:
    c = limpiar_texto(cedula, 20)
    if not CEDULA_RE.match(c):
        raise HTTPException(400, "Cédula inválida")
    return c


def validar_nombre(nombre: str) -> str:
    n = limpiar_texto(nombre, 200)
    if not NOMBRE_RE.match(n):
        raise HTTPException(400, "Nombre contiene caracteres no permitidos")
    return n


def validar_telefono(tel: str, requerido: bool = True) -> Optional[str]:
    t = limpiar_texto(tel, 20)
    if not t:
        if requerido:
            raise HTTPException(400, "Teléfono requerido")
        return None
    if not TEL_RE.match(t):
        raise HTTPException(400, "Teléfono inválido")
    return t


def validar_numero_positivo(valor, nombre: str = "valor", minimo: float = 0.01, maximo: float = 100_000_000) -> float:
    """Valida que un valor numérico esté dentro de un rango."""
    try:
        v = float(valor)
    except (TypeError, ValueError):
        raise HTTPException(400, f"{nombre} debe ser un número válido")
    if v < minimo or v > maximo:
        raise HTTPException(400, f"{nombre} debe estar entre {minimo} y {maximo}")
    return v


def validar_entero_positivo(valor, nombre: str = "valor", minimo: int = 1, maximo: int = 10_000_000) -> int:
    """Valida que un valor entero esté dentro de un rango."""
    try:
        v = int(valor)
    except (TypeError, ValueError):
        raise HTTPException(400, f"{nombre} debe ser un número entero válido")
    if v < minimo or v > maximo:
        raise HTTPException(400, f"{nombre} debe estar entre {minimo} y {maximo}")
    return v


def sanitizar_imagen_subida(filename: str, contenido: bytes, max_bytes: int = 5 * 1024 * 1024) -> tuple[str, bytes]:
    """Valida una imagen por contenido y la regraba sin metadatos EXIF."""
    ext = Path(filename or "").suffix.lower()
    formatos = {
        ".jpg": ("JPEG", ".jpg"),
        ".jpeg": ("JPEG", ".jpg"),
        ".png": ("PNG", ".png"),
        ".webp": ("WEBP", ".webp"),
    }
    if ext not in formatos:
        raise HTTPException(400, "Solo se permiten imagenes JPG, PNG o WEBP")
    if not contenido or len(contenido) > max_bytes:
        raise HTTPException(400, "Imagen demasiado grande (max 5MB)")

    try:
        with Image.open(BytesIO(contenido)) as img:
            img.verify()
        with Image.open(BytesIO(contenido)) as img:
            img = ImageOps.exif_transpose(img)
            formato, ext_normalizada = formatos[ext]
            if formato == "JPEG" and img.mode not in ("RGB", "L"):
                img = img.convert("RGB")
            elif formato in ("PNG", "WEBP") and img.mode not in ("RGB", "RGBA", "L"):
                img = img.convert("RGBA")
            salida = BytesIO()
            kwargs = {"format": formato}
            if formato == "JPEG":
                kwargs.update({"quality": 85, "optimize": True})
            elif formato == "WEBP":
                kwargs.update({"quality": 85, "method": 4})
            img.save(salida, **kwargs)
    except (UnidentifiedImageError, OSError, ValueError):
        raise HTTPException(400, "El archivo no es una imagen valida")

    data = salida.getvalue()
    if len(data) > max_bytes:
        raise HTTPException(400, "Imagen demasiado grande tras procesarla")
    return ext_normalizada, data
