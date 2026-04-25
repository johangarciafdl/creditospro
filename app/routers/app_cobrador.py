# -*- coding: utf-8 -*-
"""
App Cobrador — Router para la PWA móvil
Solo accesible para usuarios con rol cobrador
"""
from fastapi import APIRouter, Request, Depends, Form, UploadFile, File
from fastapi.responses import JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy import func
import datetime, uuid, shutil
from pathlib import Path

from app.database import get_db, Cuota, Prestamo, Cliente, Zona, Cobro, Usuario
from app.auth import require_login, get_current_empresa

router = APIRouter()
templates = Jinja2Templates(directory="templates")
BASE_DIR = Path(__file__).parent.parent.parent
UPLOAD_DIR = BASE_DIR / "uploads" / "fotos"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


def require_cobrador(current_user=Depends(require_login)):
    return current_user


@router.get("/")
async def app_home(request: Request, current_user=Depends(require_cobrador)):
    """Página principal de la app del cobrador"""
    return templates.TemplateResponse("app_cobrador.html", {
        "request": request,
        "current_user": current_user,
        "page": "app"
    })


@router.get("/ruta")
async def mi_ruta(
    request: Request,
    db: Session = Depends(get_db),
    current_user=Depends(require_cobrador),
    empresa_id: int = Depends(get_current_empresa),
):
    """Ruta del cobrador ordenada por distancia desde primera ubicación"""
    hoy = datetime.date.today()

    # Obtener zona del cobrador
    zona_id = current_user.zona_id

    query = db.query(Cuota, Prestamo, Cliente).join(
        Prestamo, Cuota.prestamo_id == Prestamo.id
    ).join(Cliente, Prestamo.cliente_id == Cliente.id).filter(
        Cuota.estado.in_(["Pendiente", "Vencida"]),
        Prestamo.empresa_id == empresa_id
    )

    if zona_id:
        query = query.filter(Prestamo.zona_id == zona_id)

    pendientes_raw = query.all()

    # Ordenar por distancia usando algoritmo greedy si hay coordenadas
    clientes_con_coords = []
    clientes_sin_coords = []

    for cuota, prestamo, cliente in pendientes_raw:
        item = {
            "cuota_id": cuota.id,
            "prestamo_id": prestamo.id,
            "cliente_id": cliente.id,
            "cliente_nombre": cliente.nombre,
            "cliente_cedula": cliente.cedula,
            "cliente_tel": cliente.telefono,
            "direccion": cliente.direccion or "Sin dirección",
            "valor_cuota": cuota.valor,
            "num_cuota": cuota.numero,
            "total_cuotas": prestamo.num_cuotas,
            "vencimiento": cuota.fecha_vencimiento.strftime("%d/%m/%Y"),
            "dias_vencida": (hoy - cuota.fecha_vencimiento).days,
            "estado": cuota.estado,
            "lat": cliente.lat,
            "lng": cliente.lng,
            "foto_path": cliente.foto_path,
        }
        if cliente.lat and cliente.lng:
            clientes_con_coords.append(item)
        else:
            clientes_sin_coords.append(item)

    # Algoritmo greedy: ordenar por distancia desde el primero
    def distancia(a, b):
        if not (a["lat"] and b["lat"]):
            return 0
        return ((a["lat"] - b["lat"]) ** 2 + (a["lng"] - b["lng"]) ** 2) ** 0.5

    ruta_ordenada = []
    if clientes_con_coords:
        pendientes_ord = clientes_con_coords.copy()
        actual = pendientes_ord.pop(0)
        ruta_ordenada.append(actual)
        while pendientes_ord:
            mas_cercano = min(pendientes_ord, key=lambda x: distancia(actual, x))
            pendientes_ord.remove(mas_cercano)
            ruta_ordenada.append(mas_cercano)
            actual = mas_cercano

    ruta_final = ruta_ordenada + clientes_sin_coords

    # Numerar paradas
    for i, item in enumerate(ruta_final):
        item["parada"] = i + 1

    zona = db.query(Zona).filter(Zona.id == zona_id).first() if zona_id else None

    return templates.TemplateResponse("app_ruta.html", {
        "request": request,
        "current_user": current_user,
        "ruta": ruta_final,
        "zona": zona,
        "hoy": hoy.strftime("%d/%m/%Y"),
        "total": len(ruta_final),
        "page": "app"
    })


@router.post("/cobrar")
async def registrar_cobro_app(
    cuota_id: int = Form(...),
    valor_cobrado: float = Form(...),
    metodo_pago: str = Form("Efectivo"),
    observaciones: str = Form(""),
    lat: float = Form(None),
    lng: float = Form(None),
    foto: UploadFile = File(None),
    db: Session = Depends(get_db),
    current_user=Depends(require_cobrador),
    empresa_id: int = Depends(get_current_empresa),
):
    if valor_cobrado <= 0:
        return JSONResponse({"ok": False, "detail": "Valor inválido"}, status_code=400)

    cuota = db.query(Cuota).filter(Cuota.id == cuota_id).first()
    if not cuota:
        return JSONResponse({"ok": False, "detail": "Cuota no encontrada"}, status_code=404)
    if cuota.estado == "Pagada":
        return JSONResponse({"ok": False, "detail": "Esta cuota ya fue pagada"}, status_code=400)

    prestamo = db.query(Prestamo).filter(Prestamo.id == cuota.prestamo_id).first()

    # Guardar foto de novedad si existe
    foto_path = None
    if foto and foto.filename:
        ext = Path(foto.filename).suffix.lower()
        if ext in [".jpg", ".jpeg", ".png", ".webp"]:
            nombre_archivo = f"novedad_{uuid.uuid4()}{ext}"
            with open(UPLOAD_DIR / nombre_archivo, "wb") as f:
                shutil.copyfileobj(foto.file, f)
            foto_path = f"fotos/{nombre_archivo}"

    try:
        cobro = Cobro(
            empresa_id=empresa_id,
            cuota_id=cuota_id,
            prestamo_id=prestamo.id,
            cliente_id=prestamo.cliente_id,
            zona_id=prestamo.zona_id,
            valor_cobrado=valor_cobrado,
            metodo_pago=metodo_pago,
            cobrador=current_user.nombre_completo,
            observaciones=observaciones or None,
            foto_novedad=foto_path,
            lat_cobro=lat,
            lng_cobro=lng,
            fecha=datetime.date.today(),
            usuario_id=current_user.id,
        )
        db.add(cobro)

        cuota.valor_pagado = (cuota.valor_pagado or 0) + valor_cobrado
        if cuota.valor_pagado >= cuota.valor:
            cuota.estado = "Pagada"
            cuota.fecha_pago = datetime.date.today()
        else:
            cuota.estado = "Parcial"

        # Verificar si préstamo completo
        cuotas_pendientes = [c for c in prestamo.cuotas if c.estado not in ["Pagada"]]
        if not cuotas_pendientes:
            prestamo.estado = "Cancelado"

        db.commit()
        return JSONResponse({"ok": True, "mensaje": f"Cobro de ${valor_cobrado:,.0f} registrado"})
    except Exception as e:
        db.rollback()
        return JSONResponse({"ok": False, "detail": str(e)}, status_code=500)


@router.get("/resumen")
async def resumen_dia(
    request: Request,
    db: Session = Depends(get_db),
    current_user=Depends(require_cobrador),
    empresa_id: int = Depends(get_current_empresa),
):
    """Resumen del día para el cobrador"""
    hoy = datetime.date.today()
    cobros_hoy = db.query(Cobro).filter(
        Cobro.fecha == hoy,
        Cobro.usuario_id == current_user.id,
    ).all()

    total_cobrado = sum(c.valor_cobrado for c in cobros_hoy)

    return templates.TemplateResponse("app_resumen.html", {
        "request": request,
        "current_user": current_user,
        "cobros": cobros_hoy,
        "total_cobrado": total_cobrado,
        "cantidad": len(cobros_hoy),
        "hoy": hoy.strftime("%d/%m/%Y"),
        "page": "app"
    })
