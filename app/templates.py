"""Instancia compartida de Jinja2Templates.

Unico punto de creacion para toda la app -- antes cada router creaba su
propia instancia (11 en total), lo que habria obligado a repetir la
configuracion de context_processors en cada una. Con una sola instancia,
{{ csp_nonce }} queda disponible en cualquier template sin que cada ruta
tenga que pasarlo explicitamente en el contexto.
"""
from fastapi.templating import Jinja2Templates

from app.utils.estaticos import estatico


def _csp_context(request):
    return {"csp_nonce": getattr(request.state, "csp_nonce", "")}


templates = Jinja2Templates(directory="templates", context_processors=[_csp_context])

# {{ estatico('js/app.js') }} devuelve la URL versionada por contenido
# (/static/dist/js/app.<hash>.js), que se sirve con cache de un año. Sin esto
# habria que escribir la ruta con hash a mano en cada plantilla y actualizarla
# en cada despliegue.
templates.env.globals["estatico"] = estatico
