"""Instancia compartida de Jinja2Templates.

Unico punto de creacion para toda la app -- antes cada router creaba su
propia instancia (11 en total), lo que habria obligado a repetir la
configuracion de context_processors en cada una. Con una sola instancia,
{{ csp_nonce }} queda disponible en cualquier template sin que cada ruta
tenga que pasarlo explicitamente en el contexto.
"""
from fastapi.templating import Jinja2Templates

from app.utils.estaticos import estatico
from app.utils.money import cop


def _csp_context(request):
    return {"csp_nonce": getattr(request.state, "csp_nonce", "")}


templates = Jinja2Templates(directory="templates", context_processors=[_csp_context])

# {{ estatico('js/app.js') }} devuelve la URL versionada por contenido
# (/static/dist/js/app.<hash>.js), que se sirve con cache de un año. Sin esto
# habria que escribir la ruta con hash a mano en cada plantilla y actualizarla
# en cada despliegue.
templates.env.globals["estatico"] = estatico


# Un solo formateador de pesos en todo el proyecto. Habia dos: este, que
# redondeaba al peso entero, y el de app/utils/money.py, que no. Como las
# plantillas usaban uno y los mensajes de las respuestas el otro, la misma
# cuota de 0,10 salia como "$0" en la tabla de cuotas y como "$0,10" en el
# formulario de cobro. Dos implementaciones del mismo concepto siempre
# terminan separandose; la de money.py es la unica.
templates.env.filters["cop"] = cop
templates.env.globals["cop"] = cop
