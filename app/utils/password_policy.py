"""
Politica de contrasenas centralizada.

Todos los endpoints que crean o cambian contrasenas deben usar estas
funciones para mantener consistencia. Antes habia min_length=6 en algunos
sitios y =8 en otros, sin validacion de complejidad.
"""
import re
from fastapi import HTTPException


MIN_LENGTH = 8
MAX_LENGTH = 128


def validar_password(password: str) -> str:
    """Valida una contrasena contra la politica de la app.

    Reglas:
    - Entre 8 y 128 caracteres
    - Al menos 1 letra minuscula
    - Al menos 1 letra mayuscula O 1 digito O 1 simbolo
    - Sin espacios al inicio/final
    - Maximo 3 caracteres repetidos consecutivos (defensa contra "aaaaaa")

    Raises HTTPException 400 si no cumple.
    Returns la contrasena limpia.
    """
    if password is None:
        raise HTTPException(400, "Contrasena requerida")
    pwd = password.strip()
    if not pwd:
        raise HTTPException(400, "Contrasena requerida")
    if len(pwd) < MIN_LENGTH:
        raise HTTPException(400, f"La contrasena debe tener al menos {MIN_LENGTH} caracteres")
    if len(pwd) > MAX_LENGTH:
        raise HTTPException(400, f"La contrasena no puede tener mas de {MAX_LENGTH} caracteres")
    if pwd != password:
        raise HTTPException(400, "La contrasena no puede empezar ni terminar con espacios")
    if not re.search(r"[a-z]", pwd):
        raise HTTPException(400, "La contrasena debe tener al menos una letra minuscula")
    # Complejidad: mayuscula O digito O simbolo
    if not (re.search(r"[A-Z]", pwd) or re.search(r"\d", pwd) or re.search(r"[^A-Za-z0-9]", pwd)):
        raise HTTPException(
            400,
            "La contrasena debe incluir una mayuscula, un numero o un simbolo",
        )
    if re.search(r"(.)\1{3,}", pwd):
        raise HTTPException(400, "Demasiados caracteres repetidos consecutivos")
    return pwd


def validar_cambio_password(
    actual: str, nueva: str, confirmar: str, db_user, verify_fn
) -> None:
    """Valida un cambio de contrasena: actual correcta + nueva cumple politica.

    Args:
        actual: contrasena actual que el usuario escribio
        nueva: contrasena nueva
        confirmar: confirmacion
        db_user: el objeto Usuario de la BD (debe tener password_hash)
        verify_fn: callable verify_password(plain, hashed) -> bool
    """
    if not verify_fn(actual, db_user.password_hash):
        raise HTTPException(401, "La contrasena actual es incorrecta")
    if nueva != confirmar:
        raise HTTPException(400, "La nueva contrasena y la confirmacion no coinciden")
    if actual == nueva:
        raise HTTPException(400, "La nueva contrasena debe ser diferente a la actual")
    validar_password(nueva)
