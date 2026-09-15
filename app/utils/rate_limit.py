"""Rate limit por IP, compartido entre todos los procesos.

Las ventanas se guardan en la tabla `rate_limit_ventanas` con un UPSERT
atomico. Con el contador en memoria de cada proceso, N workers permitian N
veces el limite configurado -- 10 intentos de login por minuto se volvian
40 con cuatro workers, que es justo lo contrario de lo que el limite
pretende. En la base de datos la ventana es una sola fila por (regla,
cliente), asi que el limite no depende de cuantos procesos haya.

Solo se consulta en metodos que escriben (POST/PUT/PATCH/DELETE), asi que
no añade ninguna consulta a la navegacion normal. Si la base de datos no
responde se vuelve al contador en memoria: es preferible un limite por
proceso a quedarse sin limite.
"""
import logging
import re
import time
from collections import defaultdict, deque
from threading import Lock

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

logger = logging.getLogger(__name__)

# Reglas por defecto: ruta exacta -> (max_requests, ventana_segundos)
# Se aplican solo a metodos POST/PUT/PATCH/DELETE.
DEFAULT_RULES = {
    "/auth/login": (10, 60),
    "/registro": (5, 300),
    "/registro/": (5, 300),
    "/auth/usuarios/nuevo": (10, 300),
    "/auth/cambiar-password": (10, 300),
    "/license/activate": (3, 60),
    "/cobros/registrar": (60, 60),
    "/whatsapp/enviar-ahora": (5, 300),
    "/whatsapp/enviar-manual": (30, 60),
    "/csp-report": (100, 60),
}

# Reglas para rutas con parametro (ej. /zonas/{id}/editar) -- el dict de
# arriba solo hace match exacto y nunca las cubre. patron -> (max, ventana).
# El patron completo (no la URL con el id real) se usa como key del bucket,
# para que /zonas/1/editar y /zonas/2/editar compartan el mismo limite.
PARAM_RULES = [
    (re.compile(r"^/zonas/\d+/editar$"), 20, 60),
    (re.compile(r"^/cobros/registrar-cliente/\d+$"), 60, 60),
    (re.compile(r"^/clientes/\d+/editar$"), 20, 60),
    (re.compile(r"^/auth/usuarios/\d+/editar$"), 10, 300),
    (re.compile(r"^/auth/usuarios/\d+$"), 10, 300),
    (re.compile(r"^/auth/sesiones/[^/]+/revocar$"), 10, 300),
]

UNSAFE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


def _client_ip(request) -> str:
    # Solo confiar en headers de proxy cuando el despliegue los sanea.
    # Por defecto el socket evita que el cliente elija su propia identidad.
    return request.client.host if request.client else "unknown"


_bd_disponible = True


def _sin_bd(exc: Exception) -> None:
    global _bd_disponible
    if _bd_disponible:
        logger.warning(
            "Rate limit sin base de datos (%s); cada proceso cuenta por su cuenta", exc
        )
    _bd_disponible = False


def _check_compartido(clave: str, limit: int, window: int):
    """Cuenta la peticion en la ventana compartida.

    Devuelve True si pasa, False si esta bloqueada, y None si la base de
    datos no esta disponible (entonces el llamador usa el contador local).

    El UPSERT hace todo en una sola sentencia atomica: si la ventana
    guardada ya caduco la reinicia, y si no, incrementa. Hacerlo en dos
    pasos (leer y despues escribir) dejaria una carrera por la que dos
    procesos podrian pasar ambos el ultimo intento permitido.
    """
    if not _bd_disponible:
        return None
    try:
        from sqlalchemy import text as _text

        from app.database import SessionLocal

        ahora = int(time.time())
        db = SessionLocal()
        try:
            fila = db.execute(
                _text(
                    """
                    INSERT INTO rate_limit_ventanas (clave, ventana_inicio, conteo, actualizado_en)
                    VALUES (:clave, :ahora, 1, :ahora)
                    ON CONFLICT (clave) DO UPDATE SET
                      ventana_inicio = CASE
                        WHEN rate_limit_ventanas.ventana_inicio <= :corte THEN :ahora
                        ELSE rate_limit_ventanas.ventana_inicio END,
                      conteo = CASE
                        WHEN rate_limit_ventanas.ventana_inicio <= :corte THEN 1
                        ELSE rate_limit_ventanas.conteo + 1 END,
                      actualizado_en = :ahora
                    RETURNING conteo
                    """
                ),
                {"clave": clave[:200], "ahora": ahora, "corte": ahora - window},
            ).first()
            db.commit()
            return bool(fila) and fila[0] <= limit
        finally:
            db.close()
    except Exception as exc:
        _sin_bd(exc)
        return None


def limpiar_ventanas_viejas(db, antiguedad_segundos: int = 3600) -> int:
    """Borra ventanas que ya no puede consultar nadie. La llama el scheduler."""
    from sqlalchemy import text as _text

    corte = int(time.time()) - antiguedad_segundos
    r = db.execute(
        _text("DELETE FROM rate_limit_ventanas WHERE actualizado_en < :corte"),
        {"corte": corte},
    )
    db.commit()
    return r.rowcount or 0


def estado() -> dict:
    """Resumen para el panel de monitoreo."""
    return {"compartido": _bd_disponible}


class InMemoryRateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, rules=None):
        super().__init__(app)
        self.rules = rules or DEFAULT_RULES
        self.requests = defaultdict(deque)
        self.lock = Lock()

    def _check(self, path: str, client: str, limit: int, window: int) -> bool:
        """Devuelve True si la peticion pasa el rate limit, False si esta bloqueada."""
        compartido = _check_compartido(f"{path}|{client}", limit, window)
        if compartido is not None:
            return compartido
        key = (path, client)
        now = time.monotonic()
        with self.lock:
            bucket = self.requests[key]
            while bucket and now - bucket[0] > window:
                bucket.popleft()
            if len(bucket) >= limit:
                return False
            bucket.append(now)
            return True

    async def dispatch(self, request, call_next):
        if request.method in UNSAFE_METHODS:
            path = request.url.path
            bucket_key = path
            rule = self.rules.get(path)
            if rule is None:
                for pattern, limit, window in PARAM_RULES:
                    if pattern.match(path):
                        rule = (limit, window)
                        bucket_key = pattern.pattern  # patron, no la url real, para compartir el balde
                        break
            if rule:
                limit, window = rule
                client = _client_ip(request)
                if not self._check(bucket_key, client, limit, window):
                    logger.warning(
                        "Rate limit alcanzado: path=%s ip=%s (%s/%ss)",
                        path, client, limit, window,
                    )
                    return JSONResponse(
                        {"error": "Demasiados intentos. Intenta mas tarde."},
                        status_code=429,
                        headers={"Retry-After": str(window)},
                    )
        return await call_next(request)


# ── API publica para uso desde endpoints individuales ─────────────────────────
# (para casos donde el rate limit depende del body o de un usuario
# autenticado, no solo de la IP)

_middleware_instance: InMemoryRateLimitMiddleware | None = None


def init_middleware(app):
    """Inicializa el singleton. Llamar una sola vez al arrancar la app."""
    global _middleware_instance
    if _middleware_instance is None:
        _middleware_instance = InMemoryRateLimitMiddleware(app)
    return _middleware_instance


def is_rate_limited(request, path: str, limit: int, window: int, key_suffix: str = "") -> bool:
    """Comprueba rate limit por path+ip(+suffix). Devuelve True si BLOQUEADO.

    Usage en un endpoint:
        if is_rate_limited(request, '/auth/recovery', 5, 3600):
            return JSONResponse({'error': '...'}, status_code=429)
    """
    if _middleware_instance is None:
        # Sin inicializar (p.ej. en tests sin app), usar estado local
        global _fallback
        try:
            _fallback
        except NameError:
            from collections import defaultdict, deque
            global _fb_state
            _fb_state = defaultdict(deque)
            from threading import Lock as _L
            global _fb_lock
            _fb_lock = _L()
        client = _client_ip(request)
        key = (path, client + key_suffix)
        now = time.monotonic()
        with _fb_lock:
            bucket = _fb_state[key]
            while bucket and now - bucket[0] > window:
                bucket.popleft()
            if len(bucket) >= limit:
                return True
            bucket.append(now)
            return False
    return not _middleware_instance._check(path, _client_ip(request) + key_suffix, limit, window)
