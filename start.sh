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

# Aplicar las migraciones pendientes antes de aceptar trafico.
#
# Sin esto habia que acordarse de ejecutarlas a mano despues de cada
# despliegue: un cambio de esquema subido pero no aplicado deja la
# aplicacion consultando columnas que no existen, y el fallo aparece en la
# primera peticion de un usuario, no en el despliegue. Se ejecuta una vez
# por arranque del contenedor, antes de que uvicorn cree sus procesos.
#
# Si falla, el arranque se detiene a proposito: Railway conserva el
# despliegue anterior, que es preferible a servir con un esquema a medias.
# Se puede saltar con SKIP_MIGRATIONS=1 para un arranque de emergencia.
#
# Se reintenta porque la causa mas probable de que falle no es una migracion
# mala, sino que la base aun no acepta conexiones en el instante del
# arranque. Sin reintento, un tropiezo de dos segundos deja el contenedor
# sin arrancar y el sitio caido hasta que alguien lo note.
if [ "${SKIP_MIGRATIONS:-0}" != "1" ]; then
  INTENTOS=${MIGRATION_RETRIES:-3}
  n=1
  while : ; do
    echo "[start] Aplicando migraciones pendientes (intento $n de $INTENTOS)..."
    if alembic upgrade head; then
      echo "[start] Migraciones al dia."
      break
    fi
    if [ "$n" -ge "$INTENTOS" ]; then
      echo "[start] ERROR: fallaron las migraciones tras $INTENTOS intentos."
      echo "[start] No se arranca con un esquema a medias; Railway conserva el despliegue anterior."
      echo "[start] Para arrancar igualmente (y arreglarlo a mano): SKIP_MIGRATIONS=1"
      exit 1
    fi
    n=$((n + 1))
    echo "[start] Reintentando en 5 segundos..."
    sleep 5
  done
fi

exec uvicorn app.main:app --host 0.0.0.0 --port "$PORT" --workers "$WORKERS" --proxy-headers --forwarded-allow-ips='*'
