# Imagen base oficial con versiones pinneadas
FROM python:3.13-slim-bookworm AS base

# No escribir .pyc, no buffer stdout (importante para logs en tiempo real)
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Crear usuario no-root para correr la app (defensa contra escalacion)
RUN groupadd -r credit && useradd -r -g credit -d /app -s /sbin/nologin credit

WORKDIR /app

# Dependencias del sistema minimas (Pillow compila nativamente)
RUN apt-get update && apt-get install -y --no-install-recommends \
        libpq5 \
        libjpeg62-turbo \
        zlib1g \
        libwebp7 \
    && rm -rf /var/lib/apt/lists/*

# Instalar dependencias Python primero (mejor caching de capas)
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Copiar el codigo
COPY . /app

# Ajustes finales: uploads, reports, backups
RUN mkdir -p /app/uploads/fotos /app/backups /app/reports \
    && chown -R credit:credit /app

USER credit

# Documentar puerto por defecto
EXPOSE 8000

# Healthcheck: el endpoint /health responde 200 si DB esta OK
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request, sys, os; \
        port = os.environ.get('PORT', '8000'); \
        r = urllib.request.urlopen(f'http://127.0.0.1:{port}/health', timeout=3); \
        sys.exit(0 if r.status == 200 else 1)" || exit 1

# Comando por defecto: uvicorn con 1 worker (la app usa in-memory state:
# rate limit, token blacklist, scheduler). Para multi-worker cambiar a
# redis y gunicorn -w N.
# Shell form para que $PORT se expanda (Railway, Heroku, etc.)
CMD uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1
