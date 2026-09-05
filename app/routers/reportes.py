"""Reportes router v2.1 - multi-tenant + auth"""
import datetime, io
from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import StreamingResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.database import get_db, Zona
from app.routers.auth import get_current_user
from app.services.excel_service import reporte_cobros_diarios, reporte_cartera, reporte_resumen_zonas
from app.utils.zone_permissions import get_allowed_zone_ids

router = APIRouter()
templates = Jinja2Templates(directory="templates")


def _excel_response(data: bytes, filename: str) -> StreamingResponse:
    return StreamingResponse(
        io.BytesIO(data),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@router.get("")
@router.get("/")
async def pagina_reportes(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url="/auth/login?next=/reportes", status_code=302)
    hoy = datetime.date.today()
    zonas = db.query(Zona).filter(Zona.empresa_id == user.empresa_id).all()
    return templates.TemplateResponse(request, "reportes.html", {
        "page": "reportes", "zonas": zonas,
        "hoy": hoy.isoformat(),
        "desde": hoy.replace(day=1).isoformat(),
        "hasta": hoy.isoformat(),
        "current_user": user,
    })


@router.get("/cobros-diarios")
async def descargar_cobros_diarios(
    request: Request,
    fecha: str = Query(default=None),
    zona_id: int = Query(default=None),
    db: Session = Depends(get_db)
):
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "No autenticado"}, status_code=401)
    allowed_zones = get_allowed_zone_ids(db, user)
    if allowed_zones is not None and zona_id is not None and zona_id not in allowed_zones:
        return JSONResponse({"error": "Sin permisos para esa zona"}, status_code=403)
    fecha_dt = datetime.date.fromisoformat(fecha) if fecha else datetime.date.today()
    data = reporte_cobros_diarios(db, empresa_id=user.empresa_id, zona_id=zona_id, fecha=fecha_dt, zona_ids=allowed_zones)
    return _excel_response(data, f"cobros_{fecha_dt.strftime('%Y%m%d')}.xlsx")


@router.get("/cartera")
async def descargar_cartera(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "No autenticado"}, status_code=401)
    data = reporte_cartera(db, empresa_id=user.empresa_id, zona_ids=get_allowed_zone_ids(db, user))
    return _excel_response(data, f"cartera_{datetime.date.today().strftime('%Y%m%d')}.xlsx")


@router.get("/resumen-zonas")
async def descargar_resumen_zonas(
    request: Request,
    fecha_desde: str = Query(default=None),
    fecha_hasta: str = Query(default=None),
    db: Session = Depends(get_db)
):
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "No autenticado"}, status_code=401)
    hoy = datetime.date.today()
    f_desde = datetime.date.fromisoformat(fecha_desde) if fecha_desde else hoy.replace(day=1)
    f_hasta = datetime.date.fromisoformat(fecha_hasta) if fecha_hasta else hoy
    data = reporte_resumen_zonas(
        db,
        empresa_id=user.empresa_id,
        fecha_desde=f_desde,
        fecha_hasta=f_hasta,
        zona_ids=get_allowed_zone_ids(db, user),
    )
    return _excel_response(data, f"resumen_zonas_{hoy.strftime('%Y%m%d')}.xlsx")
