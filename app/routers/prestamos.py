<<<<<<< HEAD
"""
Prestamos router v2.3 - multi-tenant + auth
- Carga instantanea (solo zonas al abrir)
- Busqueda AJAX
- Fix NoneType format
- Validadores centralizados en app.utils.validators
- Proteccion SQL injection via ORM
- Logging mejorado para debugging en producción
"""
import datetime
import logging
from typing import Optional

from fastapi import APIRouter, Request, Depends, Form, HTTPException, Query
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func
=======
"""Prestamos router v2.1 - multi-tenant, fix N+1, fix TemplateResponse"""
from fastapi import APIRouter, Request, Depends, Form, HTTPException
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session, joinedload
import datetime
>>>>>>> 7761f488b2aa6200974f069ea5072699c6dbd1e5

from app.database import get_db, Prestamo, Cliente, Cuota, Zona
from app.routers.auth import get_current_user
from app.services.prestamo_service import calcular_cuotas
<<<<<<< HEAD
from app.utils.money import money
from app.utils.zone_permissions import get_allowed_zone_ids, require_zone_access, visible_zonas_query
from app.utils.validators import (
    validar_numero_positivo, validar_entero_positivo, limpiar_texto
)

# Configurar logging
logger = logging.getLogger(__name__)
=======
>>>>>>> 7761f488b2aa6200974f069ea5072699c6dbd1e5

router = APIRouter()
templates = Jinja2Templates(directory="templates")


<<<<<<< HEAD
# ── GET / — Carga instantanea ────────────────────────────────────────────────
@router.get("")
@router.get("/")
async def listar_prestamos(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url="/auth/login?next=/prestamos", status_code=302)

    allowed_zones = get_allowed_zone_ids(db, user)
    zonas = visible_zonas_query(db, user).all()
    total_q = db.query(func.count(Prestamo.id)).filter(
        Prestamo.empresa_id == user.empresa_id
    )
    if allowed_zones is not None:
        total_q = total_q.filter(Prestamo.zona_id.in_(allowed_zones or [-1]))
    total = total_q.scalar() or 0

    return templates.TemplateResponse(request, "prestamos.html", {
        "page": "prestamos",
        "prestamos": [],
        "zonas": zonas,
        "estado_sel": "",
        "zona_id_sel": None,
        "current_user": user,
        "total_prestamos": total,
    })


# ── GET /buscar-ajax ─────────────────────────────────────────────────────────
@router.get("/buscar-ajax")
async def buscar_ajax(
    request: Request,
    q: str = "",
    estado: str = "",
    zona_id: int = None,
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
=======
@router.get("")
@router.get("/")
async def listar_prestamos(
    request: Request,
    estado: str = "",
    zona_id: int = None,
>>>>>>> 7761f488b2aa6200974f069ea5072699c6dbd1e5
    db: Session = Depends(get_db)
):
    user = get_current_user(request, db)
    if not user:
<<<<<<< HEAD
        return JSONResponse({"error": "No autorizado"}, status_code=401)

    q = limpiar_texto(q, 100)
    estado = limpiar_texto(estado, 30)

    if not q and not estado and not zona_id:
        return JSONResponse({"prestamos": [], "total": 0, "page": page, "per_page": per_page, "total_pages": 0})

    allowed_zones = get_allowed_zone_ids(db, user)
    if allowed_zones is not None and zona_id and zona_id not in allowed_zones:
        return JSONResponse({"prestamos": [], "total": 0, "page": page, "per_page": per_page, "total_pages": 0})

    logger.debug(f"[PRESTAMO-BUSCAR] Búsqueda: q='{q}', estado='{estado}', "
                f"zona_id={zona_id}, usuario={user.username}")

    query = (db.query(Prestamo, Cliente)
        .join(Cliente, Prestamo.cliente_id == Cliente.id)
        .filter(Prestamo.empresa_id == user.empresa_id))
    if allowed_zones is not None:
        query = query.filter(Prestamo.zona_id.in_(allowed_zones or [-1]))

    if q:
        query = query.filter(
            Cliente.nombre.ilike(f"%{q}%") | Cliente.cedula.ilike(f"%{q}%")
        )
    if estado:
        query = query.filter(Prestamo.estado.ilike(f"%{estado}%"))
    if zona_id:
        query = query.filter(Prestamo.zona_id == zona_id)

    total = query.count()
    total_pages = (total + per_page - 1) // per_page
    offset = (page - 1) * per_page

    rows = query.order_by(Prestamo.creado.desc()).offset(offset).limit(per_page).all()
    zonas_dict = {z.id: z.nombre for z in db.query(Zona).filter(Zona.empresa_id == user.empresa_id).all()}

    result = []
    for p, c in rows:
        result.append({
            "id": p.id,
            "cliente": c.nombre,
            "cedula": c.cedula,
            "cliente_id": c.id,
            "capital": float(p.capital or 0),
            "total": float(p.total_pagar or p.capital or 0),
            "saldo": float(p.total_pagar or p.capital or 0),
            "num_cuotas": p.num_cuotas or 0,
            "valor_cuota": float(p.valor_cuota or 0),
            "estado": p.estado or "Activo",
            "zona": zonas_dict.get(p.zona_id, "—"),
            "fecha_inicio": p.fecha_inicio.strftime("%d/%m/%Y") if p.fecha_inicio else "—",
            "fecha_fin": p.fecha_fin.strftime("%d/%m/%Y") if p.fecha_fin else "—",
            "tipo_cliente": c.tipo_cliente or "Regular",
        })

    return JSONResponse({
        "prestamos": result,
        "total": total,
        "page": page,
        "per_page": per_page,
        "total_pages": total_pages,
    })


# ── GET /calcular — Preview calculo ─────────────────────────────────────────
@router.get("/calcular")
async def calcular_preview(
    capital: float,
    tasa: float,
    cuotas: int,
    plazo: int = 1
):
    capital = validar_numero_positivo(capital, "capital")
    tasa = validar_numero_positivo(tasa, "tasa", minimo=0, maximo=200)
    cuotas = validar_entero_positivo(cuotas, "cuotas", minimo=1, maximo=365)
    plazo = validar_entero_positivo(plazo, "plazo", minimo=1, maximo=365)
    calc = calcular_cuotas(capital, tasa, cuotas, datetime.date.today(), plazo)
    return {
        "interes_total": float(calc.get("interes_total") or 0),
        "total_pagar": float(calc.get("total_pagar") or 0),
        "valor_cuota": float(calc.get("valor_cuota") or 0),
    }


# ── POST /nuevo — Crear prestamo ─────────────────────────────────────────────
@router.post("/nuevo")
async def crear_prestamo(
    request: Request,
    cliente_id: str = Form(...),
    zona_id: str = Form(...),
    capital: float = Form(...),
    tasa_interes: float = Form(20.0),
    num_cuotas: int = Form(...),
    plazo_dias: int = Form(1),
    fecha_inicio: str = Form(...),
=======
        return RedirectResponse(url="/auth/login?next=/prestamos", status_code=302)

    # FIX N+1: eager load cliente y cuotas en una sola query
    query = db.query(Prestamo).options(
        joinedload(Prestamo.cliente),
        joinedload(Prestamo.cuotas)
    ).filter(Prestamo.empresa_id == user.empresa_id)

    if estado:
        query = query.filter(Prestamo.estado == estado)
    if zona_id:
        query = query.filter(Prestamo.zona_id == zona_id)
    elif user.rol == "cobrador" and user.zona_id:
        query = query.filter(Prestamo.zona_id == user.zona_id)

    prestamos = query.order_by(Prestamo.creado.desc()).all()

    # Cargar zonas una vez
    zonas_map = {z.id: z for z in db.query(Zona).filter(Zona.empresa_id == user.empresa_id).all()}

    data = []
    for p in prestamos:
        cliente = p.cliente
        zona = zonas_map.get(p.zona_id)
        # FIX: valor_pagado nunca None (default 0.0 en DB)
        pagado = sum(c.valor_pagado for c in p.cuotas)
        saldo = max(0.0, (p.total_pagar or 0) - pagado)
        vencidas = sum(1 for c in p.cuotas if c.estado == "Vencida")
        prox = next((c for c in sorted(p.cuotas, key=lambda x: x.numero)
                     if c.estado in ("Pendiente", "Vencida")), None)
        data.append({
            "id": p.id,
            "cliente": cliente.nombre if cliente else "—",
            "cedula": cliente.cedula if cliente else "—",
            "capital": p.capital, "total": p.total_pagar,
            "saldo": saldo, "pagado": pagado,
            "num_cuotas": p.num_cuotas, "valor_cuota": p.valor_cuota,
            "cuota_actual": prox.numero if prox else "—",
            "vencidas": vencidas, "estado": p.estado,
            "zona": zona.nombre if zona else "—",
            "fecha_inicio": p.fecha_inicio.strftime("%d/%m/%Y") if p.fecha_inicio else "—",
            "fecha_fin": p.fecha_fin.strftime("%d/%m/%Y") if p.fecha_fin else "—",
            "tipo_cliente": cliente.tipo_cliente if cliente else "—",
        })

    return templates.TemplateResponse(request, "prestamos.html", {
        "page": "prestamos",
        "prestamos": data,
        "zonas": list(zonas_map.values()),
        "estado_sel": estado,
        "zona_id_sel": zona_id,
        "current_user": user,
    })


@router.post("/nuevo")
async def crear_prestamo(
    request: Request,
    cliente_id: int = Form(...),
    zona_id: int = Form(...),
    capital: float = Form(...),
    tasa_interes: float = Form(20.0),
    num_cuotas: int = Form(...),
    plazo_dias: int = Form(30),
    fecha_inicio: str = Form(""),
    cobrador: str = Form(""),
>>>>>>> 7761f488b2aa6200974f069ea5072699c6dbd1e5
    observaciones: str = Form(""),
    db: Session = Depends(get_db)
):
    user = get_current_user(request, db)
    if not user:
<<<<<<< HEAD
        return JSONResponse({"error": "No autorizado"}, status_code=401)

    # Validar IDs
    cliente_id_int = validar_entero_positivo(cliente_id, "Cliente")
    zona_id_int = validar_entero_positivo(zona_id, "Zona")

    # Validar rangos
    capital = validar_numero_positivo(capital, "capital", maximo=100_000_000)
    tasa_interes = validar_numero_positivo(tasa_interes, "tasa de interés", minimo=0, maximo=200)
    num_cuotas = validar_entero_positivo(num_cuotas, "cuotas", minimo=1, maximo=365)
    plazo_dias = validar_entero_positivo(plazo_dias, "plazo", minimo=1, maximo=365)

    # Verificar cliente pertenece a empresa (aislamiento multi-tenant)
    cliente = db.query(Cliente).filter(
        Cliente.id == cliente_id_int,
=======
        return JSONResponse({"error": "No autenticado"}, status_code=401)

    cliente = db.query(Cliente).filter(
        Cliente.id == cliente_id,
>>>>>>> 7761f488b2aa6200974f069ea5072699c6dbd1e5
        Cliente.empresa_id == user.empresa_id
    ).first()
    if not cliente:
        return JSONResponse({"error": "Cliente no encontrado"}, status_code=404)
<<<<<<< HEAD
    if not require_zone_access(db, user, cliente.zona_id):
        return JSONResponse({"error": "No tienes permisos para este cliente"}, status_code=403)

    zona = db.query(Zona).filter(
        Zona.id == zona_id_int,
        Zona.empresa_id == user.empresa_id
    ).first()
    if not zona:
        return JSONResponse({"error": "Zona no encontrada"}, status_code=404)
    if not require_zone_access(db, user, zona_id_int):
        return JSONResponse({"error": "No tienes permisos para esa zona"}, status_code=403)

    # Validar y parsear fecha
    try:
        if isinstance(fecha_inicio, str):
            # Intenta múltiples formatos comunes
            for fmt in ["%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"]:
                try:
                    fecha = datetime.datetime.strptime(fecha_inicio, fmt).date()
                    break
                except ValueError:
                    continue
            else:
                return JSONResponse({"error": "Formato de fecha inválido. Use YYYY-MM-DD"}, status_code=400)
        else:
            fecha = fecha_inicio
    except Exception as e:
        return JSONResponse({"error": f"Error al procesar fecha: {str(e)}"}, status_code=400)

    # Validar que la zona sea válida y activa
    if not zona.activa:
        return JSONResponse({"error": "Zona inactiva no puede recibir préstamos"}, status_code=400)

    observaciones = limpiar_texto(observaciones, 500)

    try:
        # Log: Inicio de creación
        logger.info(f"[PRESTAMO-CREAR] Iniciando creación para cliente_id={cliente_id_int}, "
                   f"capital=${capital}, cuotas={num_cuotas}, usuario={user.username}")
        
        # Calcular cuotas
        calc = calcular_cuotas(capital, tasa_interes, num_cuotas, fecha, plazo_dias)
        logger.debug(f"[PRESTAMO-CREAR] Cálculo exitoso: interés=${calc.get('interes_total')}, "
                    f"total=${calc.get('total_pagar')}, cuota=${calc.get('valor_cuota')}")
        
        # Crear préstamo
        prestamo = Prestamo(
            empresa_id=user.empresa_id,
            cliente_id=cliente_id_int,
            zona_id=zona_id_int,
            capital=capital,
            tasa_interes=tasa_interes,
            interes_total=money(calc.get("interes_total")),
            total_pagar=money(calc.get("total_pagar")),
            num_cuotas=int(num_cuotas),
            valor_cuota=money(calc.get("valor_cuota")),
            plazo_dias=int(plazo_dias),
            fecha_inicio=fecha,
            fecha_fin=calc.get("fecha_fin"),
            cobrador=user.nombre or user.username,
            observaciones=observaciones or None,
            estado="Activo",
        )
        db.add(prestamo)
        db.flush()  # Obtener ID del préstamo sin commitear aún
        logger.debug(f"[PRESTAMO-CREAR] Préstamo guardado en BD con ID={prestamo.id}")

        # Crear cuotas
        num_cuotas_creadas = 0
        for c in calc.get("cuotas", []):
            cuota = Cuota(
                empresa_id=user.empresa_id,
                prestamo_id=prestamo.id,
                numero=int(c["numero"]),
                valor=money(c.get("valor")),
                fecha_vencimiento=c["fecha_vencimiento"],
                estado="Pendiente",
            )
            db.add(cuota)
            num_cuotas_creadas += 1

        # Commit transacción
        db.commit()
        db.refresh(prestamo)
        
        logger.info(f"[PRESTAMO-CREAR] ✅ Éxito: Préstamo #{prestamo.id} creado con "
                   f"{num_cuotas_creadas} cuotas para {cliente.nombre}")
        
        return JSONResponse({
            "ok": True, 
            "id": prestamo.id, 
            "mensaje": f"Préstamo #{prestamo.id} creado exitosamente para {cliente.nombre}"
        })
    except Exception as e:
        db.rollback()
        import traceback
        error_detail = traceback.format_exc()
        
        # Log del error
        logger.error(f"[PRESTAMO-CREAR] ❌ Error: {str(e)}", extra={
            'cliente_id': cliente_id_int,
            'capital': capital,
            'usuario': user.username,
            'exception': error_detail
        })
        
        return JSONResponse({
            "error": f"Error al crear préstamo: {str(e)}",
            "detail": error_detail
        }, status_code=500)


# ── Sync endpoints para PWA (offline-first) ──────────────────────────────────
@router.get("/sync")
async def sync_prestamos(request: Request, db: Session = Depends(get_db)):
    """Retorna todos los prestamos activos/atrasados para sincronización offline."""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "No autorizado"}, status_code=401)
    prestamos = db.query(Prestamo).filter(
        Prestamo.empresa_id == user.empresa_id,
        Prestamo.estado.in_(["Activo", "Atrasado"])
    ).limit(2000).all()
    return JSONResponse([{
        "id": p.id, "cliente_id": p.cliente_id,
        "capital": float(p.capital or 0),
        "total_pagar": float(p.total_pagar or p.capital or 0),
        "num_cuotas": p.num_cuotas or 0,
        "valor_cuota": float(p.valor_cuota or 0),
        "estado": p.estado or "Activo",
        "fecha_inicio": p.fecha_inicio.isoformat() if p.fecha_inicio else None,
    } for p in prestamos])


@router.get("/sync/cuotas")
async def sync_cuotas(request: Request, db: Session = Depends(get_db)):
    """Retorna todas las cuotas pendientes para sincronización offline."""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "No autorizado"}, status_code=401)
    cuotas = db.query(Cuota).filter(
        Cuota.empresa_id == user.empresa_id,
        Cuota.estado == "Pendiente"
    ).limit(5000).all()
    return JSONResponse([{
        "id": c.id, "prestamo_id": c.prestamo_id,
        "numero": c.numero,
        "valor": float(c.valor or 0),
        "fecha_vencimiento": c.fecha_vencimiento.isoformat() if c.fecha_vencimiento else None,
        "estado": c.estado or "Pendiente",
    } for c in cuotas])
=======

    if capital <= 0:
        return JSONResponse({"error": "Capital inválido"}, status_code=400)
    if num_cuotas <= 0:
        return JSONResponse({"error": "Número de cuotas inválido"}, status_code=400)

    fecha = datetime.date.fromisoformat(fecha_inicio) if fecha_inicio else datetime.date.today()
    calc = calcular_cuotas(capital, tasa_interes, num_cuotas, fecha, plazo_dias)

    prestamo = Prestamo(
        empresa_id=user.empresa_id,
        cliente_id=cliente_id, zona_id=zona_id,
        capital=capital, tasa_interes=tasa_interes,
        interes_total=calc["interes_total"], total_pagar=calc["total_pagar"],
        num_cuotas=num_cuotas, valor_cuota=calc["valor_cuota"],
        plazo_dias=plazo_dias, fecha_inicio=fecha, fecha_fin=calc["fecha_fin"],
        cobrador=cobrador or user.nombre, observaciones=observaciones,
        estado="Activo",
    )
    db.add(prestamo)
    db.flush()

    for c in calc["cuotas"]:
        db.add(Cuota(
            empresa_id=user.empresa_id,
            prestamo_id=prestamo.id,
            numero=c["numero"], valor=c["valor"],
            fecha_vencimiento=c["fecha_vencimiento"],
            estado="Pendiente", valor_pagado=0.0,
        ))

    db.commit()
    return JSONResponse({"ok": True, "id": prestamo.id, "mensaje": "Préstamo registrado"})


@router.get("/calcular")
async def calcular_preview(capital: float, tasa: float, cuotas: int, plazo: int = 30):
    calc = calcular_cuotas(capital, tasa, cuotas, datetime.date.today(), plazo)
    return {
        "interes_total": calc["interes_total"],
        "total_pagar": calc["total_pagar"],
        "valor_cuota": calc["valor_cuota"],
    }
>>>>>>> 7761f488b2aa6200974f069ea5072699c6dbd1e5
