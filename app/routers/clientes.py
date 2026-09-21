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
from app.templates import templates
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError

from app.database import get_db, Cliente, NoPago, Prestamo, Usuario, Zona
from app.utils.almacen_imagenes import borrar_imagen, guardar_imagen
from app.routers.auth import get_current_user
from app.utils.zone_permissions import get_allowed_zone_ids, require_zone_access, visible_zonas_query
from app.utils.validators import (
    validar_cedula, validar_nombre, validar_telefono, validar_whatsapp, limpiar_texto,
    sanitizar_imagen_subida, sin_html, filtro_busqueda,
)

BASE_DIR = Path(__file__).parent.parent.parent
router = APIRouter()
UPLOAD_DIR = BASE_DIR / "uploads" / "fotos"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


# ── GET / — Carga instantanea ────────────────────────────────────────────────
@router.get("")
@router.get("/")
async def listar_clientes(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url="/auth/login?next=/clientes", status_code=302)

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
    todos: int = 0,
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db)
):
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "No autorizado"}, status_code=401)

    q = limpiar_texto(q, 100)

    # Entrar al modulo no dispara ninguna consulta: sin busqueda ni zona, y sin
    # el todos=1 que manda el boton "Ver todos", no se devuelve nada. Cargar la
    # lista completa de entrada era lo que hacia lento el modulo.
    if not q and not zona_id and not todos:
        return JSONResponse({"clientes": [], "total": 0, "page": page,
                             "per_page": per_page, "total_pages": 0,
                             "requiere_filtro": True})

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
        # Busqueda por palabras: ver filtro_busqueda(). ilike usa
        # parametros -- SQLAlchemy previene SQL injection.
        condicion = filtro_busqueda(q, Cliente.nombre, Cliente.cedula)
        if condicion is not None:
            query = query.filter(condicion)
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
    foto: UploadFile = File(None),
    db: Session = Depends(get_db)
):
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "No autorizado"}, status_code=401)

    # Validar inputs
    try:
        cedula = validar_cedula(cedula)
        nombre = validar_nombre(nombre)
        telefono = validar_telefono(telefono, requerido=True)
        whatsapp = validar_whatsapp(whatsapp, requerido=False)
        direccion = sin_html(direccion, "Dirección", 300)
        barrio = sin_html(barrio, "Barrio", 100)
    except HTTPException as e:
        return JSONResponse({"error": e.detail}, status_code=e.status_code)

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
        nombre_archivo = guardar_imagen(db, user.empresa_id, contenido, ext, "cliente")
        foto_path = f"fotos/{nombre_archivo}"

    cliente = Cliente(
        empresa_id=user.empresa_id,
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
    )
    db.add(cliente)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        return JSONResponse({"error": f"Ya existe un cliente con cédula {cedula}"}, status_code=400)
    db.refresh(cliente)
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
    foto: UploadFile = File(None),
    db: Session = Depends(get_db)
):
    user = get_current_user(request, db)
    if not user:
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

    try:
        nombre = validar_nombre(nombre)
        # Un telefono heredado que ya estaba mal (ej. el "000" de la migracion
        # inicial) no bloquea editar la direccion de ese cliente: solo se exige
        # el formato nuevo cuando de verdad se esta cambiando el numero.
        if (telefono or "").strip() != (cliente.telefono or ""):
            telefono = validar_telefono(telefono, requerido=True)
        if (whatsapp or "").strip() != (cliente.whatsapp or ""):
            whatsapp = validar_whatsapp(whatsapp, requerido=False)
        direccion = sin_html(direccion, "Dirección", 300)
        barrio = sin_html(barrio, "Barrio", 100)
    except HTTPException as e:
        return JSONResponse({"error": e.detail}, status_code=e.status_code)
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
        anterior = (cliente.foto_path or "").removeprefix("fotos/")
        nombre_archivo = guardar_imagen(db, user.empresa_id, contenido, ext,
                                        "cliente", cliente.id)
        cliente.foto_path = f"fotos/{nombre_archivo}"
        borrar_imagen(db, user.empresa_id, anterior)

    db.commit()
    return JSONResponse({"ok": True, "mensaje": "Cliente actualizado"})


def _cliente_editable(db: Session, user, cliente_id: int):
    """Cliente de la empresa del usuario, con permiso de zona. None si no aplica."""
    cliente = db.query(Cliente).filter(
        Cliente.id == cliente_id,
        Cliente.empresa_id == user.empresa_id,
        Cliente.activo == True,
    ).first()
    if not cliente or not require_zone_access(db, user, cliente.zona_id):
        return None
    return cliente


# Actualizaciones parciales con endpoint propio. Antes estas dos acciones
# reusaban /editar mandando solo 4 campos, y como el resto del formulario
# llegaba vacio se guardaba vacio: tomar una foto o capturar el GPS BORRABA
# la direccion, el barrio y el WhatsApp del cliente. Con un endpoint por
# accion, una actualizacion parcial no puede tocar campos que no envia.
@router.post("/{cliente_id}/ubicacion")
async def actualizar_ubicacion(
    request: Request, cliente_id: int,
    lat: str = Form(...), lng: str = Form(...),
    db: Session = Depends(get_db),
):
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "No autorizado"}, status_code=401)
    cliente = _cliente_editable(db, user, cliente_id)
    if not cliente:
        return JSONResponse({"error": "Cliente no encontrado"}, status_code=404)

    try:
        lat_val, lng_val = float(lat), float(lng)
    except (TypeError, ValueError):
        return JSONResponse({"error": "Coordenadas invalidas"}, status_code=400)
    if not (-90 <= lat_val <= 90) or not (-180 <= lng_val <= 180):
        return JSONResponse({"error": "Coordenadas fuera de rango"}, status_code=400)

    cliente.lat, cliente.lng = lat_val, lng_val
    db.commit()
    return JSONResponse({"ok": True, "mensaje": "Ubicación guardada"})


@router.post("/{cliente_id}/foto")
async def actualizar_foto(
    request: Request, cliente_id: int,
    foto: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "No autorizado"}, status_code=401)
    cliente = _cliente_editable(db, user, cliente_id)
    if not cliente:
        return JSONResponse({"error": "Cliente no encontrado"}, status_code=404)
    if not foto or not foto.filename:
        return JSONResponse({"error": "No se recibió ninguna foto"}, status_code=400)

    try:
        contenido = await foto.read()
        ext, contenido = sanitizar_imagen_subida(foto.filename, contenido)
    except HTTPException as e:
        return JSONResponse({"error": e.detail}, status_code=e.status_code)

    anterior = (cliente.foto_path or "").removeprefix("fotos/")
    nombre_archivo = guardar_imagen(db, user.empresa_id, contenido, ext,
                                    "cliente", cliente.id)
    cliente.foto_path = f"fotos/{nombre_archivo}"
    # La imagen sustituida ya no la referencia nadie.
    borrar_imagen(db, user.empresa_id, anterior)
    db.commit()
    return JSONResponse({"ok": True, "mensaje": "Foto actualizada"})


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

    # Visitas en las que se fue a cobrar y el cliente no pago. Se traen de una
    # sola consulta para no hacer una por cuota.
    no_pagos_por_cuota: dict[int, list] = {}
    for np in (
        db.query(NoPago)
        .filter(NoPago.cliente_id == cliente.id, NoPago.empresa_id == user.empresa_id)
        .order_by(NoPago.fecha)
        .all()
    ):
        no_pagos_por_cuota.setdefault(np.cuota_id, []).append(np.fecha)

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
                # El id hace falta para poder cobrar la cuota desde el perfil.
                "id": c.id,
                "numero": c.numero, "valor": c.valor or 0,
                "valor_pagado": c.valor_pagado or 0,
                "fecha_vencimiento": c.fecha_vencimiento.strftime("%d/%m/%Y") if c.fecha_vencimiento else "—",
                # Cuando se pago de verdad, que puede no ser el dia que vencia.
                "fecha_pago": c.fecha_pago.strftime("%d/%m/%Y") if c.fecha_pago else "",
                "dias_tarde": ((c.fecha_pago - c.fecha_vencimiento).days
                               if c.fecha_pago and c.fecha_vencimiento
                               and c.fecha_pago > c.fecha_vencimiento else 0),
                "no_pagos": [f.strftime("%d/%m/%Y") for f in no_pagos_por_cuota.get(c.id, [])],
                "estado": c.estado or "Pendiente",
            } for c in sorted(p.cuotas, key=lambda x: x.numero)],
        })

    # El cobrador del prestamo se escribia a mano en un campo de texto: un
    # error de tecleo creaba un "cobrador" que no existe y los informes por
    # cobrador dejaban de cuadrar. Se envia la lista real para elegir.
    cobradores = (
        db.query(Usuario)
        .filter(
            Usuario.empresa_id == user.empresa_id,
            Usuario.activo == True,
            Usuario.rol.in_(("cobrador", "supervisor", "admin")),
        )
        .order_by(Usuario.nombre)
        .all()
    )

    return templates.TemplateResponse(request, "cliente_detalle.html", {
        "page": "clientes", "current_user": user,
        "cliente": cliente, "zona": zona, "zonas": zonas,
        "prestamos": prestamos_data,
        "cobradores": cobradores,
    })
