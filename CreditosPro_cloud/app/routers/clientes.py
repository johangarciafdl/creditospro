from fastapi import APIRouter, Request, Depends, UploadFile, File, Form, HTTPException
from fastapi.responses import JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from pathlib import Path
import shutil, uuid

from app.database import get_db, Cliente, Prestamo, Cuota, Zona
from app.auth import require_login, get_current_empresa

BASE_DIR = Path(__file__).parent.parent.parent
router = APIRouter()
templates = Jinja2Templates(directory="templates")
UPLOAD_DIR = BASE_DIR / "uploads" / "fotos"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


@router.get("/")
async def listar_clientes(request: Request, q: str = "", zona_id: int = None, db: Session = Depends(get_db), empresa_id: int = Depends(get_current_empresa), current_user=Depends(require_login)):
    query = db.query(Cliente).filter(Cliente.activo == True, Cliente.empresa_id == empresa_id)
    if q:
        query = query.filter((Cliente.nombre.contains(q)) | (Cliente.cedula.contains(q)))
    if zona_id:
        query = query.filter(Cliente.zona_id == zona_id)
    clientes = query.order_by(Cliente.nombre).all()

    zonas = db.query(Zona).filter(Zona.empresa_id == empresa_id).all()
    clientes_data = []
    for c in clientes:
        prestamo_activo = db.query(Prestamo).filter(Prestamo.cliente_id == c.id, Prestamo.estado.in_(["Activo", "Atrasado", "Mora"])).first()
        zona = db.query(Zona).filter(Zona.id == c.zona_id).first()
        saldo = 0
        cuota_actual = None
        if prestamo_activo:
            pagado = sum(cu.valor_pagado or 0 for cu in prestamo_activo.cuotas)
            saldo = max(0, prestamo_activo.total_pagar - pagado)
            cuota_actual = next((cu for cu in sorted(prestamo_activo.cuotas, key=lambda x: x.numero) if cu.estado in ["Pendiente", "Vencida"]), None)
        clientes_data.append({
            "id": c.id, "cedula": c.cedula, "nombre": c.nombre,
            "telefono": c.telefono, "whatsapp": c.whatsapp,
            "direccion": c.direccion, "zona": zona.nombre if zona else "—",
            "zona_id": c.zona_id, "tipo_cliente": c.tipo_cliente,
            "foto_path": c.foto_path, "activo": c.activo,
            "prestamo": {
                "id": prestamo_activo.id, "capital": prestamo_activo.capital,
                "total": prestamo_activo.total_pagar,
                "cuotas": f"{(cuota_actual.numero if cuota_actual else 0)}/{prestamo_activo.num_cuotas}",
                "saldo": saldo, "estado": prestamo_activo.estado,
                "progreso": round((cuota_actual.numero - 1 if cuota_actual else prestamo_activo.num_cuotas) / prestamo_activo.num_cuotas * 100, 1),
            } if prestamo_activo else None,
        })

    return templates.TemplateResponse("clientes.html", context={
        "request": request, "page": "clientes",
        "clientes": clientes_data, "zonas": zonas,
        "q": q, "zona_id_sel": zona_id,
        "current_user": current_user,
    })



@router.get("/buscar")
async def buscar_clientes_json(
    q: str = "",
    db: Session = Depends(get_db),
    empresa_id: int = Depends(get_current_empresa),
):
    """Endpoint JSON para autocompletar búsqueda de clientes en modal préstamo."""
    if len(q) < 2:
        return []
    clientes = db.query(Cliente).filter(
        Cliente.activo == True,
        Cliente.empresa_id == empresa_id,
        (Cliente.nombre.contains(q)) | (Cliente.cedula.contains(q))
    ).order_by(Cliente.nombre).limit(10).all()
    return [{"id": c.id, "nombre": c.nombre, "cedula": c.cedula} for c in clientes]

@router.get("/{cliente_id}")
async def detalle_cliente(request: Request, cliente_id: int, db: Session = Depends(get_db), empresa_id: int = Depends(get_current_empresa), current_user=Depends(require_login)):
    cliente = db.query(Cliente).filter(Cliente.id == cliente_id, Cliente.empresa_id == empresa_id).first()
    if not cliente:
        raise HTTPException(status_code=404, detail="Cliente no encontrado")
    zona = db.query(Zona).filter(Zona.id == cliente.zona_id).first()
    prestamos = db.query(Prestamo).filter(Prestamo.cliente_id == cliente_id).order_by(Prestamo.creado.desc()).all()
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
            "cuotas": [{"num": c.numero, "valor": c.valor, "vencimiento": c.fecha_vencimiento, "estado": c.estado, "pagado": c.valor_pagado or 0} for c in sorted(p.cuotas, key=lambda x: x.numero)],
        })

    return templates.TemplateResponse("cliente_detalle.html", context={
        "request": request, "page": "clientes",
        "cliente": cliente, "zona": zona, "zonas": zonas,
        "prestamos": prestamos_data, "current_user": current_user,
    })


@router.post("/nuevo")
async def crear_cliente(
    cedula: str = Form(...), nombre: str = Form(...), telefono: str = Form(...),
    whatsapp: str = Form(""), direccion: str = Form(""), barrio: str = Form(""),
    zona_id: int = Form(...), tipo_cliente: str = Form("Regular"),
    codeudor_nombre: str = Form(""), codeudor_cedula: str = Form(""), codeudor_tel: str = Form(""),
    lat: float = Form(None), lng: float = Form(None),
    foto: UploadFile = File(None),
    db: Session = Depends(get_db), empresa_id: int = Depends(get_current_empresa)
):
    # Validaciones
    cedula = cedula.strip()
    if not cedula or not nombre.strip():
        return JSONResponse({"error": "Cédula y nombre son obligatorios"}, status_code=400)
    if db.query(Cliente).filter(Cliente.cedula == cedula, Cliente.empresa_id == empresa_id).first():
        return JSONResponse({"error": f"Ya existe un cliente con la cédula {cedula}"}, status_code=400)

    foto_path = None
    if foto and foto.filename:
        ext = Path(foto.filename).suffix.lower()
        if ext not in [".jpg", ".jpeg", ".png", ".webp"]:
            return JSONResponse({"error": "Solo se permiten imágenes JPG, PNG o WEBP"}, status_code=400)
        nombre_archivo = f"{uuid.uuid4()}{ext}"
        with open(UPLOAD_DIR / nombre_archivo, "wb") as f:
            shutil.copyfileobj(foto.file, f)
        foto_path = f"fotos/{nombre_archivo}"

    cliente = Cliente(
        empresa_id=empresa_id,
        cedula=cedula, nombre=nombre.strip(), telefono=telefono,
        whatsapp=whatsapp or telefono, direccion=direccion, barrio=barrio,
        zona_id=zona_id, tipo_cliente=tipo_cliente,
        codeudor_nombre=codeudor_nombre or None,
        codeudor_cedula=codeudor_cedula or None,
        codeudor_tel=codeudor_tel or None,
        lat=lat, lng=lng, foto_path=foto_path,
    )
    db.add(cliente)
    db.commit()
    db.refresh(cliente)
    return JSONResponse({"ok": True, "id": cliente.id, "mensaje": "Cliente creado exitosamente"})


@router.post("/{cliente_id}/editar")
async def editar_cliente(
    cliente_id: int,
    nombre: str = Form(...), telefono: str = Form(...), whatsapp: str = Form(""),
    direccion: str = Form(""), zona_id: int = Form(...), tipo_cliente: str = Form("Regular"),
    lat: float = Form(None), lng: float = Form(None),
    foto: UploadFile = File(None),
    db: Session = Depends(get_db), current_user=Depends(require_login)
):
    cliente = db.query(Cliente).filter(Cliente.id == cliente_id).first()
    if not cliente:
        return JSONResponse({"error": "Cliente no encontrado"}, status_code=404)

    cliente.nombre = nombre.strip()
    cliente.telefono = telefono
    cliente.whatsapp = whatsapp or telefono
    cliente.direccion = direccion
    cliente.zona_id = zona_id
    cliente.tipo_cliente = tipo_cliente
    if lat is not None:
        cliente.lat = lat
    if lng is not None:
        cliente.lng = lng

    if foto and foto.filename:
        ext = Path(foto.filename).suffix.lower()
        if ext in [".jpg", ".jpeg", ".png", ".webp"]:
            nombre_archivo = f"{uuid.uuid4()}{ext}"
            with open(UPLOAD_DIR / nombre_archivo, "wb") as f:
                shutil.copyfileobj(foto.file, f)
            cliente.foto_path = f"fotos/{nombre_archivo}"

    db.commit()
    return JSONResponse({"ok": True, "mensaje": "Cliente actualizado correctamente"})


@router.delete("/{cliente_id}")
async def eliminar_cliente(cliente_id: int, db: Session = Depends(get_db), current_user=Depends(require_login)):
    cliente = db.query(Cliente).filter(Cliente.id == cliente_id).first()
    if not cliente:
        raise HTTPException(status_code=404)
    cliente.activo = False
    db.commit()
    return JSONResponse({"ok": True})
