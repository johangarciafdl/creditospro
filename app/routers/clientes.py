<<<<<<< HEAD
"""
Clientes router v2.3 — multi-tenant
- Carga instantanea (solo zonas al abrir)
- Busqueda AJAX por zona, nombre, cedula
- Sin N+1 queries
- Proteccion SQL injection via SQLAlchemy ORM (nunca raw SQL)
- Validadores centralizados en app.utils.validators
"""
import re
import uuid
import shutil
import datetime
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Request, Depends, UploadFile, File, Form, HTTPException, Query
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func

from app.database import get_db, Cliente, Prestamo, Zona
from app.routers.auth import get_current_user
from app.utils.zone_permissions import get_allowed_zone_ids, require_zone_access, visible_zonas_query
from app.utils.validators import (
    validar_cedula, validar_nombre, validar_telefono, limpiar_texto,
    sanitizar_imagen_subida
)
=======
"""Clientes router v2.1 - multi-tenant, fix TemplateResponse"""
from fastapi import APIRouter, Request, Depends, UploadFile, File, Form, HTTPException
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session, joinedload
from pathlib import Path
import shutil, uuid, datetime

from app.database import get_db, Cliente, Prestamo, Cuota, Zona
from app.routers.auth import get_current_user
>>>>>>> 7761f488b2aa6200974f069ea5072699c6dbd1e5

BASE_DIR = Path(__file__).parent.parent.parent
router = APIRouter()
templates = Jinja2Templates(directory="templates")
UPLOAD_DIR = BASE_DIR / "uploads" / "fotos"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


<<<<<<< HEAD
# ── GET / — Carga instantanea ────────────────────────────────────────────────
@router.get("")
@router.get("/")
async def listar_clientes(request: Request, db: Session = Depends(get_db)):
=======
@router.get("")
@router.get("/")
async def listar_clientes(
    request: Request, q: str = "", zona_id: int = None,
    db: Session = Depends(get_db)
):
>>>>>>> 7761f488b2aa6200974f069ea5072699c6dbd1e5
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url="/auth/login?next=/clientes", status_code=302)

<<<<<<< HEAD
    # SOLO carga zonas (13 registros) — instantaneo
    allowed_zones = get_allowed_zone_ids(db, user)
    zonas = visible_zonas_query(db, user).all()
    total_q = db.query(func.count(Cliente.id)).filter(
        Cliente.empresa_id == user.empresa_id, Cliente.activo == True
    )
    if allowed_zones is not None:
        total_q = total_q.filter(Cliente.zona_id.in_(allowed_zones or [-1]))
    total = total_q.scalar() or 0

    return templates.TemplateResponse(request, "clientes.html", {
        "page": "clientes",
        "clientes": [],
        "zonas": zonas,
        "q": "", "zona_id_sel": None,
        "current_user": user,
        "total_clientes": total,
        "buscando": False,
    })


# ── GET /buscar-ajax — Busqueda AJAX ────────────────────────────────────────
@router.get("/buscar-ajax")
async def buscar_ajax(
    request: Request,
    q: str = "",
    zona_id: int = None,
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db)
):
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "No autorizado"}, status_code=401)

    q = limpiar_texto(q, 100)

    if not q and not zona_id:
        return JSONResponse({"clientes": [], "total": 0, "page": page, "per_page": per_page, "total_pages": 0})

    # Cobrador solo ve su zona
    allowed_zones = get_allowed_zone_ids(db, user)
    if allowed_zones is not None and zona_id and zona_id not in allowed_zones:
        return JSONResponse({"clientes": [], "total": 0, "page": page, "per_page": per_page, "total_pages": 0})

    # Validar que zona_id pertenezca a la empresa si se proporciona
    if zona_id:
        zona_check = db.query(Zona).filter(
            Zona.id == zona_id,
            Zona.empresa_id == user.empresa_id
        ).first()
        if not zona_check:
            return JSONResponse({"clientes": [], "total": 0, "page": page, "per_page": per_page, "total_pages": 0})

    query = db.query(Cliente).filter(
        Cliente.empresa_id == user.empresa_id,
        Cliente.activo == True
    )
    if allowed_zones is not None:
        query = query.filter(Cliente.zona_id.in_(allowed_zones or [-1]))

    if q:
        # ilike usa parametros — SQLAlchemy previene SQL injection
        query = query.filter(
            Cliente.nombre.ilike(f"%{q}%") | Cliente.cedula.ilike(f"%{q}%")
        )
    if zona_id:
        query = query.filter(Cliente.zona_id == zona_id)

    # Paginación
    total = query.count()
    total_pages = (total + per_page - 1) // per_page
    offset = (page - 1) * per_page

    clientes = query.order_by(Cliente.nombre).offset(offset).limit(per_page).all()

    # Cache de zonas — una sola query
    if not hasattr(buscar_ajax, '_zonas_cache'):
        buscar_ajax._zonas_cache = {}
    if user.empresa_id not in buscar_ajax._zonas_cache:
        buscar_ajax._zonas_cache[user.empresa_id] = {
            z.id: z.nombre for z in db.query(Zona).filter(Zona.empresa_id == user.empresa_id).all()
        }
    zonas_dict = buscar_ajax._zonas_cache[user.empresa_id]
    
    # Un solo query para prestamos activos
    ids = [c.id for c in clientes]
    prestamos_map = {}
    if ids:
        for p in db.query(Prestamo).filter(
            Prestamo.cliente_id.in_(ids),
            Prestamo.empresa_id == user.empresa_id,
            Prestamo.estado.in_(["Activo", "activo", "Atrasado", "atrasado"])
        ).all():
            if p.cliente_id not in prestamos_map:
                prestamos_map[p.cliente_id] = p

    result = []
    for c in clientes:
        p = prestamos_map.get(c.id)
        result.append({
            "id": c.id,
            "cedula": c.cedula,
            "nombre": c.nombre,
            "telefono": c.telefono or "",
            "whatsapp": c.whatsapp or "",
            "zona": zonas_dict.get(c.zona_id, "—"),
            "zona_id": c.zona_id,
            "tipo_cliente": c.tipo_cliente or "Regular",
            "foto_path": c.foto_path or "",
            "prestamo": {
                "id": p.id,
                "capital": float(p.capital or 0),
                "total": float(p.total_pagar or p.capital or 0),
                "saldo": float(p.total_pagar or p.capital or 0),
                "num_cuotas": p.num_cuotas or 0,
                "estado": p.estado or "Activo",
            } if p else None,
        })

    return JSONResponse({
        "clientes": result,
        "total": total,
        "page": page,
        "per_page": per_page,
        "total_pages": total_pages,
    })


# ── Sync endpoints para PWA (offline-first) ──────────────────────────────────
@router.get("/sync")
async def sync_clientes(request: Request, db: Session = Depends(get_db)):
    """Retorna todos los clientes activos para sincronización offline."""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "No autorizado"}, status_code=401)
    allowed_zones = get_allowed_zone_ids(db, user)
    clientes = db.query(Cliente).filter(
        Cliente.empresa_id == user.empresa_id, Cliente.activo == True
    )
    if allowed_zones is not None:
        clientes = clientes.filter(Cliente.zona_id.in_(allowed_zones or [-1]))
    clientes = clientes.limit(2000).all()
    return JSONResponse([{
        "id": c.id, "cedula": c.cedula, "nombre": c.nombre,
        "telefono": c.telefono or "", "zona_id": c.zona_id,
        "tipo_cliente": c.tipo_cliente or "Regular",
        "creado": c.creado.isoformat() if c.creado else None,
    } for c in clientes])


# ── POST /nuevo — Crear cliente ──────────────────────────────────────────────
@router.post("/nuevo")
async def crear_cliente(
    request: Request,
    cedula: str = Form(...),
    nombre: str = Form(...),
    telefono: str = Form(...),
    whatsapp: str = Form(""),
    zona_id: str = Form(...),
    direccion: str = Form(""),
    barrio: str = Form(""),
    tipo_cliente: str = Form("Regular"),
=======
    query = db.query(Cliente).options(joinedload(Cliente.zona_rel)).filter(
        Cliente.empresa_id == user.empresa_id, Cliente.activo == True
    )
    if q:
        query = query.filter((Cliente.nombre.ilike(f"%{q}%")) | (Cliente.cedula.ilike(f"%{q}%")))
    if zona_id:
        query = query.filter(Cliente.zona_id == zona_id)
    elif user.rol == "cobrador" and user.zona_id:
        query = query.filter(Cliente.zona_id == user.zona_id)

    clientes = query.order_by(Cliente.nombre).all()
    zonas = db.query(Zona).filter(Zona.empresa_id == user.empresa_id).all()

    data = []
    for c in clientes:
        prestamo_activo = db.query(Prestamo).options(joinedload(Prestamo.cuotas)).filter(
            Prestamo.cliente_id == c.id,
            Prestamo.estado.in_(("Activo", "Atrasado", "Mora"))
        ).first()
        saldo = 0
        cuota_actual = None
        if prestamo_activo:
            pagado = sum(cu.valor_pagado for cu in prestamo_activo.cuotas)
            saldo = max(0.0, (prestamo_activo.total_pagar or 0) - pagado)
            cuota_actual = next(
                (cu for cu in sorted(prestamo_activo.cuotas, key=lambda x: x.numero)
                 if cu.estado in ("Pendiente", "Vencida", "Parcial")), None
            )
        data.append({
            "id": c.id, "cedula": c.cedula, "nombre": c.nombre,
            "telefono": c.telefono, "whatsapp": c.whatsapp,
            "direccion": c.direccion,
            "zona": c.zona_rel.nombre if c.zona_rel else "—",
            "zona_id": c.zona_id,
            "tipo_cliente": c.tipo_cliente,
            "foto_path": c.foto_path, "activo": c.activo,
            "prestamo": {
                "id": prestamo_activo.id,
                "capital": prestamo_activo.capital,
                "total": prestamo_activo.total_pagar,
                "cuotas": f"{cuota_actual.numero if cuota_actual else '?'}/{prestamo_activo.num_cuotas}",
                "saldo": saldo, "estado": prestamo_activo.estado,
                "progreso": round(
                    ((cuota_actual.numero - 1) if cuota_actual else prestamo_activo.num_cuotas)
                    / max(1, prestamo_activo.num_cuotas) * 100, 1
                ),
            } if prestamo_activo else None,
        })

    return templates.TemplateResponse(request, "clientes.html", {
        "page": "clientes", "clientes": data, "zonas": zonas,
        "q": q, "zona_id_sel": zona_id, "current_user": user,
    })


@router.get("/{cliente_id}")
async def detalle_cliente(request: Request, cliente_id: int, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url=f"/auth/login?next=/clientes/{cliente_id}", status_code=302)

    cliente = db.query(Cliente).filter(
        Cliente.id == cliente_id, Cliente.empresa_id == user.empresa_id
    ).first()
    if not cliente:
        raise HTTPException(status_code=404)

    zona = db.query(Zona).filter(Zona.id == cliente.zona_id).first()
    prestamos = db.query(Prestamo).options(joinedload(Prestamo.cuotas)).filter(
        Prestamo.cliente_id == cliente_id
    ).order_by(Prestamo.creado.desc()).all()
    zonas = db.query(Zona).filter(Zona.empresa_id == user.empresa_id).all()

    prestamos_data = []
    for p in prestamos:
        pagado = sum(c.valor_pagado for c in p.cuotas)
        saldo = max(0.0, (p.total_pagar or 0) - pagado)
        vencidas = sum(1 for c in p.cuotas if c.estado == "Vencida")
        prestamos_data.append({
            "id": p.id, "capital": p.capital, "total": p.total_pagar,
            "saldo": saldo, "num_cuotas": p.num_cuotas,
            "pagado": pagado, "vencidas": vencidas,
            "estado": p.estado, "fecha_inicio": p.fecha_inicio,
            "cuotas": [{"num": c.numero, "valor": c.valor,
                        "vencimiento": c.fecha_vencimiento,
                        "estado": c.estado, "pagado": c.valor_pagado}
                       for c in sorted(p.cuotas, key=lambda x: x.numero)],
        })

    return templates.TemplateResponse(request, "cliente_detalle.html", {
        "page": "clientes", "cliente": cliente, "zona": zona,
        "zonas": zonas, "prestamos": prestamos_data, "current_user": user,
    })


@router.post("/nuevo")
async def crear_cliente(
    request: Request,
    cedula: str = Form(...), nombre: str = Form(...),
    telefono: str = Form(...), whatsapp: str = Form(""),
    direccion: str = Form(""), barrio: str = Form(""),
    zona_id: int = Form(...), tipo_cliente: str = Form("Regular"),
    codeudor_nombre: str = Form(""), codeudor_cedula: str = Form(""),
    codeudor_tel: str = Form(""), lat: float = Form(None), lng: float = Form(None),
>>>>>>> 7761f488b2aa6200974f069ea5072699c6dbd1e5
    foto: UploadFile = File(None),
    db: Session = Depends(get_db)
):
    user = get_current_user(request, db)
    if not user:
<<<<<<< HEAD
        return JSONResponse({"error": "No autorizado"}, status_code=401)

    # Validar inputs
    cedula = validar_cedula(cedula)
    nombre = validar_nombre(nombre)
    telefono = validar_telefono(telefono, requerido=True)
    whatsapp = validar_telefono(whatsapp, requerido=False)
    direccion = limpiar_texto(direccion, 300)
    barrio = limpiar_texto(barrio, 100)

    if tipo_cliente not in ("Regular", "Bueno", "Riesgo"):
        tipo_cliente = "Regular"

    if not zona_id or not zona_id.strip().isdigit():
        return JSONResponse({"error": "Zona inválida"}, status_code=400)
    zona_id_int = int(zona_id)

    # Verificar que zona pertenece a empresa
    zona = db.query(Zona).filter(Zona.id == zona_id_int, Zona.empresa_id == user.empresa_id).first()
    if not zona:
        return JSONResponse({"error": "Zona no encontrada"}, status_code=404)
    if not require_zone_access(db, user, zona_id_int):
        return JSONResponse({"error": "No tienes permisos para esa zona"}, status_code=403)

    # Verificar cedula unica por empresa
    existente = db.query(Cliente).filter(
        Cliente.empresa_id == user.empresa_id,
        Cliente.cedula == cedula
    ).first()
    if existente:
        return JSONResponse({"error": f"Ya existe un cliente con cédula {cedula}"}, status_code=400)

    # Foto — validar extension y tamaño
    foto_path = None
    if foto and foto.filename:
        contenido = await foto.read()
        ext, contenido = sanitizar_imagen_subida(foto.filename, contenido)
        nombre_archivo = f"{user.empresa_id}_{uuid.uuid4().hex}{ext}"
        ruta = UPLOAD_DIR / nombre_archivo
        ruta.write_bytes(contenido)
=======
        return JSONResponse({"error": "No autenticado"}, status_code=401)

    existente = db.query(Cliente).filter(
        Cliente.empresa_id == user.empresa_id,
        Cliente.cedula == cedula.strip()
    ).first()
    if existente:
        return JSONResponse({"error": "Ya existe un cliente con esa cédula"}, status_code=400)

    foto_path = None
    if foto and foto.filename:
        ext = Path(foto.filename).suffix.lower()
        if ext not in (".jpg", ".jpeg", ".png", ".webp"):
            return JSONResponse({"error": "Formato de foto no permitido"}, status_code=400)
        nombre_archivo = f"{uuid.uuid4()}{ext}"
        with open(UPLOAD_DIR / nombre_archivo, "wb") as f:
            shutil.copyfileobj(foto.file, f)
>>>>>>> 7761f488b2aa6200974f069ea5072699c6dbd1e5
        foto_path = f"fotos/{nombre_archivo}"

    cliente = Cliente(
        empresa_id=user.empresa_id,
<<<<<<< HEAD
        cedula=cedula,
        nombre=nombre,
        telefono=telefono,
        whatsapp=whatsapp,
        zona_id=zona_id_int,
        direccion=direccion or None,
        barrio=barrio or None,
        tipo_cliente=tipo_cliente,
        foto_path=foto_path,
        activo=True,
=======
        cedula=cedula.strip(), nombre=nombre.strip(),
        telefono=telefono.strip(),
        whatsapp=whatsapp.strip() or telefono.strip(),
        direccion=direccion.strip(), barrio=barrio.strip(),
        zona_id=zona_id, tipo_cliente=tipo_cliente,
        codeudor_nombre=codeudor_nombre.strip() or None,
        codeudor_cedula=codeudor_cedula.strip() or None,
        codeudor_tel=codeudor_tel.strip() or None,
        lat=lat, lng=lng, foto_path=foto_path,
>>>>>>> 7761f488b2aa6200974f069ea5072699c6dbd1e5
    )
    db.add(cliente)
    db.commit()
    db.refresh(cliente)
<<<<<<< HEAD
    return JSONResponse({"ok": True, "id": cliente.id, "mensaje": f"Cliente {nombre} creado"})


# ── GET /{id} — Detalle ──────────────────────────────────────────────────────
@router.post("/{cliente_id}/editar")
async def editar_cliente(
    request: Request,
    cliente_id: int,
    nombre: str = Form(...),
    telefono: str = Form(...),
    whatsapp: str = Form(""),
    zona_id: str = Form(...),
    direccion: str = Form(""),
    barrio: str = Form(""),
    tipo_cliente: str = Form("Regular"),
    lat: str = Form(""),
    lng: str = Form(""),
=======
    return JSONResponse({"ok": True, "id": cliente.id, "mensaje": "Cliente creado"})


@router.post("/{cliente_id}/editar")
async def editar_cliente(
    request: Request, cliente_id: int,
    nombre: str = Form(...), telefono: str = Form(...),
    whatsapp: str = Form(""), direccion: str = Form(""),
    zona_id: int = Form(...), tipo_cliente: str = Form("Regular"),
    lat: float = Form(None), lng: float = Form(None),
>>>>>>> 7761f488b2aa6200974f069ea5072699c6dbd1e5
    foto: UploadFile = File(None),
    db: Session = Depends(get_db)
):
    user = get_current_user(request, db)
    if not user:
<<<<<<< HEAD
        return JSONResponse({"error": "No autorizado"}, status_code=401)

    cliente = db.query(Cliente).filter(
        Cliente.id == cliente_id,
        Cliente.empresa_id == user.empresa_id,
        Cliente.activo == True
    ).first()
    if not cliente:
        return JSONResponse({"error": "Cliente no encontrado"}, status_code=404)
    if not require_zone_access(db, user, cliente.zona_id):
        return JSONResponse({"error": "No tienes permisos para este cliente"}, status_code=403)

    nombre = validar_nombre(nombre)
    telefono = validar_telefono(telefono, requerido=True)
    whatsapp = validar_telefono(whatsapp, requerido=False)
    direccion = limpiar_texto(direccion, 300)
    barrio = limpiar_texto(barrio, 100)
    if tipo_cliente not in ("Regular", "Bueno", "Riesgo"):
        tipo_cliente = "Regular"

    if not zona_id or not zona_id.strip().isdigit():
        return JSONResponse({"error": "Zona invalida"}, status_code=400)
    zona_id_int = int(zona_id)
    zona = db.query(Zona).filter(Zona.id == zona_id_int, Zona.empresa_id == user.empresa_id).first()
    if not zona:
        return JSONResponse({"error": "Zona no encontrada"}, status_code=404)
    if not require_zone_access(db, user, zona_id_int):
        return JSONResponse({"error": "No tienes permisos para esa zona"}, status_code=403)

    cliente.nombre = nombre
    cliente.telefono = telefono
    cliente.whatsapp = whatsapp or None
    cliente.zona_id = zona_id_int
    cliente.direccion = direccion or None
    cliente.barrio = barrio or None
    cliente.tipo_cliente = tipo_cliente

    if lat.strip() and lng.strip():
        try:
            cliente.lat = float(lat)
            cliente.lng = float(lng)
        except ValueError:
            return JSONResponse({"error": "Coordenadas invalidas"}, status_code=400)

    if foto and foto.filename:
        contenido = await foto.read()
        ext, contenido = sanitizar_imagen_subida(foto.filename, contenido)
        nombre_archivo = f"{user.empresa_id}_{cliente.id}_{uuid.uuid4().hex}{ext}"
        ruta = UPLOAD_DIR / nombre_archivo
        ruta.write_bytes(contenido)
        cliente.foto_path = f"fotos/{nombre_archivo}"
=======
        return JSONResponse({"error": "No autenticado"}, status_code=401)

    cliente = db.query(Cliente).filter(
        Cliente.id == cliente_id, Cliente.empresa_id == user.empresa_id
    ).first()
    if not cliente:
        return JSONResponse({"error": "No encontrado"}, status_code=404)

    cliente.nombre = nombre.strip()
    cliente.telefono = telefono.strip()
    cliente.whatsapp = whatsapp.strip() or telefono.strip()
    cliente.direccion = direccion.strip()
    cliente.zona_id = zona_id
    cliente.tipo_cliente = tipo_cliente
    cliente.lat = lat
    cliente.lng = lng
    cliente.actualizado = datetime.datetime.now()

    if foto and foto.filename:
        ext = Path(foto.filename).suffix.lower()
        if ext in (".jpg", ".jpeg", ".png", ".webp"):
            nombre_archivo = f"{uuid.uuid4()}{ext}"
            with open(UPLOAD_DIR / nombre_archivo, "wb") as f:
                shutil.copyfileobj(foto.file, f)
            cliente.foto_path = f"fotos/{nombre_archivo}"
>>>>>>> 7761f488b2aa6200974f069ea5072699c6dbd1e5

    db.commit()
    return JSONResponse({"ok": True, "mensaje": "Cliente actualizado"})


<<<<<<< HEAD
@router.get("/{cliente_id}")
async def detalle_cliente(
    request: Request,
    cliente_id: int,
    db: Session = Depends(get_db)
):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url="/auth/login", status_code=302)

    cliente = db.query(Cliente).filter(
        Cliente.id == cliente_id,
        Cliente.empresa_id == user.empresa_id  # Aislamiento multi-tenant
    ).first()
    if not cliente:
        raise HTTPException(404, "Cliente no encontrado")
    if not require_zone_access(db, user, cliente.zona_id):
        raise HTTPException(403, "Sin permisos para este cliente")

    prestamos = db.query(Prestamo).options(joinedload(Prestamo.cuotas)).filter(
        Prestamo.cliente_id == cliente_id,
        Prestamo.empresa_id == user.empresa_id
    ).order_by(Prestamo.creado.desc()).all()

    zona = db.query(Zona).filter(Zona.id == cliente.zona_id).first() if cliente.zona_id else None
    zonas = visible_zonas_query(db, user).all()

    prestamos_data = []
    for p in prestamos:
        pagado = sum(c.valor_pagado or 0 for c in p.cuotas)
        saldo = max(0.0, (p.total_pagar or p.capital or 0) - pagado)
        prestamos_data.append({
            "id": p.id, "capital": p.capital or 0,
            "total": p.total_pagar or p.capital or 0,
            "saldo": saldo, "pagado": pagado,
            "num_cuotas": p.num_cuotas or 0,
            "valor_cuota": p.valor_cuota or 0,
            "estado": p.estado or "Activo",
            "vencidas": sum(1 for c in p.cuotas if (c.estado or "") == "Vencida"),
            "fecha_inicio": p.fecha_inicio.strftime("%d/%m/%Y") if p.fecha_inicio else "—",
            "fecha_fin": p.fecha_fin.strftime("%d/%m/%Y") if p.fecha_fin else "—",
            "cuotas": [{
                "numero": c.numero, "valor": c.valor or 0,
                "valor_pagado": c.valor_pagado or 0,
                "fecha_vencimiento": c.fecha_vencimiento.strftime("%d/%m/%Y") if c.fecha_vencimiento else "—",
                "estado": c.estado or "Pendiente",
            } for c in sorted(p.cuotas, key=lambda x: x.numero)],
        })

    return templates.TemplateResponse(request, "cliente_detalle.html", {
        "page": "clientes", "current_user": user,
        "cliente": cliente, "zona": zona, "zonas": zonas,
        "prestamos": prestamos_data,
    })
=======
@router.delete("/{cliente_id}")
async def eliminar_cliente(request: Request, cliente_id: int, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user or user.rol not in ("admin", "supervisor", "superadmin"):
        return JSONResponse({"error": "Sin permisos"}, status_code=403)

    cliente = db.query(Cliente).filter(
        Cliente.id == cliente_id, Cliente.empresa_id == user.empresa_id
    ).first()
    if not cliente:
        return JSONResponse({"error": "No encontrado"}, status_code=404)
    cliente.activo = False
    db.commit()
    return JSONResponse({"ok": True})
>>>>>>> 7761f488b2aa6200974f069ea5072699c6dbd1e5
