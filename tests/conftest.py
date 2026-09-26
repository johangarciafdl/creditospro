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


def sustituir_sesion(app, fabrica):
    """Inyecta una sesion de base de datos en TODAS las rutas de la app.

    No basta con `app.dependency_overrides[get_db] = ...` usando el `get_db`
    que importa la prueba. Cada router importo su dependencia al cargarse, y
    `tests/test_integration.py` recarga `app.database`, con lo que
    `app.database.get_db` pasa a ser un objeto nuevo mientras los routers
    siguen con el viejo. Las claves de dependency_overrides se comparan por
    identidad, asi que la sustitucion no se aplicaba y la prueba terminaba
    hablando con la base de otro modulo -- con el sintoma desconcertante de
    "Clave de activacion invalida" para una clave recien creada.

    Aqui se recorren las rutas montadas y se sustituye cada callable que se
    llame get_db o get_db_system, sea el objeto que sea.

    Devuelve las claves sustituidas para poder deshacerlo al terminar.
    """
    from fastapi.routing import APIRoute

    def _rutas(rutas):
        for r in rutas:
            if isinstance(r, APIRoute):
                yield r
            elif type(r).__name__ == "_IncludedRouter":
                yield from _rutas(r.original_router.routes)

    claves = set()
    for ruta in _rutas(app.routes):
        for dep in ruta.dependant.dependencies:
            fn = dep.call
            if getattr(fn, "__name__", "") in ("get_db", "get_db_system"):
                claves.add(fn)
    for fn in claves:
        app.dependency_overrides[fn] = fabrica
    return claves
