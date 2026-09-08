import os

# Asignacion directa (no setdefault) y ANTES que cualquier otra cosa: al
# quedar ya presente en os.environ, load_dotenv(override=False) -- que
# app/main.py ejecuta sin condicion al importarse -- no la reemplaza con el
# valor real de produccion del .env del desarrollador. Sin esto, los tests
# de integracion que import an app.main despues de este conftest terminarian
# conectando el rol restringido de RLS (DATABASE_URL_APP) a la base real.
os.environ["DATABASE_URL_APP"] = ""

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("SECRET_KEY", "test-secret-key-for-pytest")
os.environ.setdefault("SESSION_SECRET_KEY", "test-session-secret-key-for-pytest")
os.environ.setdefault("ENVIRONMENT", "development")
os.environ.setdefault("AUTO_CREATE_TABLES", "0")
