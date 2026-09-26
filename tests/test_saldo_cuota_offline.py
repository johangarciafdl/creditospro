"""El celular necesita el saldo real de cada cuota, no solo su valor.

Sin `valor_pagado` en /prestamos/sync/cuotas, la PWA calculaba el saldo de
una cuota Parcial como si nada se hubiera abonado, cobraba el valor completo
y el servidor rechazaba el envio con "El valor supera el saldo de la cuota"
al recuperar señal — el cobro se perdia sin que el cobrador se enterara.
"""
import re
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
FIN_FUNCION = chr(10) + "}" + chr(10)


def test_sync_cuotas_incluye_valor_pagado():
    codigo = (RAIZ / "app" / "routers" / "prestamos.py").read_text(encoding="utf-8")
    bloque = codigo.split("async def sync_cuotas")[1].split("@router")[0]
    assert '"valor_pagado"' in bloque, (
        "/prestamos/sync/cuotas debe enviar valor_pagado para que el celular "
        "pueda calcular el saldo pendiente sin señal"
    )


def test_cobros_calcula_el_saldo_y_no_el_valor():
    """Cobros arma el saldo en el navegador, a partir de valor y valor_pagado."""
    html = (RAIZ / "templates" / "cobros.html").read_text(encoding="utf-8")
    assert "Number(p.valor||0) - Number(p.valor_pagado||0)" in html, (
        "cobros.html debe calcular el saldo pendiente de la cuota"
    )
    assert "const saldo = Math.round(" in html, (
        "cobros.html debe redondear el saldo a centavos"
    )
    llamadas = re.findall(r"abrirCobro\((.*?)\)\"", html)
    assert llamadas, "cobros.html: no se encontro la llamada a abrirCobro"
    for args in llamadas:
        assert "Number(p.valor||0)" not in args, (
            "cobros.html: abrirCobro recibe el valor total de la cuota en vez del saldo"
        )


def test_la_vista_simple_prellena_el_saldo_que_calculo_el_servidor():
    """La garantia es la misma; quien hace la resta, no.

    La vista del cobrador recibe el saldo ya calculado (`falta`) desde
    /ruta/zona, donde se hace con Decimal. Restar otra vez en el navegador
    seria una segunda implementacion del mismo concepto, que es exactamente
    como las dos pantallas empiezan a discrepar en los centavos. Lo que no
    puede pasar, igual que antes, es pre-llenar el cobro con el valor total
    de la cuota.
    """
    html = (RAIZ / "templates" / "app_cobrador.html").read_text(encoding="utf-8")
    ruta = (RAIZ / "app" / "routers" / "ruta.py").read_text(encoding="utf-8")
    assert 'money(cu.valor) - money(cu.valor_pagado or 0)' in ruta, (
        "/ruta/zona debe calcular el saldo pendiente con Decimal"
    )
    assert '"falta": float(falta)' in ruta, (
        "/ruta/zona debe enviar el saldo pendiente de la cuota"
    )
    llamadas = re.findall(r"abrirCobro\((.*?)\)\"", html)
    assert llamadas, "app_cobrador.html: no se encontro la llamada a abrirCobro"
    for args in llamadas:
        assert "p.falta" in args, (
            "app_cobrador.html: abrirCobro debe recibir el saldo (falta), no el valor"
        )
        assert "p.valor" not in args, (
            "app_cobrador.html: abrirCobro recibe el valor total de la cuota"
        )


def test_perfil_no_trunca_los_centavos_del_saldo():
    html = (RAIZ / "templates" / "cliente_detalle.html").read_text(encoding="utf-8")
    assert "round(0, 'floor')|int" not in html, (
        "truncar el saldo a pesos enteros deja en 0 las cuotas de menos de $1 "
        "y bloquea el cobro desde el perfil"
    )
    assert "'%.2f'|format(c.valor - c.valor_pagado)" in html


def test_cobro_rapido_sin_senal_usa_la_regla_del_servidor():
    """El boton Cobrar de Clientes debe elegir la misma cuota con y sin señal.

    La funcion que lo resuelve paso de llamarse cobrarSinSenal a ser la rama
    sin conexion de cobrarCliente, cuando Clientes adopto el modal de cobro
    completo que ya usaba el modulo de Cobros. Lo que se exige aqui no es el
    nombre sino la garantia: con y sin señal debe elegirse la misma cuota.
    """
    html = (RAIZ / "templates" / "clientes.html").read_text(encoding="utf-8").replace(chr(13), "")
    assert "getProximaCuotaCliente" in html
    cuerpo_js = html.split("async function cobrarCliente")[1].split(FIN_FUNCION)[0]
    assert "getProximaCuotaCliente" in cuerpo_js, (
        "la rama sin conexion de cobrarCliente debe usar la misma regla que "
        "el servidor para elegir la cuota"
    )
    assert "pwa.getPendientesOffline" not in cuerpo_js, (
        "getPendientesOffline solo ve los proximos 3 dias; el servidor no "
        "aplica ventana de fechas al cobro rapido"
    )

    pwa = (RAIZ / "static" / "js" / "pwa.js").read_text(encoding="utf-8").replace(chr(13), "")
    assert "getProximaCuotaCliente," in pwa, "el helper debe exportarse en window.pwa"
    cuerpo = pwa.split("async function getProximaCuotaCliente")[1].split("\n}\n")[0]
    assert "setDate" not in cuerpo, "no debe filtrar por ventana de fechas"
    assert "saldo > 0" in cuerpo, "debe descartar cuotas ya cubiertas"
