"""Rate limit en memoria. Adecuado para 1 worker. Para multi-worker usar Redis."""
import logging
import time
from collections import defaultdict, deque
from threading import Lock

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

logger = logging.getLogger(__name__)

# Reglas por defecto: ruta -> (max_requests, ventana_segundos)
# Se aplican solo a metodos POST/PUT/PATCH/DELETE.
DEFAULT_RULES = {
    "/auth/login": (10, 60),
    "/registro": (5, 300),
    "/registro/": (5, 300),
    "/auth/usuarios/nuevo": (10, 300),
    "/license/activate": (3, 60),
    "/cobros/registrar": (60, 60),
    "/whatsapp/enviar-ahora": (5, 300),
    "/whatsapp/enviar-manual": (30, 60),
}

UNSAFE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


def _client_ip(request) -> str:
    # Solo confiar en headers de proxy cuando el despliegue los sanea.
    # Por defecto el socket evita que el cliente elija su propia identidad.
    return request.client.host if request.client else "unknown"


class InMemoryRateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, rules=None):
        super().__init__(app)
        self.rules = rules or DEFAULT_RULES
        self.requests = defaultdict(deque)
        self.lock = Lock()

    def _check(self, path: str, client: str, limit: int, window: int) -> bool:
        """Devuelve True si la peticion pasa el rate limit, False si esta bloqueada."""
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
        rule = self.rules.get(request.url.path)
        if request.method in UNSAFE_METHODS and rule:
            limit, window = rule
            client = _client_ip(request)
            if not self._check(request.url.path, client, limit, window):
                logger.warning(
                    "Rate limit alcanzado: path=%s ip=%s (%s/%ss)",
                    request.url.path, client, limit, window,
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
