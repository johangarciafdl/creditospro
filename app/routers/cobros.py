from fastapi import APIRouter, Request, Depends, Form, UploadFile, File
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy import func
import datetime
import uuid
from pathlib import Path

from app.database import get_db, Cobro, Cuota, Prestamo, Cliente, Zona
from app.routers.auth import get_current_user
from app.services.prestamo_service import get_estado_prestamo
from app.utils.money import money
from app.utils.validators import sanitizar_imagen_subida
from app.utils.zone_permissions import get_allowed_zone_ids, require_zone_access, visible_zonas_query

router = APIRouter()
templates = Jinja2Templates(directory="templates")

BASE_DIR = Path(__file__).parent.parent.parent
FOTO_DIR = BASE_DIR / "uploads" / "fotos"
FOTO_DIR.mkdir(parents=True, exist_ok=True)

@router.get("")
@router.get("/")
async def listar_cobros(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse("/auth/login", 302)
    eid = user.empresa_id
    hoy = datetime.date.today()
    allowed_zones = get_allowed_zone_ids(db, user)
    zonas = visible_zonas_query(db, user).all()
    total_q = db.query(func.sum(Cobro.valor_cobrado)).filter(Cobro.empresa_id==eid, Cobro.fecha==hoy)
    num_q = db.query(func.count(Cobro.id)).filter(Cobro.empresa_id==eid, Cobro.fecha==hoy)
    venc_q = db.query(func.count(Cuota.id)).join(Prestamo, Cuota.prestamo_id==Prestamo.id).filter(Cuota.empresa_id==eid, Cuota.estado=="Vencida")
    if allowed_zones is not None:
        total_q = total_q.filter(Cobro.zona_id.in_(allowed_zones or [-1]))
        num_q = num_q.filter(Cobro.zona_id.in_(allowed_zones or [-1]))
        venc_q = venc_q.filter(Prestamo.zona_id.in_(allowed_zones or [-1]))
    total_hoy = total_q.scalar() or 0
    num_hoy = num_q.scalar() or 0
    vencidas = venc_q.scalar() or 0
    return templates.TemplateResponse(request, "cobros.html", {
        "page": "cobros", "current_user": user,
        "cuotas_vencidas_nav": vencidas,
        "zonas": zonas, "total_hoy": total_hoy,
        "num_hoy": num_hoy, "vencidas": vencidas,
    })

@router.get("/buscar-ajax")
async def buscar_cobros(request: Request, q: str="", zona_id: int=None, fecha: str="", db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error":"No autorizado"}, 401)
    eid = user.empresa_id
    allowed_zones = get_allowed_zone_ids(db, user)
    if allowed_zones is not None and zona_id and zona_id not in allowed_zones:
        return JSONResponse({"cobros": [], "total": 0})
    hoy = datetime.date.today()
    fecha_f = datetime.date.fromisoformat(fecha) if fecha else hoy

    query = (db.query(Cobro, Cliente, Cuota)
        .join(Cliente, Cobro.cliente_id==Cliente.id)
        .join(Cuota, Cobro.cuota_id==Cuota.id)
        .filter(Cobro.empresa_id==eid, Cobro.fecha==fecha_f))
    if q:
        query = query.filter(Cliente.nombre.ilike(f"%{q}%")|Cliente.cedula.ilike(f"%{q}%"))
    if zona_id:
        query = query.filter(Cobro.zona_id==zona_id)
    if allowed_zones is not None:
        query = query.filter(Cobro.zona_id.in_(allowed_zones or [-1]))
    rows = query.order_by(Cobro.hora.desc()).limit(200).all()

    return JSONResponse({"cobros": [{
        "id": co.id, "cliente": cl.nombre, "cedula": cl.cedula,
        "valor": float(co.valor_cobrado),
        "metodo": co.metodo_pago or "Efectivo",
        "observaciones": co.observaciones or "",
        "hora": co.hora.strftime("%H:%M") if co.hora else "—",
        "cuota_num": cu.numero,
        "cobrador": co.cobrador or "—",
    } for co, cl, cu in rows], "total": len(rows)})

@router.get("/pendientes-ajax")
async def pendientes(request: Request, zona_id: int=None, q: str="", db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error":"No autorizado"}, 401)
    eid = user.empresa_id
    allowed_zones = get_allowed_zone_ids(db, user)
    if allowed_zones is not None and zona_id and zona_id not in allowed_zones:
        return JSONResponse({"pendientes": []})
    hoy = datetime.date.today()

    query = (db.query(Cuota, Prestamo, Cliente)
        .join(Prestamo, Cuota.prestamo_id==Prestamo.id)
        .join(Cliente, Prestamo.cliente_id==Cliente.id)
        .filter(Cuota.empresa_id==eid,
                Cuota.estado.in_(["Pendiente","Vencida"]),
                Cuota.fecha_vencimiento<=hoy+datetime.timedelta(days=3)))
    if q:
        query = query.filter(Cliente.nombre.ilike(f"%{q}%")|Cliente.cedula.ilike(f"%{q}%"))
    if zona_id:
        query = query.filter(Prestamo.zona_id==zona_id)
    if allowed_zones is not None:
        query = query.filter(Prestamo.zona_id.in_(allowed_zones or [-1]))
    rows = query.order_by(Cuota.fecha_vencimiento).limit(150).all()

    return JSONResponse({"pendientes": [{
        "cuota_id": cu.id, "prestamo_id": p.id, "cliente_id": cl.id,
        "cliente": cl.nombre, "cedula": cl.cedula,
        "telefono": cl.telefono or "", "whatsapp": cl.whatsapp or cl.telefono or "",
        "cuota_num": cu.numero, "total_cuotas": p.num_cuotas,
        "valor": float(cu.valor), "valor_pagado": float(cu.valor_pagado or 0),
        "estado": cu.estado,
        "vencimiento": cu.fecha_vencimiento.strftime("%d/%m/%Y") if cu.fecha_vencimiento else "—",
        "dias": (hoy - cu.fecha_vencimiento).days if cu.fecha_vencimiento else 0,
    } for cu, p, cl in rows]})

@router.post("/registrar")
async def registrar_cobro(
    request: Request,
    cuota_id: int = Form(...),
    valor_cobrado: float = Form(...),
    metodo_pago: str = Form("Efectivo"),
    observaciones: str = Form(""),
    lat: str = Form(""),
    lng: str = Form(""),
    foto: UploadFile = File(None),
    db: Session = Depends(get_db)
):
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error":"No autorizado"}, 401)
    if valor_cobrado <= 0:
        return JSONResponse({"error":"Valor invalido"}, 400)

    cuota = db.query(Cuota).filter(Cuota.id==cuota_id, Cuota.empresa_id==user.empresa_id).with_for_update().first()
    if not cuota:
        return JSONResponse({"error":"Cuota no encontrada"}, 404)

    prestamo = db.query(Prestamo).filter(Prestamo.id==cuota.prestamo_id, Prestamo.empresa_id==user.empresa_id).first()
    if not prestamo:
        return JSONResponse({"error":"Préstamo no encontrado"}, 404)
    if not require_zone_access(db, user, prestamo.zona_id):
        return JSONResponse({"error":"No tienes permisos para esa zona"}, 403)

    cliente  = db.query(Cliente).filter(Cliente.id==prestamo.cliente_id, Cliente.empresa_id==user.empresa_id).first()
    if not cliente:
        return JSONResponse({"error":"Cliente no encontrado"}, 404)

    # Guardar foto si viene
    foto_path = None
    if foto and foto.filename:
        contenido = await foto.read()
        ext, contenido = sanitizar_imagen_subida(foto.filename, contenido)
        nombre = f"{user.empresa_id}_{uuid.uuid4().hex}{ext}"
        ruta = FOTO_DIR / nombre
        ruta.write_bytes(contenido)
        foto_path = nombre

    valor_cobrado_dec = money(valor_cobrado)
    restante = money(cuota.valor) - money(cuota.valor_pagado)
    if restante <= 0:
        return JSONResponse({"error":"La cuota ya esta pagada"}, 400)
    if valor_cobrado_dec > restante:
        return JSONResponse({"error":"El valor supera el saldo de la cuota"}, 400)

    cobro = Cobro(
        empresa_id=user.empresa_id,
        cuota_id=cuota_id,
        prestamo_id=prestamo.id,
        cliente_id=cliente.id,
        zona_id=prestamo.zona_id,
        valor_cobrado=valor_cobrado_dec,
        fecha=datetime.date.today(),
        hora=datetime.datetime.now(),
        cobrador=user.nombre or user.username,
        metodo_pago=(metodo_pago or "Efectivo")[:50],
        observaciones=observaciones[:500] or None,
        usuario_id=user.id,
        lat_cobro=float(lat) if lat.strip() else None,
        lng_cobro=float(lng) if lng.strip() else None,
    )
    db.add(cobro)

    cuota.valor_pagado = money(cuota.valor_pagado) + valor_cobrado_dec
    cuota.fecha_pago = datetime.date.today()
    if cuota.valor_pagado >= cuota.valor:
        cuota.estado = "Pagada"

    cuotas_pend = db.query(Cuota).filter(
        Cuota.prestamo_id==prestamo.id,
        Cuota.estado.in_(["Pendiente","Vencida"])
    ).count()
    if cuotas_pend == 0:
        prestamo.estado = "Pagado"
    elif cuota.estado == "Pagada":
        prestamo.estado = "Activo"

    # Recalcular estado real del préstamo con la función del servicio
    prestamo.estado = get_estado_prestamo(prestamo)

    db.commit()
    return JSONResponse({"ok":True,"mensaje":f"Cobro de ${float(valor_cobrado_dec):,.0f} registrado","cuota_estado":cuota.estado})


@router.post("/registrar-cliente/{cliente_id}")
async def registrar_cobro_cliente_rapido(
    request: Request,
    cliente_id: int,
    metodo_pago: str = Form("Efectivo"),
    db: Session = Depends(get_db)
):
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "No autorizado"}, status_code=401)

    hoy = datetime.date.today()
    query = (db.query(Cuota, Prestamo, Cliente)
        .join(Prestamo, Cuota.prestamo_id == Prestamo.id)
        .join(Cliente, Prestamo.cliente_id == Cliente.id)
        .filter(
            Cliente.id == cliente_id,
            Cliente.empresa_id == user.empresa_id,
            Prestamo.empresa_id == user.empresa_id,
            Cuota.empresa_id == user.empresa_id,
            Cuota.estado.in_(["Pendiente", "Vencida", "Parcial"]),
        ).with_for_update())

    allowed_zones = get_allowed_zone_ids(db, user)
    if allowed_zones is not None:
        query = query.filter(Prestamo.zona_id.in_(allowed_zones or [-1]))

    cuota, prestamo, cliente = query.order_by(Cuota.fecha_vencimiento.asc(), Cuota.numero.asc()).first() or (None, None, None)
    if not cuota:
        return JSONResponse({"error": "Este cliente no tiene cuotas pendientes"}, status_code=404)

    valor_cobrado = money(cuota.valor) - money(cuota.valor_pagado)
    if valor_cobrado <= 0:
        return JSONResponse({"error": "La cuota ya esta pagada"}, status_code=400)

    cobro = Cobro(
        empresa_id=user.empresa_id,
        cuota_id=cuota.id,
        prestamo_id=prestamo.id,
        cliente_id=cliente.id,
        zona_id=prestamo.zona_id,
        valor_cobrado=valor_cobrado,
        fecha=hoy,
        hora=datetime.datetime.now(),
        cobrador=user.nombre or user.username,
        metodo_pago=metodo_pago,
        observaciones="Cobro rapido desde lista de clientes",
        usuario_id=user.id,
    )
    db.add(cobro)

    cuota.valor_pagado = money(cuota.valor_pagado) + valor_cobrado
    cuota.fecha_pago = hoy
    cuota.estado = "Pagada" if cuota.valor_pagado >= cuota.valor else "Parcial"

    cuotas_pend = db.query(Cuota).filter(
        Cuota.prestamo_id == prestamo.id,
        Cuota.estado.in_(["Pendiente", "Vencida", "Parcial"])
    ).count()
    prestamo.estado = "Pagado" if cuotas_pend == 0 else get_estado_prestamo(prestamo)

    db.commit()
    return JSONResponse({
        "ok": True,
        "mensaje": f"Cobro registrado a {cliente.nombre}: ${float(valor_cobrado):,.0f}",
        "cuota_id": cuota.id,
        "valor_cobrado": float(valor_cobrado),
    })
