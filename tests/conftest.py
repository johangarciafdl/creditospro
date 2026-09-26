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


import pytest as _pytest


def vaciar_limitador():
    """Vacia los cubos del limitador en memoria, ahora mismo.

    La fixture autouse de abajo lo hace entre pruebas, que es suficiente para
    casi todo. No lo es cuando una fixture de modulo activa licencia e inicia
    sesion varias veces en un mismo setup: esas peticiones van seguidas, sin
    ninguna prueba en medio, y la cuarta activacion se lleva un 429 que no
    tiene nada que ver con lo que la prueba comprueba. Esas fixtures llaman a
    esto entre sesion y sesion.
    """
    from app.main import app
    from app.utils.rate_limit import InMemoryRateLimitMiddleware

    pila = getattr(app, "middleware_stack", None)
    while pila is not None:
        if isinstance(pila, InMemoryRateLimitMiddleware):
            pila.requests.clear()
            return True
        pila = getattr(pila, "app", None)
    return False


@_pytest.fixture(autouse=True)
def _limitador_limpio_entre_pruebas():
    """Vacia los contadores del rate limit antes de cada prueba.

    InMemoryRateLimitMiddleware guarda sus cubos en el objeto de la
    aplicacion, que vive una sola vez por proceso: los intentos se suman a
    lo largo de TODA la suite. Cada modulo que activa licencia e inicia
    sesion gasta cupo del siguiente, asi que anadir pruebas hacia fallar a
    las de mas abajo con un 429 -- un fallo que no tiene nada que ver con
    lo que esas pruebas comprueban y que aparece o no segun el orden.

    Es tambien la causa de que test_login_credenciales_invalidas_no_enumera
    _usuarios fallara de vez en cuando: pasaba sola y fallaba en la suite
    completa, que es la firma de un estado compartido entre pruebas.

    Ninguna prueba comprueba el rate limit en si, asi que vaciarlo no tapa
    nada. El limitador compartido por base de datos no se toca: ese vive en
    la base de cada modulo y se va con ella.
    """
    from app.main import app
    from app.utils.rate_limit import InMemoryRateLimitMiddleware

    def _cubos():
        # El middleware instanciado vive en la pila ya construida; antes de
        # la primera peticion solo existe la definicion en user_middleware.
        pila = getattr(app, "middleware_stack", None)
        while pila is not None:
            if isinstance(pila, InMemoryRateLimitMiddleware):
                return pila.requests
            pila = getattr(pila, "app", None)
        return None

    cubos = _cubos()
    if cubos is not None:
        cubos.clear()
    yield
    cubos = _cubos()
    if cubos is not None:
        cubos.clear()
