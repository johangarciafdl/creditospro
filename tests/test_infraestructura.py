"""Garantias de infraestructura: caches, escalabilidad y monitoreo.

Cada test protege una propiedad que ya se rompio una vez o que, si se
rompe, no da ningun sintoma visible hasta que es tarde.
"""
import re
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]


# ── Caching ───────────────────────────────────────────────────────────────

def test_los_estaticos_versionados_se_sirven_como_inmutables():
    """Sin cache larga el navegador revalida cada archivo en cada pagina."""
    main = (RAIZ / "app" / "main.py").read_text(encoding="utf-8")
    assert "max-age=31536000, immutable" in main
    assert 'app.mount(\n    "/static/dist"' in main or '"/static/dist"' in main


def test_base_html_no_vuelve_a_llevar_css_ni_js_incrustado():
    """Lo incrustado viaja en CADA pagina y no se puede cachear."""
    base = (RAIZ / "templates" / "base.html").read_text(encoding="utf-8")
    for bloque in re.findall(r"<style[^>]*>(.*?)</style>", base, re.S):
        assert len(bloque) < 500, (
            "volvio a aparecer CSS incrustado en base.html: son bytes que se "
            "reenvian en cada navegacion en vez de cachearse"
        )
    grandes = [
        b for b in re.findall(r"<script(?![^>]*src=)[^>]*>(.*?)</script>", base, re.S)
        if len(b) > 3000
    ]
    assert not grandes, (
        "volvio a aparecer un bloque grande de JavaScript incrustado en base.html"
    )


def test_las_plantillas_no_apuntan_a_los_estaticos_sin_versionar():
    """Una ruta fija se queda sin la cache larga y sin invalidacion."""
    base = (RAIZ / "templates" / "base.html").read_text(encoding="utf-8")
    assert "/static/js/" not in base, "usar {{ estatico('js/...') }} en vez de la ruta fija"
    assert "/static/css/" not in base, "usar {{ estatico('css/...') }} en vez de la ruta fija"


# ── Escalabilidad ─────────────────────────────────────────────────────────

def test_el_numero_de_procesos_es_configurable():
    inicio = (RAIZ / "start.sh").read_text(encoding="utf-8")
    assert "WEB_CONCURRENCY" in inicio
    assert "--workers 1" not in inicio, (
        "fijar 1 worker impide escalar; el limite real lo pone el pool de conexiones"
    )


def test_el_pool_no_puede_agotar_las_conexiones_del_servidor():
    """La app abre DOS motores por proceso; el servidor admite 60 conexiones.

    Con los valores historicos (5 + 10) un solo proceso llegaba a 30 y dos
    workers habrian agotado la base de datos.
    """
    from app.database import MAX_OVERFLOW, POOL_SIZE

    por_proceso = 2 * (POOL_SIZE + MAX_OVERFLOW)
    assert por_proceso * 4 <= 60, (
        f"cada proceso puede abrir {por_proceso} conexiones: cuatro workers "
        f"agotarian el limite de 60 del servidor"
    )


def test_las_sesiones_revocadas_se_guardan_fuera_del_proceso():
    """Si solo viven en memoria, un logout no se propaga a los demas workers
    y ademas se pierde en cada despliegue."""
    codigo = (RAIZ / "app" / "utils" / "token_blacklist.py").read_text(encoding="utf-8")
    assert "SesionJWT" in codigo
    assert "revocada" in codigo


def test_el_rate_limit_se_cuenta_fuera_del_proceso():
    """Con el contador en memoria, N workers permiten N veces el limite."""
    codigo = (RAIZ / "app" / "utils" / "rate_limit.py").read_text(encoding="utf-8")
    assert "rate_limit_ventanas" in codigo
    assert "ON CONFLICT" in codigo, (
        "la cuenta tiene que ser atomica: leer y despues escribir deja una "
        "carrera por la que dos procesos pasan el ultimo intento permitido"
    )


def test_los_estaticos_se_construyen_sin_borrar_la_carpeta():
    """Con varios workers, uno borrando mientras otro sirve deja peticiones
    sin archivo."""
    codigo = (RAIZ / "app" / "utils" / "estaticos.py").read_text(encoding="utf-8")
    assert "rmtree" not in codigo
    assert "os.replace" in codigo, "los archivos deben escribirse de forma atomica"


def test_los_estaticos_se_construyen_antes_de_montarlos():
    """StaticFiles exige que la carpeta exista al importar el modulo.

    Construirlos en el lifespan dejo la aplicacion caida con 502: el montaje
    se ejecuta antes que el lifespan.
    """
    main = (RAIZ / "app" / "main.py").read_text(encoding="utf-8")
    construccion = main.index("construir_estaticos(BASE_DIR)")
    montaje = main.index('app.mount(\n    "/static/dist"')
    assert construccion < montaje, (
        "los estaticos se construyen despues de montarse: la app no arrancara "
        "en un despliegue limpio"
    )


# ── Monitoreo ─────────────────────────────────────────────────────────────

def test_health_comprueba_la_base_de_datos_de_verdad():
    """Devolver siempre 'healthy' hace que un proceso sin base de datos se
    reporte sano y el proveedor le mande trafico igual."""
    main = (RAIZ / "app" / "main.py").read_text(encoding="utf-8")
    bloque = main.split("async def health_check")[1][:900]
    assert "salud()" in bloque
    assert "503" in bloque, "un proceso sin base de datos debe responder 503"

    estado = (RAIZ / "app" / "utils" / "estado_sistema.py").read_text(encoding="utf-8")
    assert "SELECT 1" in estado


def test_las_metricas_agrupan_las_rutas_con_parametros():
    """Sin agrupar, cada id crea su propia entrada y la tabla crece sin fin."""
    codigo = (RAIZ / "app" / "utils" / "metricas.py").read_text(encoding="utf-8")
    assert "_plantilla_de_ruta" in codigo
    assert 'request.scope.get("route")' in codigo


def test_las_metricas_reportan_percentiles_no_solo_el_promedio():
    from app.utils import metricas

    metricas.registrar("/prueba", "GET", 200, 10)
    for _ in range(18):
        metricas.registrar("/prueba", "GET", 200, 12)
    metricas.registrar("/prueba", "GET", 200, 5000)

    fila = next(r for r in metricas.resumen()["rutas"] if r["ruta"] == "GET /prueba")
    assert fila["mediana_ms"] < 100, "la mediana no debe arrastrar el caso lento"
    # Con 20 muestras y una sola lenta, esa muestra ES el 5% superior, asi
    # que por definicion queda por encima del p95 y este no la refleja. El
    # que siempre la enseña es el maximo.
    assert fila["peor_ms"] >= 5000, "el peor tiempo debe delatar la peticion lenta"
    assert fila["lentas"] == 1

    # Con dos lentas de veinte (10%), el p95 si tiene que moverse.
    metricas.registrar("/prueba", "GET", 200, 5000)
    fila = next(r for r in metricas.resumen()["rutas"] if r["ruta"] == "GET /prueba")
    assert fila["p95_ms"] >= 5000


def test_las_metricas_cuentan_los_fallos_del_servidor_con_su_identificador():
    from app.utils import metricas

    metricas.registrar("/falla", "POST", 500, 40, request_id="abc-123")
    resumen = metricas.resumen()
    assert any(e["request_id"] == "abc-123" for e in resumen["ultimos_errores"])


def test_el_superadmin_tiene_panel_de_monitoreo():
    codigo = (RAIZ / "app" / "routers" / "plataforma.py").read_text(encoding="utf-8")
    assert '@router.get("/monitoreo")' in codigo
    assert "_requiere_superadmin" in codigo.split('@router.get("/monitoreo")')[1][:800], (
        "el panel de monitoreo debe seguir siendo exclusivo del superadmin"
    )
    assert (RAIZ / "templates" / "plataforma_monitoreo.html").exists()


def test_el_administrador_de_empresa_tiene_su_propio_estado():
    codigo = (RAIZ / "app" / "routers" / "dashboard.py").read_text(encoding="utf-8")
    bloque = codigo.split('@router.get("/estado")')[1][:1200]
    assert 'user.rol not in ("admin", "superadmin")' in bloque, (
        "un cobrador no deberia ver el estado de toda la empresa"
    )
    assert "Cobro.empresa_id == user.empresa_id" in bloque, (
        "el estado debe filtrarse por la empresa del usuario"
    )
    assert (RAIZ / "templates" / "estado_operacion.html").exists()


def test_se_puede_saber_que_version_esta_desplegada():
    """Ante un fallo en produccion hay que poder decir si la version que
    corre incluye o no un arreglo concreto."""
    estado = (RAIZ / "app" / "utils" / "estado_sistema.py").read_text(encoding="utf-8")
    assert "RAILWAY_GIT_COMMIT_SHA" in estado
    assert "alembic_version" in estado


def test_los_recordatorios_no_se_envian_dos_veces_con_varios_workers():
    """El lock evita el envio simultaneo, no el consecutivo.

    La ventana de disparo dura cinco minutos y el control de "ya se envio
    hoy" era memoria de cada proceso: el segundo worker reintentaba cuando
    el primero ya habia soltado el lock y los clientes recibian el mismo
    recordatorio dos veces.
    """
    codigo = (RAIZ / "app" / "services" / "scheduler.py").read_text(encoding="utf-8")
    assert "_ya_se_enviaron_hoy" in codigo
    bloque = codigo.split("async def _recordatorios_async")[1]
    assert bloque.index("_ya_se_enviaron_hoy(db)") < bloque.index("ejecutar_recordatorios(db"), (
        "hay que comprobar la marca ANTES de enviar nada"
    )
    assert "_marcar_enviados_hoy" in bloque
