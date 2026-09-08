"""Instancia compartida de Jinja2Templates.

Unico punto de creacion para toda la app -- antes cada router creaba su
propia instancia (11 en total), lo que habria obligado a repetir la
configuracion de context_processors en cada una. Con una sola instancia,
{{ csp_nonce }} queda disponible en cualquier template sin que cada ruta
tenga que pasarlo explicitamente en el contexto.
"""
from fastapi.templating import Jinja2Templates


def _csp_context(request):
    return {"csp_nonce": getattr(request.state, "csp_nonce", "")}


templates = Jinja2Templates(directory="templates", context_processors=[_csp_context])
