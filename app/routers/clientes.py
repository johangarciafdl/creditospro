"""Clientes router - FIXED"""
from fastapi import APIRouter, Request, Depends, UploadFile, File, Form, HTTPException
from fastapi.responses import JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from pathlib import Path
import shutil, uuid

from app.database import get_db, Cliente, Prestamo, Cuota, Zona
from app.auth import require_login, get_current_empresa

router = APIRouter()
templates = Jinja2Templates(directory="templates")
BASE_DIR = Path(__file__).parent.parent.parent
UPLOAD_DIR = BASE_DIR / "uploads" / "fotos"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


@router.get("/")
async def listar_clientes(
    request: Request,
    q: str = "",
    zona_id: int = None,
    page: int = 1,
    db: Session = Depends(get_db),
    empresa_id: int = Depends(get_current_empresa),
    current_user=Depends(require_login)
):
    POR_PAGINA = 50
    zonas = db.query(Zona).filter(Zona.empresa_id == empresa_id).all()
    zonas_dict = {z.id: z.nombre for z in zonas}

    # Query base
    query = db.query(Cliente).filter(Cliente.activo == True, Cliente.empresa_id == empresa_id)
    if q:
        query = query.filter((Cliente.nombre.ilike(f"%{q}%")) | (Cliente.cedula.ilike(f"%{q}%")))
    if zona_id:
        query = query.filter(Cliente.zona_id == zona_id)

    total = query.count()
    total_paginas = max(1, (total + POR_PAGINA - 1) // POR_PAGINA)
    page = max(1, min(page, total_paginas))
    clientes = query.order_by(Cliente.nombre).offset((page - 1) * POR_PAGINA).limit(POR_PAGINA).all()

    # Un solo query para préstamos activos de estos clientes
    ids = [c.id for c in clientes]
    prestamos_activos = {}
    if ids:
        for p in db.query(Prestamo).filter(
            Prestamo.cliente_id.in_(ids),
            Prestamo.empresa_id == empresa_id,
            Prestamo.estado.in_(["activo", "Activo", "atrasado", "Atrasado"])
        ).all():
            if p.cliente_id not in prestamos_activos:
                prestamos_activos[p.cliente_id] = p

    clientes_data = []
    for c in clientes:
        p = prestamos_activos.get(c.id)
        clientes_data.append({
            "id": c.id, "cedula": c.cedula, "nombre": c.nombre,
            "telefono": c.telefono, "whatsapp": c.whatsapp,
            "direccion": c.direccion,
            "zona": zonas_dict.get(c.zona_id, "—"),
            "zona_id": c.zona_id, "tipo_cliente": c.tipo_cliente,
            "foto_path": c.foto_path, "activo": c.activo,
            "prestamo": {
                "id": p.id,
                "capital": p.capital,
                "total": p.total_pagar or p.capital,
                "cuotas": f"0/{p.num_cuotas}",
                "saldo": p.saldo_pendiente or p.capital,
                "estado": p.estado,
            } if p else None,
        })

    return templates.TemplateResponse("clientes.html", {
        "request": request, "page_name": "clientes",
        "clientes": clientes_data, "zonas": zonas,
        "q": q, "zona_id_sel": zona_id,
        "current_user": current_user,
        "page": page, "total_paginas": total_paginas, "total": total,
    })


@router.get("/buscar")
async def buscar_clientes_json(
    q: str = "",
    db: Session = Depends(get_db),
    empresa_id: int = Depends(get_current_empresa),
):
    if len(q) < 2:
        return []
    clientes = db.query(Cliente).filter(
        Cliente.activo == True,
        Cliente.empresa_id == empresa_id,
        (Cliente.nombre.contains(q)) | (Cliente.cedula.contains(q))
    ).order_by(Cliente.nombre).limit(10).all()
    return [{"id": c.id, "nombre": c.nombre, "cedula": c.cedula} for c in clientes]


@router.get("/{cliente_id}")
async def detalle_cliente(
    request: Request,
    cliente_id: int,
    db: Session = Depends(get_db),
    empresa_id: int = Depends(get_current_empresa),
    current_user=Depends(require_login)
):
    cliente = db.query(Cliente).filter(
        Cliente.id == cliente_id, Cliente.empresa_id == empresa_id
    ).first()
    if not cliente:
        raise HTTPException(status_code=404, detail="Cliente no encontrado")
    zona = db.query(Zona).filter(Zona.id == cliente.zona_id).first()
    prestamos = db.query(Prestamo).filter(
        Prestamo.cliente_id == cliente_id
    ).order_by(Prestamo.creado.desc()).all()
    zonas = db.query(Zona).filter(Zona.empresa_id == empresa_id).all()

    prestamos_data = []
    for p in prestamos:
        pagado = sum(c.valor_pagado or 0 for c in p.cuotas)
        saldo = max(0, p.total_pagar - pagado)
        vencidas = sum(1 for c in p.cuotas if c.estado == "Vencida")
        prestamos_data.append({
            "id": p.id, "capital": p.capital, "total": p.total_pagar,
            "saldo": saldo, "num_cuotas": p.num_cuotas,
            "pagado": pagado, "vencidas": vencidas,
            "estado": p.estado, "fecha_inicio": p.fecha_inicio,
            "cuotas": [{
                "num": c.numero, "valor": c.valor,
                "vencimiento": c.fecha_vencimiento,
                "estado": c.estado, "pagado": c.valor_pagado or 0
            } for c in sorted(p.cuotas, key=lambda x: x.numero)],
        })

    return templates.TemplateResponse("cliente_detalle.html", {
        "request": request, "page": "clientes",
        "cliente": cliente, "zona": zona, "zonas": zonas,
        "prestamos": prestamos_data, "current_user": current_user,
    })


@router.post("/nuevo")
async def crear_cliente(
    cedula: str = Form(...),
    nombre: str = Form(...),
    telefono: str = Form(...),
    whatsapp: str = Form(""),
    direccion: str = Form(""),
    barrio: str = Form(""),
    zona_id: str = Form(""),
    tipo_cliente: str = Form("Regular"),
    codeudor_nombre: str = Form(""),
    codeudor_cedula: str = Form(""),
    codeudor_tel: str = Form(""),
    lat: str = Form(""),
    lng: str = Form(""),
    foto: UploadFile = File(None),
    db: Session = Depends(get_db),
    empresa_id: int = Depends(get_current_empresa),
    current_user=Depends(require_login)
):
    cedula = cedula.strip()
    nombre = nombre.strip()

    if not cedula or not nombre:
        return JSONResponse({"error": "Cedula y nombre son obligatorios"}, status_code=400)

    if not zona_id or not zona_id.strip():
        return JSONResponse({"error": "Debes seleccionar una zona"}, status_code=400)

    try:
        zona_id_int = int(zona_id)
    except ValueError:
        return JSONResponse({"error": "Zona invalida"}, status_code=400)

    if db.query(Cliente).filter(
        Cliente.cedula == cedula, Cliente.empresa_id == empresa_id
    ).first():
        return JSONResponse({"error": f"Ya existe un cliente con cedula {cedula}"}, status_code=400)

    foto_path = None
    if foto and foto.filename:
        ext = Path(foto.filename).suffix.lower()
        if ext in [".jpg", ".jpeg", ".png", ".webp"]:
            nombre_archivo = f"{uuid.uuid4()}{ext}"
            with open(UPLOAD_DIR / nombre_archivo, "wb") as f:
                shutil.copyfileobj(foto.file, f)
            foto_path = f"fotos/{nombre_archivo}"

    try:
        cliente = Cliente(
            empresa_id=empresa_id,
            cedula=cedula,
            nombre=nombre,
            telefono=telefono.strip(),
            whatsapp=whatsapp.strip() or telefono.strip(),
            direccion=direccion.strip(),
            barrio=barrio.strip(),
            zona_id=zona_id_int,
            tipo_cliente=tipo_cliente,
            codeudor_nombre=codeudor_nombre.strip() or None,
            codeudor_cedula=codeudor_cedula.strip() or None,
            codeudor_tel=codeudor_tel.strip() or None,
            lat=float(lat) if lat and lat.strip() else None,
            lng=float(lng) if lng and lng.strip() else None,
            foto_path=foto_path,
        )
        db.add(cliente)
        db.commit()
        db.refresh(cliente)
        return JSONResponse({"ok": True, "id": cliente.id, "mensaje": "Cliente creado exitosamente"})
    except Exception as e:
        db.rollback()
        return JSONResponse({"error": f"Error al guardar: {str(e)}"}, status_code=500)


@router.post("/{cliente_id}/editar")
async def editar_cliente(
    cliente_id: int,
    nombre: str = Form(...),
    telefono: str = Form(...),
    whatsapp: str = Form(""),
    direccion: str = Form(""),
    zona_id: str = Form(""),
    tipo_cliente: str = Form("Regular"),
    lat: str = Form(""),
    lng: str = Form(""),
    foto: UploadFile = File(None),
    db: Session = Depends(get_db),
    empresa_id: int = Depends(get_current_empresa),
    current_user=Depends(require_login)
):
    cliente = db.query(Cliente).filter(
        Cliente.id == cliente_id, Cliente.empresa_id == empresa_id
    ).first()
    if not cliente:
        return JSONResponse({"error": "Cliente no encontrado"}, status_code=404)

    cliente.nombre = nombre.strip()
    cliente.telefono = telefono.strip()
    cliente.whatsapp = whatsapp.strip() or telefono.strip()
    cliente.direccion = direccion.strip()
    cliente.tipo_cliente = tipo_cliente
    if zona_id and zona_id.strip():
        cliente.zona_id = int(zona_id)
    if lat and lat.strip():
        cliente.lat = float(lat)
    if lng and lng.strip():
        cliente.lng = float(lng)

    if foto and foto.filename:
        ext = Path(foto.filename).suffix.lower()
        if ext in [".jpg", ".jpeg", ".png", ".webp"]:
            nombre_archivo = f"{uuid.uuid4()}{ext}"
            with open(UPLOAD_DIR / nombre_archivo, "wb") as f:
                shutil.copyfileobj(foto.file, f)
            cliente.foto_path = f"fotos/{nombre_archivo}"

    db.commit()
    return JSONResponse({"ok": True, "mensaje": "Cliente actualizado"})


@router.delete("/{cliente_id}")
async def eliminar_cliente(
    cliente_id: int,
    db: Session = Depends(get_db),
    empresa_id: int = Depends(get_current_empresa),
    current_user=Depends(require_login)
):
    cliente = db.query(Cliente).filter(
        Cliente.id == cliente_id, Cliente.empresa_id == empresa_id
    ).first()
    if not cliente:
        raise HTTPException(status_code=404)
    cliente.activo = False
    db.commit()
    return JSONResponse({"ok": True})