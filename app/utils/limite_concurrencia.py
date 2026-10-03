"""Cuantas peticiones atiende a la vez cada proceso.

Las pantallas hacen sus consultas a la base de forma sincrona dentro del
bucle de eventos. Cuando todas las conexiones del pool estan ocupadas, la
siguiente peticion se queda esperando una conexion (hasta pool_timeout, 30 s)
CON EL BUCLE BLOQUEADO: las peticiones que tienen las conexiones no pueden
terminar para soltarlas. Resultado medido en produccion: un celular que abre
la app lanza ~13 peticiones juntas (el service worker guarda 8 pantallas y la
sincronizacion pide los datos), 5 salen al instante y las otras 8 tardan
65 segundos, dos de ellas con error 500. Con varios cobradores a la vez, la
app se congela para todos.

Aqui se limita la entrada: como mucho LIMITE peticiones a la vez por proceso,
menos que las conexiones del pool. Las demas esperan su turno con `await`,
sin bloquear el bucle, y entran en cuanto una termina.
"""
from __future__ import annotations

import asyncio
import os

from app.database import MAX_OVERFLOW, POOL_SIZE

# Una conexion de margen: algunas peticiones abren ademas una sesion corta
# (lista de sesiones revocadas, auditoria) con el mismo pool.
LIMITE = max(1, int(os.getenv("MAX_PETICIONES_A_LA_VEZ", str(POOL_SIZE + MAX_OVERFLOW - 1))))

# No tocan la base: no hace falta que hagan fila.
_SIN_FILA = ("/static/", "/sw.js", "/favicon.ico", "/health")


class LimiteConcurrenciaMiddleware:
    def __init__(self, app, limite: int = LIMITE):
        self.app = app
        self.limite = limite
        self._sem: asyncio.Semaphore | None = None

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope.get("path", "").startswith(_SIN_FILA):
            await self.app(scope, receive, send)
            return
        if self._sem is None:                    # se crea dentro del bucle que la usa
            self._sem = asyncio.Semaphore(self.limite)
        async with self._sem:
            await self.app(scope, receive, send)
