#!/bin/sh
PORT=${PORT:-8000}

# --proxy-headers hace que uvicorn confie en X-Forwarded-For/-Proto y
# reescriba request.client con la IP real del visitante en vez de la del
# proxy de Railway. --forwarded-allow-ips='*' es seguro aqui porque en
# Railway nada llega a este puerto salvo su propio proxy de borde -- sin
# esto, TODO el rate limiting por IP (login, activacion, recuperacion de
# clave) ve la misma IP para todos los usuarios y no aisla nada.
exec uvicorn app.main:app --host 0.0.0.0 --port "$PORT" --workers 1 --proxy-headers --forwarded-allow-ips='*'
