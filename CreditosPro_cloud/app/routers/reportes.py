"""Reportes router - Genera y descarga archivos Excel"""
from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import StreamingResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from pathlib import Path
import datetime, io

from app.auth import require_login
from app.database import get_db, Zona
from app.services.excel_service import (
    reporte_cobros_diarios,
    reporte_cartera,
    reporte_resumen_zonas,
)

BASE_DIR = Path(__file__).parent.parent.parent
templates = Jinja2Templates(directory="templates")
router = APIRouter()


def excel_response(data: bytes, filename: str) -> StreamingResponse:
    return StreamingResponse(
        io.BytesIO(data),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@router.get("/")
async def pagina_reportes(request: Request, db: Session = Depends(get_db), current_user=Depends(require_login)):
    hoy = datetime.date.today()
    zonas = db.query(Zona).all()
    return templates.TemplateResponse("reportes.html", context={
        "request": request, "page": "reportes",
        "zonas": zonas,
        "hoy": hoy.isoformat(),
        "desde": hoy.replace(day=1).isoformat(),
        "hasta": hoy.isoformat(),
        "current_user": current_user,
    })


@router.get("/cobros-diarios")
async def descargar_cobros_diarios(
    fecha: str = Query(default=None),
    zona_id: int = Query(default=None),
    db: Session = Depends(get_db),
    current_user=Depends(require_login)
):
    fecha_dt = datetime.date.fromisoformat(fecha) if fecha else datetime.date.today()
    data = reporte_cobros_diarios(db, zona_id=zona_id, fecha=fecha_dt)
    fn = f"cobros_{fecha_dt.strftime('%Y%m%d')}.xlsx"
    return excel_response(data, fn)


@router.get("/cartera")
async def descargar_cartera(db: Session = Depends(get_db), current_user=Depends(require_login)):
    data = reporte_cartera(db)
    fn = f"cartera_{datetime.date.today().strftime('%Y%m%d')}.xlsx"
    return excel_response(data, fn)


@router.get("/resumen-zonas")
async def descargar_resumen_zonas(
    fecha_desde: str = Query(default=None),
    fecha_hasta: str = Query(default=None),
    db: Session = Depends(get_db),
    current_user=Depends(require_login)
):
    hoy = datetime.date.today()
    f_desde = datetime.date.fromisoformat(fecha_desde) if fecha_desde else hoy.replace(day=1)
    f_hasta = datetime.date.fromisoformat(fecha_hasta) if fecha_hasta else hoy
    data = reporte_resumen_zonas(db, f_desde, f_hasta)
    fn = f"resumen_zonas_{hoy.strftime('%Y%m%d')}.xlsx"
    return excel_response(data, fn)
