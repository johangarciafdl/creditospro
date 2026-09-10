"""Zonas router v2.1 - multi-tenant"""
from fastapi import APIRouter, Request, Depends, Form, HTTPException
from fastapi.responses import JSONResponse, RedirectResponse
from app.templates import templates
from sqlalchemy.orm import Session
from sqlalchemy import func

import re

from app.database import get_db, Empresa, Zona, Cliente, Prestamo, Cobro, Usuario
from app.routers.auth import get_current_user
from app.utils.plan_limits import tiene_funcion
from app.utils.validators import validar_nombre, limpiar_texto, sin_html
from app.utils.zone_permissions import get_allowed_zone_ids

router = APIRouter()

_PLACA_RE = re.compile(r"^[A-Za-z0-9]{6}$")
_TEL_COBRADOR_RE = re.compile(r"^[0-9]{7,10}$")
_CODIGO_ZONA_RE = re.compile(r"^[A-Za-z0-9_-]{2,20}$")


def _validar_codigo_zona(codigo: str) -> str:
    c = limpiar_texto(codigo, 20).upper()
    if not _CODIGO_ZONA_RE.match(c):
        raise HTTPException(400, "El codigo de zona debe ser alfanumerico, entre 2 y 20 caracteres")
    return c


def _validar_placa(placa: str) -> str | None:
    """Moto/placa del cobrador: exactamente 6 caracteres alfanumericos."""
    p = limpiar_texto(placa, 10).upper()
    if not p:
        return None
    if not _PLACA_RE.match(p):
        raise HTTPException(400, "La placa debe tener exactamente 6 caracteres alfanumericos")
    return p


def _validar_telefono_cobrador(tel: str) -> str | None:
    """Telefono del cobrador: solo digitos, 7 a 10 (celular colombiano = 10).

    OJO: el limite de longitud aqui debe ser mayor que el maximo valido (10)
    -- si se trunca a 10 antes de aplicar la regex, un valor de 11+ digitos
    se recorta a 10 y pasa la validacion en vez de ser rechazado.
    """
    t = limpiar_texto(tel, 20)
    if not t:
        return None
    if not _TEL_COBRADOR_RE.match(t):
        raise HTTPException(400, "El telefono debe tener entre 7 y 10 numeros, sin letras ni simbolos")
    return t


def _validar_cobrador(db: Session, empresa_id: int, cobrador_nombre: str) -> str | None:
    """El cobrador debe ser un empleado activo ya existente de la empresa --
    no texto libre. Se valida por nombre (la relacion sigue siendo un campo
    de texto en Zona, no una FK a Usuario, para no requerir migracion)."""
    nombre = limpiar_texto(cobrador_nombre, 200)
    if not nombre:
        return None
    existe = db.query(Usuario).filter(
        Usuario.empresa_id == empresa_id,
        Usuario.nombre == nombre,
        Usuario.activo == True,
    ).first()
    if not existe:
        raise HTTPException(400, "Selecciona un cobrador de la lista de empleados existentes")
    return nombre


def _empleados_activos(db: Session, empresa_id: int) -> list[dict]:
    usuarios = db.query(Usuario).filter(
        Usuario.empresa_id == empresa_id, Usuario.activo == True
    ).order_by(Usuario.nombre).all()
    return [{"id": u.id, "nombre": u.nombre} for u in usuarios]


@router.get("")
@router.get("/")
async def listar_zonas(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url="/auth/login?next=/zonas", status_code=302)

    eid = user.empresa_id
    allowed_zones = get_allowed_zone_ids(db, user)
    zonas_q = db.query(Zona).filter(Zona.empresa_id == eid)
    if allowed_zones is not None:
        zonas_q = zonas_q.filter(Zona.id.in_(allowed_zones or [-1]))
    zonas = zonas_q.all()

    # 2 consultas agrupadas en vez de 2 por zona (N+1): antes, con 20 zonas
    # esta pantalla hacia 41 consultas; ahora siempre son 3, sin importar
    # cuantas zonas tenga la empresa.
    clientes_por_zona = dict(
        db.query(Cliente.zona_id, func.count(Cliente.id))
        .filter(Cliente.empresa_id == eid, Cliente.activo == True)
        .group_by(Cliente.zona_id).all()
    )
    prestamos_por_zona = dict(
        db.query(Prestamo.zona_id, func.count(Prestamo.id))
        .filter(Prestamo.empresa_id == eid, Prestamo.estado == "Activo")
        .group_by(Prestamo.zona_id).all()
    )

    data = []
    for z in zonas:
        data.append({
            "id": z.id, "codigo": z.codigo, "nombre": z.nombre,
            "ciudad": z.ciudad, "cobrador": z.cobrador_nombre or "—",
            "cobrador_tel": z.cobrador_tel or "—",
            "cobrador_moto": z.cobrador_moto or "—",
            "clientes": clientes_por_zona.get(z.id, 0),
            "prestamos": prestamos_por_zona.get(z.id, 0),
            "activa": z.activa, "lat": z.lat, "lng": z.lng,
        })

    return templates.TemplateResponse(request, "zonas.html", {
        "page": "zonas", "zonas": data, "current_user": user,
        "empleados": _empleados_activos(db, eid),
    })


@router.get("/sync")
async def sync_zonas(request: Request, db: Session = Depends(get_db)):
    """Lista minima (id, nombre) para que la PWA resuelva nombres de zona sin conexion."""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "No autorizado"}, status_code=401)
    allowed_zones = get_allowed_zone_ids(db, user)
    zonas_q = db.query(Zona).filter(Zona.empresa_id == user.empresa_id)
    if allowed_zones is not None:
        zonas_q = zonas_q.filter(Zona.id.in_(allowed_zones or [-1]))
    return JSONResponse([{"id": z.id, "nombre": z.nombre} for z in zonas_q.all()])


@router.post("/nueva")
async def crear_zona(
    request: Request,
    codigo: str = Form(...), nombre: str = Form(...),
    ciudad: str = Form("Medellín"), departamento: str = Form("Antioquia"),
    pais: str = Form("Colombia"), cobrador_nombre: str = Form(""),
    cobrador_tel: str = Form(""), cobrador_moto: str = Form(""),
    lat: float = Form(None), lng: float = Form(None),
    db: Session = Depends(get_db)
):
    user = get_current_user(request, db)
    if not user or user.rol not in ("admin", "superadmin"):
        return JSONResponse({"error": "Sin permisos"}, status_code=403)

    try:
        codigo_limpio = _validar_codigo_zona(codigo)
        nombre = sin_html(nombre, "Nombre de zona")
        ciudad = sin_html(ciudad, "Ciudad", 100) or "Medellín"
        departamento = sin_html(departamento, "Departamento", 100) or "Antioquia"
        pais = sin_html(pais, "País", 100) or "Colombia"
        cobrador_nombre_limpio = _validar_cobrador(db, user.empresa_id, cobrador_nombre)
        cobrador_moto_limpio = _validar_placa(cobrador_moto)
        cobrador_tel_limpio = _validar_telefono_cobrador(cobrador_tel)
        # Si se asigna un cobrador, su telefono y placa dejan de ser opcionales
        # -- un cobrador sin como contactarlo ni identificar su moto no sirve
        # para operar la zona en campo.
        if cobrador_nombre_limpio and not (cobrador_tel_limpio and cobrador_moto_limpio):
            raise HTTPException(400, "Si asignas un cobrador, su telefono y placa/moto son obligatorios")
    except HTTPException as e:
        return JSONResponse({"error": e.detail}, status_code=e.status_code)

    existente = db.query(Zona).filter(
        Zona.empresa_id == user.empresa_id, Zona.codigo == codigo_limpio
    ).first()
    if existente:
        return JSONResponse({"error": "Código de zona ya existe"}, status_code=400)

    zona = Zona(
        empresa_id=user.empresa_id,
        codigo=codigo_limpio, nombre=nombre,
        ciudad=ciudad, departamento=departamento, pais=pais,
        cobrador_nombre=cobrador_nombre_limpio,
        cobrador_tel=cobrador_tel_limpio,
        cobrador_moto=cobrador_moto_limpio,
        lat=lat, lng=lng,
    )
    db.add(zona)
    db.commit()
    return JSONResponse({"ok": True, "mensaje": "Zona creada"})


@router.post("/{zona_id}/editar")
async def editar_zona(
    request: Request, zona_id: int,
    nombre: str = Form(...), cobrador_nombre: str = Form(""),
    cobrador_tel: str = Form(""), cobrador_moto: str = Form(""),
    activa: str = Form("true"),
    bot_phone: str = Form(""), bot_apikey: str = Form(""),
    bot_activo: str = Form("false"),
    db: Session = Depends(get_db)
):
    user = get_current_user(request, db)
    if not user or user.rol not in ("admin", "superadmin"):
        return JSONResponse({"error": "Sin permisos"}, status_code=403)

    zona = db.query(Zona).filter(
        Zona.id == zona_id, Zona.empresa_id == user.empresa_id
    ).first()
    if not zona:
        return JSONResponse({"error": "No encontrado"}, status_code=404)

    try:
        nombre_limpio = sin_html(nombre, "Nombre de zona")
        cobrador_nombre_limpio = _validar_cobrador(db, user.empresa_id, cobrador_nombre)
        cobrador_moto_limpio = _validar_placa(cobrador_moto)
        cobrador_tel_limpio = _validar_telefono_cobrador(cobrador_tel)
        if cobrador_nombre_limpio and not (cobrador_tel_limpio and cobrador_moto_limpio):
            raise HTTPException(400, "Si asignas un cobrador, su telefono y placa/moto son obligatorios")
    except HTTPException as e:
        return JSONResponse({"error": e.detail}, status_code=e.status_code)
    zona.nombre = nombre_limpio
    zona.cobrador_nombre = cobrador_nombre_limpio
    zona.cobrador_moto = cobrador_moto_limpio
    zona.cobrador_tel = cobrador_tel_limpio
    zona.activa = activa.lower() in ("true", "1", "on")
    zona.bot_phone = bot_phone.strip() or None
    zona.bot_apikey = bot_apikey.strip() or None
    bot_activo_nuevo = bot_activo.lower() in ("true", "1", "on")
    if bot_activo_nuevo:
        empresa_plan = db.query(Empresa).filter(Empresa.id == user.empresa_id).first()
        if not empresa_plan or not tiene_funcion(empresa_plan, "whatsapp"):
            return JSONResponse(
                {"error": "Tu plan no incluye WhatsApp automatico. Contacta al proveedor para activarlo."},
                status_code=403,
            )
    zona.bot_activo = bot_activo_nuevo
    db.commit()
    return JSONResponse({"ok": True})
