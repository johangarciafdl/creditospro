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
from app.templates import templates
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func

from app.database import get_db, Prestamo, Cliente, Cuota, Zona
from app.routers.auth import get_current_user
from app.services.prestamo_service import calcular_cuotas
from app.utils.money import money
from app.utils.zone_permissions import get_allowed_zone_ids, require_zone_access, visible_zonas_query
from app.utils.validators import (
    validar_numero_positivo, validar_entero_positivo, limpiar_texto, sin_html
)

# Ventana para considerar dos prestamos identicos como la misma peticion
# repetida (doble clic / reintento), no como dos prestamos distintos.
VENTANA_DEDUP_SEGUNDOS = 25

# Configurar logging
logger = logging.getLogger(__name__)

router = APIRouter()


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
    db: Session = Depends(get_db)
):
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "No autorizado"}, status_code=401)

    q = limpiar_texto(q, 100)
    estado = limpiar_texto(estado, 30)

    # Sin filtros se muestran los prestamos mas recientes (paginados, 20 por
    # pagina). Antes se devolvia una lista vacia para no traer todo de golpe,
    # pero el resultado era una pantalla en blanco al entrar a Prestamos, como
    # si la empresa no tuviera ninguno. La paginacion ya acota la consulta.
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
    try:
        capital = validar_numero_positivo(capital, "capital")
        tasa = validar_numero_positivo(tasa, "tasa", minimo=0, maximo=200)
        cuotas = validar_entero_positivo(cuotas, "cuotas", minimo=1, maximo=365)
        plazo = validar_entero_positivo(plazo, "plazo", minimo=1, maximo=365)
    except HTTPException as e:
        return JSONResponse({"error": e.detail}, status_code=e.status_code)
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
    observaciones: str = Form(""),
    db: Session = Depends(get_db)
):
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "No autorizado"}, status_code=401)

    # Validar IDs y rangos
    try:
        cliente_id_int = validar_entero_positivo(cliente_id, "Cliente")
        zona_id_int = validar_entero_positivo(zona_id, "Zona")
        capital = validar_numero_positivo(capital, "capital", maximo=100_000_000)
        tasa_interes = validar_numero_positivo(tasa_interes, "tasa de interés", minimo=0, maximo=200)
        num_cuotas = validar_entero_positivo(num_cuotas, "cuotas", minimo=1, maximo=365)
        plazo_dias = validar_entero_positivo(plazo_dias, "plazo", minimo=1, maximo=365)
    except HTTPException as e:
        return JSONResponse({"error": e.detail}, status_code=e.status_code)

    # Verificar cliente pertenece a empresa (aislamiento multi-tenant)
    cliente = db.query(Cliente).filter(
        Cliente.id == cliente_id_int,
        Cliente.empresa_id == user.empresa_id
    ).first()
    if not cliente:
        return JSONResponse({"error": "Cliente no encontrado"}, status_code=404)
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

    try:
        observaciones = sin_html(observaciones, "Observaciones", 500)
    except HTTPException as e:
        return JSONResponse({"error": e.detail}, status_code=e.status_code)

    # Idempotencia: red de seguridad contra el doble clic (y contra un reintento
    # del navegador si la respuesta se perdio). Un prestamo identico al mismo
    # cliente, por el mismo monto y el mismo dia, creado hace segundos, no es
    # un prestamo nuevo -- es la misma peticion repetida. Se devuelve el que ya
    # existe en vez de crear otro. El bloqueo del boton en el frontend es la
    # primera linea; esto cubre a cualquier cliente que no sea el navegador.
    hace_poco = datetime.datetime.now() - datetime.timedelta(seconds=VENTANA_DEDUP_SEGUNDOS)
    duplicado = db.query(Prestamo).filter(
        Prestamo.empresa_id == user.empresa_id,
        Prestamo.cliente_id == cliente_id_int,
        Prestamo.capital == capital,
        Prestamo.num_cuotas == int(num_cuotas),
        Prestamo.fecha_inicio == fecha,
        Prestamo.creado >= hace_poco,
    ).order_by(Prestamo.id.desc()).first()
    if duplicado:
        logger.warning(
            "[PRESTAMO-CREAR] Peticion duplicada ignorada: ya existe el prestamo %s "
            "(cliente=%s, capital=%s) creado hace menos de %ss",
            duplicado.id, cliente_id_int, capital, VENTANA_DEDUP_SEGUNDOS,
        )
        return JSONResponse({
            "ok": True, "id": duplicado.id, "duplicado": True,
            "mensaje": f"Ese préstamo ya se había creado (#{duplicado.id}) — no se duplicó.",
        })

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
        logger.exception(
            "[PRESTAMO-CREAR] Error creando prestamo",
            extra={
                "cliente_id": cliente_id_int,
                "capital": capital,
                "usuario": user.username,
            },
        )
        return JSONResponse(
            {"error": "No se pudo crear el prestamo. Revisa los datos e intenta nuevamente."},
            status_code=500,
        )


# ── Sync endpoints para PWA (offline-first) ──────────────────────────────────
@router.get("/sync")
async def sync_prestamos(request: Request, db: Session = Depends(get_db)):
    """Retorna todos los prestamos activos/atrasados para sincronización offline."""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "No autorizado"}, status_code=401)
    allowed_zones = get_allowed_zone_ids(db, user)
    prestamos = db.query(Prestamo).filter(
        Prestamo.empresa_id == user.empresa_id,
        Prestamo.estado.in_(["Activo", "Atrasado"])
    )
    if allowed_zones is not None:
        prestamos = prestamos.filter(Prestamo.zona_id.in_(allowed_zones or [-1]))
    prestamos = prestamos.limit(2000).all()
    return JSONResponse([{
        "id": p.id, "cliente_id": p.cliente_id, "zona_id": p.zona_id,
        "capital": float(p.capital or 0),
        "total_pagar": float(p.total_pagar or p.capital or 0),
        "num_cuotas": p.num_cuotas or 0,
        "valor_cuota": float(p.valor_cuota or 0),
        "estado": p.estado or "Activo",
        "fecha_inicio": p.fecha_inicio.isoformat() if p.fecha_inicio else None,
    } for p in prestamos])


@router.get("/sync/cuotas")
async def sync_cuotas(request: Request, db: Session = Depends(get_db)):
    """Retorna todas las cuotas pendientes/vencidas/parciales para sincronización offline.

    Incluye Vencida y Parcial ademas de Pendiente: son justo las que un
    cobrador sin señal necesita ver para saber a quien cobrar.
    """
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "No autorizado"}, status_code=401)
    allowed_zones = get_allowed_zone_ids(db, user)
    cuotas = db.query(Cuota).join(Prestamo, Cuota.prestamo_id == Prestamo.id).filter(
        Cuota.empresa_id == user.empresa_id,
        Prestamo.empresa_id == user.empresa_id,
        Cuota.estado.in_(["Pendiente", "Vencida", "Parcial"])
    )
    if allowed_zones is not None:
        cuotas = cuotas.filter(Prestamo.zona_id.in_(allowed_zones or [-1]))
    cuotas = cuotas.limit(5000).all()
    return JSONResponse([{
        "id": c.id, "prestamo_id": c.prestamo_id,
        "numero": c.numero,
        "valor": float(c.valor or 0),
        # Sin valor_pagado el celular no puede calcular el saldo: cobraba el
        # valor completo de una cuota parcial y el servidor rechazaba el envio
        # con "El valor supera el saldo de la cuota" al recuperar señal.
        "valor_pagado": float(c.valor_pagado or 0),
        "fecha_vencimiento": c.fecha_vencimiento.isoformat() if c.fecha_vencimiento else None,
        "estado": c.estado or "Pendiente",
    } for c in cuotas])
