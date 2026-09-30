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
USERNAME_RE = re.compile(r'^[a-z0-9_.\-]{3,100}$')


def limpiar_texto(s: str, max_len: int = 200) -> str:
    """Strip y limitar longitud — previene payloads gigantes."""
    return (s or "").strip()[:max_len]


def sin_html(texto: str, campo: str, max_len: int = 200) -> str:
    """Limpia y rechaza '<'/'>' -- para texto libre sin formato fijo (direcciones,
    mensajes, nombres de zona) que se muestra en el frontend: en vez de una lista
    blanca estricta, bloquea solo lo que permitiria inyectar HTML/JS."""
    t = limpiar_texto(texto, max_len)
    if "<" in t or ">" in t:
        raise HTTPException(400, f"{campo} no puede contener '<' o '>'")
    return t


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


# ── Texto que escribe una persona ─────────────────────────────────────────────
# Un programa no puede saber si "resdads" es un apellido o si "almuerzo" era
# de verdad un almuerzo. Lo que si puede es rechazar lo que NINGUN nombre ni
# ninguna descripcion tiene: sopas de signos (".,.,.,+´+"), palabras sin una
# sola vocal o con cinco consonantes seguidas ("mtdfgdg"), un caracter
# repetido ("aaaaa"), numeros pegados al final de una palabra ("almuerzo23").
# Es un filtro de basura evidente, no un corrector: lo que pasa es texto con
# forma de texto, que es lo que un reporte necesita para poder leerse.
_LETRA = "A-Za-zÁÉÍÓÚÜÑáéíóúüñ"
_VOCALES = set("aeiouyáéíóúüAEIOUYÁÉÍÓÚÜ")
_CONSONANTES_SEGUIDAS = re.compile(r"[bcdfghjklmnñpqrstvwxz]{5,}", re.IGNORECASE)
DESCRIPCION_RE = re.compile(rf"^[{_LETRA}0-9 .,;:\-/#()$%¿?¡!'\"]+$")
NOMBRE_PERSONA_RE = re.compile(rf"^[{_LETRA}]+\.?(?:[ '\-][{_LETRA}]+\.?)*$")


def _palabra_sin_forma(palabra: str) -> bool:
    letras = re.sub(rf"[^{_LETRA}]", "", palabra)
    if len(letras) >= 4 and not any(c in _VOCALES for c in letras):
        return True
    return bool(_CONSONANTES_SEGUIDAS.search(letras))


def _espacios(texto: str) -> str:
    return re.sub(r"\s+", " ", texto or "").strip()


def validar_descripcion(texto: str, campo: str, max_len: int = 300,
                        requerido: bool = False) -> str:
    """Texto corto que describe algo: el concepto de un gasto, el motivo de
    una visita sin pago, una observacion. Devuelve "" si viene vacio y no es
    obligatorio."""
    t = _espacios(texto)[:max_len]
    if not t:
        if requerido:
            raise HTTPException(400, f"Escribe {campo.lower()}")
        return ""
    if not DESCRIPCION_RE.match(t):
        raise HTTPException(
            400, f"{campo}: usa solo letras, numeros y los signos . , - / # ( )")
    letras = len(re.findall(rf"[{_LETRA}]", t))
    signos = len(re.findall(rf"[^{_LETRA}0-9 ]", t))
    if letras < 3:
        raise HTTPException(400, f"{campo}: escribelo con palabras (ej. almuerzo, gasolina)")
    if signos > max(3, letras // 2):
        raise HTTPException(400, f"{campo}: tiene demasiados signos")
    if re.search(r"([^\d])\1{3,}", t):
        raise HTTPException(400, f"{campo}: no repitas el mismo caracter")
    pegado = re.search(rf"[{_LETRA}]{{4,}}\d+", t)
    if pegado:
        raise HTTPException(
            400, f"{campo}: separa el numero de la palabra en '{pegado.group(0)}'")
    for palabra in t.split():
        if _palabra_sin_forma(palabra):
            raise HTTPException(400, f"{campo}: '{palabra}' no parece una palabra")
    return t[0].upper() + t[1:]


def validar_nombre_persona(nombre: str) -> str:
    """Nombre de un cliente: nombre y apellido, solo letras.

    Mas estricto que validar_nombre (que sirve tambien para zonas y usuarios)
    porque un cliente es alguien a quien hay que encontrar y cobrar: con un
    nombre solo, o con uno inventado, no se le encuentra.
    """
    n = _espacios(nombre)[:120]
    if not n:
        raise HTTPException(400, "Escribe el nombre del cliente")
    if not NOMBRE_PERSONA_RE.match(n):
        raise HTTPException(400, "El nombre solo puede tener letras y espacios")
    palabras = [p for p in re.split(r"[ \-]", n) if len(p.strip(".'")) >= 2]
    if len(palabras) < 2:
        raise HTTPException(400, "Escribe nombre y apellido (ej. Juan Perez)")
    for p in palabras:
        if _palabra_sin_forma(p):
            raise HTTPException(400, f"'{p}' no parece un nombre. Revisalo.")
    return n


def validar_cedula_persona(cedula: str) -> str:
    """Documento de un cliente: el formato de validar_cedula y ademas al
    menos 5 numeros. Una cedula, un PPT o un pasaporte los tienen; una
    palabra escrita en ese campo, no."""
    c = validar_cedula(re.sub(r"[\s.]", "", cedula or ""))
    if len(re.findall(r"\d", c)) < 5:
        raise HTTPException(400, "La cedula debe tener al menos 5 numeros")
    return c


def validar_username(username: str) -> str:
    """Username: minusculas, digitos, punto/guion/guion bajo. Sin espacios ni
    simbolos raros -- es un identificador de login, no texto libre."""
    u = limpiar_texto(username, 100).lower()
    if not USERNAME_RE.match(u):
        raise HTTPException(400, "Username invalido: usa minusculas, numeros, '.', '_' o '-' (3-100 caracteres)")
    return u


def _solo_digitos(valor: str) -> str:
    return re.sub(r"\D", "", valor or "")


def validar_telefono(tel: str, requerido: bool = True) -> Optional[str]:
    """Telefono de contacto: fijo (7 digitos) o con indicativo/celular (10).

    No se exige que empiece por 3: los fijos de Medellin tambien son de 10
    digitos (604...) desde el cambio de numeracion. Esa exigencia solo aplica
    a WhatsApp, que unicamente funciona sobre celulares.
    """
    t = _solo_digitos(limpiar_texto(tel, 25))
    if not t:
        if requerido:
            raise HTTPException(400, "Teléfono requerido")
        return None
    if len(t) not in (7, 10):
        raise HTTPException(400, "El teléfono debe tener 7 dígitos (fijo) o 10 (celular)")
    return t


def validar_whatsapp(numero: str, requerido: bool = False) -> Optional[str]:
    """WhatsApp: exactamente 10 digitos empezando por 3 (celular colombiano).

    Un numero incompleto no falla al guardarlo sino despues, en silencio, al
    intentar enviar el recordatorio -- por eso se rechaza aqui y no alla.
    """
    n = _solo_digitos(limpiar_texto(numero, 25))
    if not n:
        if requerido:
            raise HTTPException(400, "WhatsApp requerido")
        return None
    if len(n) != 10 or not n.startswith("3"):
        raise HTTPException(400, "El WhatsApp debe tener exactamente 10 dígitos y empezar por 3")
    return n


WP_INSTANCE_RE = re.compile(r"^[0-9]{5,20}$")
WP_TOKEN_RE = re.compile(r"^[A-Za-z0-9]{10,100}$")


def validar_wp_instance(valor: str) -> Optional[str]:
    """ID de instancia de Green API: solo digitos."""
    v = limpiar_texto(valor, 30)
    if not v:
        return None
    if not WP_INSTANCE_RE.match(v):
        raise HTTPException(400, "ID de instancia invalido: solo digitos (5-20)")
    return v


def validar_wp_token(valor: str) -> Optional[str]:
    """Token de instancia de Green API: alfanumerico."""
    v = limpiar_texto(valor, 120)
    if not v:
        return None
    if not WP_TOKEN_RE.match(v):
        raise HTTPException(400, "Token de instancia invalido: solo letras y numeros (10-100 caracteres)")
    return v


METODOS_PAGO_VALIDOS = ("Efectivo", "Nequi", "Daviplata", "Transferencia")


def validar_metodo_pago(metodo: str) -> str:
    """Metodo de pago: lista blanca fija (botones/select del frontend), no texto libre."""
    m = limpiar_texto(metodo, 50) or "Efectivo"
    if m not in METODOS_PAGO_VALIDOS:
        raise HTTPException(400, f"Metodo de pago invalido. Usa: {', '.join(METODOS_PAGO_VALIDOS)}")
    return m


def validar_numero_positivo(valor, nombre: str = "valor", minimo: float = 0.01, maximo: float = 100_000_000) -> float:
    """Valida que un valor numérico esté dentro de un rango.

    Usa una comparación encadenada (no `v < min or v > max`): con NaN esa
    forma se evalua False en ambos lados y el valor pasa sin error.
    """
    try:
        v = float(valor)
    except (TypeError, ValueError):
        raise HTTPException(400, f"{nombre} debe ser un número válido")
    if not (minimo <= v <= maximo):
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


LADO_MAXIMO_IMAGEN = 1280


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
            # Un movil actual entrega 12 megapixeles. Para la foto de un
            # cliente o la evidencia de un cobro sobra de largo, y guardar
            # varios megas por imagen encarece cada copia de seguridad y cada
            # carga del perfil. Se reduce el lado mayor a 1280 px, que sigue
            # siendo nitido en pantalla y en una impresion pequena.
            if max(img.size) > LADO_MAXIMO_IMAGEN:
                img.thumbnail((LADO_MAXIMO_IMAGEN, LADO_MAXIMO_IMAGEN), Image.LANCZOS)
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


def filtro_busqueda(texto: str, *columnas):
    """Condicion SQL para buscar una persona por nombre o cedula.

    Busca por PALABRAS, no por la cadena literal. Escribir "JOHAN RO" tenia
    que encontrar a "JOHAN ROJAS", pero con un unico ILIKE '%JOHAN RO%' no lo
    encontraba si el nombre guardado trae dos espacios ("JOHAN  ROJAS"), que
    es el caso de casi un tercio de los clientes importados. Tampoco
    encontraba nada si el usuario escribia los apellidos primero.

    Cada palabra tiene que aparecer en alguna de las columnas, en cualquier
    orden y en cualquier posicion. Devuelve None si no hay nada que buscar.
    """
    from sqlalchemy import and_, or_

    palabras = (texto or "").split()
    if not palabras or not columnas:
        return None
    condiciones = [
        or_(*[col.ilike(f"%{palabra}%") for col in columnas])
        for palabra in palabras
    ]
    return and_(*condiciones)
