"""Metricas de peticiones del proceso, para el panel de monitoreo.

Que mide y que no: estos contadores viven en la memoria del proceso que
atiende la peticion. Con varios workers, cada uno tiene los suyos, asi que
lo que se muestra es el comportamiento de UN proceso, no la suma de todos
-- el panel lo dice explicitamente. Para las cifras que tienen que ser
exactas y sobrevivir a un reinicio (cobros, auditoria, sesiones) el panel
consulta la base de datos, no esto.

Se prefiere asi antes que escribir una fila por peticion: el objetivo es
ver si la aplicacion va lenta o esta devolviendo errores, y para eso no
hace falta pagar una escritura en cada peticion.

La latencia se guarda en una ventana de las ultimas `_MAX_MUESTRAS`
peticiones por ruta. Guardar solo el promedio esconde justo lo que
interesa: si unas pocas peticiones tardan cinco segundos, el promedio
apenas se mueve pero el usuario si lo nota. Por eso se guardan tres
cifras: la mediana (lo normal), el percentil 95 (lo que sufre una minoria
apreciable) y el peor tiempo. El p95 solo delata un caso lento cuando pasa
del 5% de las peticiones; por debajo de eso, el unico que lo enseña es el
maximo, y por eso tambien se muestra.
"""
from __future__ import annotations

import time
from collections import defaultdict, deque
from threading import Lock

from starlette.middleware.base import BaseHTTPMiddleware

# Peticiones por ruta de las que se conserva la latencia.
_MAX_MUESTRAS = 200
# A partir de aqui una peticion se considera lenta y se cuenta aparte.
UMBRAL_LENTA_MS = 1500

_inicio = time.time()
_lock = Lock()
_peticiones: dict[str, int] = defaultdict(int)
_errores_cliente: dict[str, int] = defaultdict(int)   # 4xx
_errores_servidor: dict[str, int] = defaultdict(int)  # 5xx
_lentas: dict[str, int] = defaultdict(int)
_latencias: dict[str, deque] = defaultdict(lambda: deque(maxlen=_MAX_MUESTRAS))
_ultimos_errores: deque = deque(maxlen=25)


def _plantilla_de_ruta(request) -> str:
    """Agrupa /clientes/123/editar bajo /clientes/{id}/editar.

    Sin esto cada id crearia su propia entrada y la tabla de metricas
    creceria sin limite ademas de volverse ilegible.
    """
    ruta = request.scope.get("route")
    plantilla = getattr(ruta, "path", None)
    if plantilla:
        prefijo = request.scope.get("root_path", "")
        return f"{prefijo}{plantilla}" if prefijo else plantilla
    return request.url.path


def registrar(ruta: str, metodo: str, estado: int, ms: float, request_id: str = "") -> None:
    clave = f"{metodo} {ruta}"
    with _lock:
        _peticiones[clave] += 1
        _latencias[clave].append(ms)
        if ms >= UMBRAL_LENTA_MS:
            _lentas[clave] += 1
        if 400 <= estado < 500:
            _errores_cliente[clave] += 1
        elif estado >= 500:
            _errores_servidor[clave] += 1
            _ultimos_errores.append({
                "ruta": clave,
                "estado": estado,
                "ms": round(ms),
                "cuando": time.time(),
                "request_id": request_id or "-",
            })


def _percentil(valores: list[float], p: float) -> float:
    if not valores:
        return 0.0
    orden = sorted(valores)
    i = min(int(round(p * (len(orden) - 1))), len(orden) - 1)
    return orden[i]


def resumen(top: int = 12) -> dict:
    """Fotografia de las metricas de ESTE proceso."""
    with _lock:
        claves = list(_peticiones.keys())
        rutas = []
        for clave in claves:
            muestras = list(_latencias[clave])
            rutas.append({
                "ruta": clave,
                "peticiones": _peticiones[clave],
                "mediana_ms": round(_percentil(muestras, 0.50)),
                "p95_ms": round(_percentil(muestras, 0.95)),
                "peor_ms": round(max(muestras)) if muestras else 0,
                "lentas": _lentas[clave],
                "errores_cliente": _errores_cliente[clave],
                "errores_servidor": _errores_servidor[clave],
            })
        totales = {
            "peticiones": sum(_peticiones.values()),
            "errores_cliente": sum(_errores_cliente.values()),
            "errores_servidor": sum(_errores_servidor.values()),
            "lentas": sum(_lentas.values()),
        }
        ultimos = list(_ultimos_errores)

    # Se ordena por las que mas tiempo consumen en total (peticiones x p95):
    # una ruta lenta que se llama poco importa menos que una media lenta que
    # se llama todo el rato.
    rutas.sort(key=lambda r: r["peticiones"] * max(r["p95_ms"], 1), reverse=True)
    return {
        "activo_desde": _inicio,
        "segundos_en_marcha": round(time.time() - _inicio),
        "totales": totales,
        "rutas": rutas[:top],
        "ultimos_errores": list(reversed(ultimos)),
        "umbral_lenta_ms": UMBRAL_LENTA_MS,
    }


class MetricasMiddleware(BaseHTTPMiddleware):
    """Mide cada peticion. Va por dentro para medir solo el trabajo real."""

    async def dispatch(self, request, call_next):
        arranque = time.perf_counter()
        estado = 500
        try:
            respuesta = await call_next(request)
            estado = respuesta.status_code
            return respuesta
        finally:
            ms = (time.perf_counter() - arranque) * 1000
            # Los estaticos no dicen nada del rendimiento de la aplicacion y
            # solo ensucian la tabla.
            if not request.url.path.startswith("/static"):
                registrar(
                    _plantilla_de_ruta(request),
                    request.method,
                    estado,
                    ms,
                    getattr(request.state, "request_id", ""),
                )
