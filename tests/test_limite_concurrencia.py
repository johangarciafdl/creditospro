"""El limite de peticiones a la vez por proceso (app/utils/limite_concurrencia).

En produccion, 13 peticiones juntas de un solo celular congelaban la app 65
segundos: con el pool lleno, la peticion que esperaba conexion bloqueaba el
bucle y las que tenian conexion no podian terminar. Con el limite, las que
sobran esperan su turno sin bloquear y todas terminan."""
import asyncio

from app.utils.limite_concurrencia import LimiteConcurrenciaMiddleware


def _app_que_cuenta():
    estado = {"ahora": 0, "maximo": 0, "atendidas": 0}

    async def app(scope, receive, send):
        estado["ahora"] += 1
        estado["maximo"] = max(estado["maximo"], estado["ahora"])
        await asyncio.sleep(0.02)
        estado["ahora"] -= 1
        estado["atendidas"] += 1

    return app, estado


async def _peticiones(mw, rutas):
    async def una(ruta):
        await mw({"type": "http", "path": ruta}, None, None)
    await asyncio.wait_for(asyncio.gather(*(una(r) for r in rutas)), timeout=5)


def test_no_entran_mas_de_las_que_caben_y_todas_terminan():
    app, estado = _app_que_cuenta()
    mw = LimiteConcurrenciaMiddleware(app, limite=3)
    asyncio.run(_peticiones(mw, ["/clientes"] * 13))
    assert estado["atendidas"] == 13
    assert estado["maximo"] == 3


def test_los_estaticos_no_hacen_fila():
    app, estado = _app_que_cuenta()
    mw = LimiteConcurrenciaMiddleware(app, limite=1)
    asyncio.run(_peticiones(mw, ["/static/css/app.css"] * 6 + ["/health"] * 2))
    assert estado["atendidas"] == 8 and estado["maximo"] == 8


def test_esta_puesto_y_es_el_de_afuera():
    from app.main import app
    assert app.user_middleware[0].cls is LimiteConcurrenciaMiddleware


def test_el_limite_deja_margen_en_el_pool():
    from app.database import MAX_OVERFLOW, POOL_SIZE
    from app.utils.limite_concurrencia import LIMITE
    assert 1 <= LIMITE < POOL_SIZE + MAX_OVERFLOW
