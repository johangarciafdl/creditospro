"""El navegador no debe inventarse por que fallo algo.

Dos veces en este proyecto un error se presento como otra cosa y el
diagnostico se fue a la parte del sistema que si funcionaba:

  - El login decidia el exito con `r.url !== location.href`, una propiedad
    que no dice nada del resultado. Con credenciales malas el servidor
    respondia 401 con la misma plantilla, la condicion daba verdadero y el
    cliente mostraba la animacion de exito. El sintoma que se reporto fue
    "el registro de usuarios no funciona", y el registro estaba perfecto.
  - Las busquedas trataban cualquier error como caida de red: un 403 de
    permisos se anunciaba como "sin conexion" y se mostraban datos viejos
    del celular como si fueran los buenos.

Las dos reglas que quedan fijadas aqui: la condicion de exito se apoya en
algo que el servidor emite a proposito, y la rama de fallo lee el motivo
que el servidor manda en vez de inventarse uno.
"""
import pathlib
import re

RAIZ = pathlib.Path(__file__).resolve().parent.parent
FRONT = [RAIZ / "templates", RAIZ / "static" / "js"]


def _lineas():
    for carpeta in FRONT:
        for ruta in list(carpeta.rglob("*.html")) + list(carpeta.rglob("*.js")):
            texto = ruta.read_text(encoding="utf-8")
            for n, linea in enumerate(texto.splitlines(), 1):
                # Los comentarios explican fallos pasados; no son codigo.
                despejada = re.sub(r"//.*$", "", linea)
                if despejada.strip().startswith(("*", "{#", "#}")):
                    continue
                yield ruta, n, despejada


def test_el_exito_no_se_deduce_de_la_url_de_la_respuesta():
    """r.url no dice si la operacion salio bien; el estado HTTP si."""
    culpables = [
        f"{ruta.name}:{n}: {linea.strip()[:90]}"
        for ruta, n, linea in _lineas()
        if re.search(r"\br\.url\s*(!==|===|!=|==)", linea)
    ]
    assert not culpables, (
        "Decide el exito por el estado HTTP o por la ruta de destino:"
        + chr(10) + "  " + (chr(10) + "  ").join(culpables)
    )


def test_la_rama_de_fallo_no_descarta_el_motivo_del_servidor():
    """`if (!r.ok) throw new Error('HTTP 403')` tira el mensaje util."""
    culpables = [
        f"{ruta.name}:{n}: {linea.strip()[:90]}"
        for ruta, n, linea in _lineas()
        if re.search(r"if\s*\(\s*!\s*\w+\.ok\s*\)\s*throw", linea)
    ]
    assert not culpables, (
        "Lee el cuerpo y muestra d.error antes de lanzar:"
        + chr(10) + "  " + (chr(10) + "  ").join(culpables)
    )


def test_solo_un_fallo_de_red_activa_el_modo_sin_conexion():
    """Un 500 mostrado como 'sin conexion' esconde el fallo real.

    fetch solo lanza TypeError cuando la peticion no llega a salir; una
    respuesta de error si llega y hay que tratarla como lo que es.
    """
    ficheros_con_respaldo = []
    for carpeta in FRONT:
        for ruta in list(carpeta.rglob("*.html")) + list(carpeta.rglob("*.js")):
            texto = ruta.read_text(encoding="utf-8")
            if "Offline(" in texto and "catch" in texto and "window.pwa" in texto:
                ficheros_con_respaldo.append((ruta, texto))

    assert ficheros_con_respaldo, "la prueba dejo de encontrar el codigo que vigila"
    sin_distinguir = [
        ruta.name
        for ruta, texto in ficheros_con_respaldo
        # El respaldo dentro de un catch exige comprobar que fue de red.
        if re.search(r"catch\s*\([^)]*\)\s*\{[^}]*Offline\(", texto, re.S)
        and "instanceof TypeError" not in texto
        and "navigator.onLine" not in texto
    ]
    assert not sin_distinguir, (
        "Cae al modo sin conexion sin comprobar que el fallo fue de red: "
        + ", ".join(sin_distinguir)
    )
