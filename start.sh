#!/bin/sh
PORT=${PORT:-8000}

# --proxy-headers hace que uvicorn confie en X-Forwarded-For/-Proto y
# reescriba request.client con la IP real del visitante en vez de la del
# proxy de Railway. --forwarded-allow-ips='*' es seguro aqui porque en
# Railway nada llega a este puerto salvo su propio proxy de borde -- sin
# esto, TODO el rate limiting por IP (login, activacion, recuperacion de
# clave) ve la misma IP para todos los usuarios y no aisla nada.
# Numero de procesos. Se puede subir con WEB_CONCURRENCY sin tocar codigo.
# Antes estaba fijo en 1 porque el rate limit y la lista de sesiones
# revocadas vivian en memoria de cada proceso: con varios workers el limite
# de intentos se multiplicaba y un logout no se propagaba a los demas. Las
# dos cosas estan ahora en la base de datos (tablas rate_limit_ventanas y
# sesiones_jwt), asi que varios workers se comportan igual que uno.
#
# Ojo al subirlo: el consumo maximo de conexiones es
# workers x 2 motores x (DB_POOL_SIZE + DB_MAX_OVERFLOW), y el servidor de
# base de datos admite 60 en total.
WORKERS=${WEB_CONCURRENCY:-2}

exec uvicorn app.main:app --host 0.0.0.0 --port "$PORT" --workers "$WORKERS" --proxy-headers --forwarded-allow-ips='*'
