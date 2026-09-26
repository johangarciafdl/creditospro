"""La vista unica del cobrador: su ruta del dia y nada mas.

Es la pantalla de la interfaz `simple` (ver `app/utils/interfaz.py`). No
añade ningun permiso: cobrar y consultar es lo mismo que puede hacer en la
interfaz completa, solo que aqui lo tiene todo en una pantalla de celular en
vez de repartido en tres modulos.

El admin tambien puede abrirla. No es un descuido: si va a encender esta
interfaz para su equipo, necesita poder ver antes lo que van a ver ellos.
"""
from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.routers.auth import get_current_user
from app.templates import templates
from app.utils.zone_permissions import get_allowed_zone_ids, visible_zonas_query

router = APIRouter()


@router.get("/ruta")
async def mi_ruta(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse("/auth/login?next=/ruta", status_code=302)

    # Las zonas que puede elegir hoy. Para un cobrador con ruta semanal
    # configurada son solo las que le tocan hoy (lo resuelve
    # get_allowed_zone_ids); para un admin, todas las de la empresa.
    zonas = visible_zonas_query(db, user).all()
    zonas.sort(key=lambda z: (z.nombre or "").lower())

    return templates.TemplateResponse(request, "app_cobrador.html", {
        "page": "ruta",
        "current_user": user,
        "zonas": zonas,
        # Con una sola zona no tiene sentido obligar a elegirla: se
        # preselecciona y la pantalla carga con ella.
        "zona_unica": zonas[0].id if len(zonas) == 1 else None,
        "sin_zonas": not zonas and get_allowed_zone_ids(db, user) is not None,
    })
