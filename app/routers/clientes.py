"""Clientes router v2.1 - multi-tenant, fix TemplateResponse"""
from fastapi import APIRouter, Request, Depends, UploadFile, File, Form, HTTPException
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session, joinedload
from pathlib import Path
import shutil, uuid, datetime

from app.database import get_db, Cliente, Prestamo, Cuota, Zona
from app.routers.auth import get_current_user

BASE_DIR = Path(__file__).parent.parent.parent
router = APIRouter()
templates = Jinja2Templates(directory="templates")
UPLOAD_DIR = BASE_DIR / "uploads" / "fotos"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


@router.get("")
@router.get("/")
async def listar_clientes(
    request: Request, q: str = "", zona_id: int = None,
    db: Session = Depends(get_db)
):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url="/auth/login?next=/clientes", status_code=302)

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
    foto: UploadFile = File(None),
    db: Session = Depends(get_db)
):
    user = get_current_user(request, db)
    if not user:
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
        foto_path = f"fotos/{nombre_archivo}"

    cliente = Cliente(
        empresa_id=user.empresa_id,
        cedula=cedula.strip(), nombre=nombre.strip(),
        telefono=telefono.strip(),
        whatsapp=whatsapp.strip() or telefono.strip(),
        direccion=direccion.strip(), barrio=barrio.strip(),
        zona_id=zona_id, tipo_cliente=tipo_cliente,
        codeudor_nombre=codeudor_nombre.strip() or None,
        codeudor_cedula=codeudor_cedula.strip() or None,
        codeudor_tel=codeudor_tel.strip() or None,
        lat=lat, lng=lng, foto_path=foto_path,
    )
    db.add(cliente)
    db.commit()
    db.refresh(cliente)
    return JSONResponse({"ok": True, "id": cliente.id, "mensaje": "Cliente creado"})


@router.post("/{cliente_id}/editar")
async def editar_cliente(
    request: Request, cliente_id: int,
    nombre: str = Form(...), telefono: str = Form(...),
    whatsapp: str = Form(""), direccion: str = Form(""),
    zona_id: int = Form(...), tipo_cliente: str = Form("Regular"),
    lat: float = Form(None), lng: float = Form(None),
    foto: UploadFile = File(None),
    db: Session = Depends(get_db)
):
    user = get_current_user(request, db)
    if not user:
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

    db.commit()
    return JSONResponse({"ok": True, "mensaje": "Cliente actualizado"})


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
