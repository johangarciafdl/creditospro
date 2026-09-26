from fastapi import APIRouter, Request, Depends, Form, UploadFile, File, HTTPException
from fastapi.responses import JSONResponse, RedirectResponse
from app.templates import templates
from sqlalchemy.orm import Session
from sqlalchemy import func, update
from decimal import Decimal
import datetime
import logging
import uuid
from pathlib import Path

from app.database import (
    get_db, Cobro, Cuota, NoPago, Prestamo, Cliente, Zona, IS_SQLITE,
    dia_semana_local, hoy_local,
)
from app.routers.auth import get_current_user
from app.services.prestamo_service import get_estado_prestamo
from app.utils.audit import log_action
from app.utils.interfaz import redirigir_a_vista_simple
from app.utils.money import cop, money, money_int
from app.utils.almacen_imagenes import guardar_imagen
from app.utils.validators import (
    sanitizar_imagen_subida, validar_metodo_pago, sin_html, limpiar_texto,
    filtro_busqueda,
)
from app.utils.zone_permissions import (
    DIAS_SEMANA, get_allowed_zone_ids, require_zone_access, ruta_semanal,
    visible_zonas_query,
)

router = APIRouter()

# Hasta cuantos dias atras se puede fechar un cobro. Permite registrar lo que
# se recibio ayer o la semana pasada sin abrir la puerta a reescribir meses
# de historia.
MAX_DIAS_RETROACTIVO = 60
logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).parent.parent.parent
FOTO_DIR = BASE_DIR / "uploads" / "fotos"
FOTO_DIR.mkdir(parents=True, exist_ok=True)


def _lock_for_update(query):
    """Aplica with_for_update() solo si el dialecto lo soporta."""
    return query if IS_SQLITE else query.with_for_update()


def aplicar_cobro_atomico(db: Session, cuota: Cuota, valor_cobrado: Decimal,
                          fecha_pago: datetime.date | None = None) -> bool:
    """Actualiza valor_pagado de la cuota usando UPDATE condicional.

    Devuelve True si la actualizacion afecto exactamente una fila (sin race
    condition). Si devuelve False es porque otra transaccion modifico la
    cuota entre la lectura y la escritura (otra peticion gano la carrera).
    Funciona en SQLite y PostgreSQL porque no depende de SELECT FOR UPDATE.
    """
    # La fecha del pago puede no ser hoy: un cobro que no se pudo registrar
    # el dia que se recibio se registra despues con su fecha real.
    fecha_pago = fecha_pago or hoy_local()
    valor_pagado_actual = money(cuota.valor_pagado)
    nuevo_pagado = valor_pagado_actual + valor_cobrado
    nuevo_estado = "Pagada" if nuevo_pagado >= money(cuota.valor) else (
        "Parcial" if nuevo_pagado > Decimal("0") else cuota.estado
    )

    stmt = (
        update(Cuota)
        .where(
            Cuota.id == cuota.id,
            Cuota.empresa_id == cuota.empresa_id,
            Cuota.valor_pagado == valor_pagado_actual,
        )
        .values(
            valor_pagado=nuevo_pagado,
            fecha_pago=fecha_pago,
            estado=nuevo_estado,
        )
    )
    result = db.execute(stmt)
    if result.rowcount == 1:
        cuota.valor_pagado = nuevo_pagado
        cuota.fecha_pago = fecha_pago
        cuota.estado = nuevo_estado
        return True
    return False


@router.get("")
@router.get("/")
async def listar_cobros(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse("/auth/login", 302)

    # La pantalla de cobros de la interfaz completa. Con la simple, el
    # cobrador cobra desde su ruta: se le manda alli. Los endpoints -ajax y
    # /cobros/registrar NO se redirigen -- son justamente los que usa la
    # vista simple para funcionar.
    simple = redirigir_a_vista_simple(db, user)
    if simple:
        return simple

    eid = user.empresa_id
    # Fecha del negocio, no la del servidor: en UTC, a partir de las 7pm hora
    # de Colombia "hoy" ya seria manana y los cobros de la tarde saldrian del
    # resumen del dia.
    hoy = hoy_local()
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
    # Si al cobrador le armaron una ruta semanal, las zonas que ve hoy no son
    # todas las suyas. Hay que decirselo: si no, parece que le desaparecieron.
    ruta = ruta_semanal(db, user.id) if user.rol not in ("admin", "superadmin") else {}

    return templates.TemplateResponse(request, "cobros.html", {
        "page": "cobros", "current_user": user,
        "cuotas_vencidas_nav": vencidas,
        "zonas": zonas, "total_hoy": total_hoy,
        "num_hoy": num_hoy, "vencidas": vencidas,
        "ruta_activa": bool(ruta),
        "dia_hoy": DIAS_SEMANA[dia_semana_local()],
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
    hoy = hoy_local()
    try:
        fecha_f = datetime.date.fromisoformat(fecha) if fecha else hoy
    except ValueError:
        return JSONResponse({"error": "Fecha invalida. Usa el formato AAAA-MM-DD."}, status_code=400)

    query = (db.query(Cobro, Cliente, Cuota)
        .join(Cliente, Cobro.cliente_id==Cliente.id)
        .join(Cuota, Cobro.cuota_id==Cuota.id)
        .filter(Cobro.empresa_id==eid, Cobro.fecha==fecha_f))
    if q:
        query = query.filter(filtro_busqueda(q, Cliente.nombre, Cliente.cedula))
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
async def pendientes(request: Request, zona_id: int=None, q: str="", fecha: str="",
                     db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error":"No autorizado"}, 401)
    eid = user.empresa_id
    allowed_zones = get_allowed_zone_ids(db, user)
    if allowed_zones is not None and zona_id and zona_id not in allowed_zones:
        return JSONResponse({"pendientes": []})
    # La pantalla manda la fecha del selector y el endpoint la ignoraba: se
    # cambiaba el dia y la lista salia siempre la de hoy.
    hoy = hoy_local()
    try:
        dia = datetime.date.fromisoformat(fecha.strip()) if fecha.strip() else hoy
    except ValueError:
        dia = hoy

    query = (db.query(Cuota, Prestamo, Cliente)
        .join(Prestamo, Cuota.prestamo_id==Prestamo.id)
        .join(Cliente, Prestamo.cliente_id==Cliente.id)
        # "Parcial" faltaba: una cuota con un abono sigue debiendo, pero
        # desaparecia de la lista y el cobrador no volvia a pasar por ella.
        .filter(Cuota.empresa_id==eid,
                Cuota.estado.in_(["Pendiente","Vencida","Parcial"]),
                Cuota.fecha_vencimiento<=dia+datetime.timedelta(days=3)))
    if q:
        query = query.filter(filtro_busqueda(q, Cliente.nombre, Cliente.cedula))
    if zona_id:
        query = query.filter(Prestamo.zona_id==zona_id)
    if allowed_zones is not None:
        query = query.filter(Prestamo.zona_id.in_(allowed_zones or [-1]))
    rows = query.order_by(Cuota.fecha_vencimiento).limit(150).all()

    # Marcar el cliente como "no pago" no cambiaba nada en esta lista: seguia
    # apareciendo igual que el resto y el cobrador no sabia si ya habia
    # pasado por el. Se envia si se registro no pago en el dia consultado y
    # cuantas visitas sin cobro acumula la cuota.
    ids = [cu.id for cu, _, _ in rows]
    del_dia: set[int] = set()
    historico: dict[int, int] = {}
    motivos: dict[int, str] = {}
    if ids:
        for np in db.query(NoPago).filter(NoPago.empresa_id == eid,
                                          NoPago.cuota_id.in_(ids)).all():
            historico[np.cuota_id] = historico.get(np.cuota_id, 0) + 1
            if np.fecha == dia:
                del_dia.add(np.cuota_id)
                if np.motivo:
                    motivos[np.cuota_id] = np.motivo

    return JSONResponse({"pendientes": [{
        "cuota_id": cu.id, "prestamo_id": p.id, "cliente_id": cl.id,
        "cliente": cl.nombre, "cedula": cl.cedula,
        "telefono": cl.telefono or "", "whatsapp": cl.whatsapp or cl.telefono or "",
        "cuota_num": cu.numero, "total_cuotas": p.num_cuotas,
        "valor": float(cu.valor), "valor_pagado": float(cu.valor_pagado or 0),
        "estado": cu.estado,
        "vencimiento": cu.fecha_vencimiento.strftime("%d/%m/%Y") if cu.fecha_vencimiento else "—",
        "dias": (dia - cu.fecha_vencimiento).days if cu.fecha_vencimiento else 0,
        "no_pago_hoy": cu.id in del_dia,
        "no_pago_motivo": motivos.get(cu.id, ""),
        "no_pagos": historico.get(cu.id, 0),
    } for cu, p, cl in rows]})

@router.post("/registrar")
async def registrar_cobro(
    request: Request,
    cuota_id: int = Form(...),
    valor_cobrado: float = Form(...),
    metodo_pago: str = Form("Efectivo"),
    observaciones: str = Form(""),
    # Fecha real del pago (AAAA-MM-DD). Vacio = hoy.
    fecha_cobro: str = Form(""),
    lat: str = Form(""),
    lng: str = Form(""),
    # La manda la PWA: la genera el celular al registrar el cobro, incluso sin
    # señal, y la repite en cada reintento de sincronizacion.
    idempotency_key: str = Form(""),
    foto: UploadFile = File(None),
    db: Session = Depends(get_db),
):
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "No autorizado"}, 401)
    # not (> 0) en vez de <= 0: con NaN ambas comparaciones dan False,
    # asi que "<= 0" deja pasar un NaN sin querer (float('nan') es lo que
    # llega si el form envia "nan"/"NaN"); "not (> 0)" si lo rechaza.
    if not (valor_cobrado > 0):
        return JSONResponse({"error": "Valor invalido"}, 400)
    try:
        metodo_pago = validar_metodo_pago(metodo_pago)
        observaciones = sin_html(observaciones, "Observaciones", 500)
    except HTTPException as e:
        return JSONResponse({"error": e.detail}, status_code=e.status_code)

    # Reintento de un cobro que ya se aplico (se perdio la respuesta): se
    # devuelve el que existe en vez de cobrarle dos veces al cliente.
    clave = limpiar_texto(idempotency_key, 64) or None
    if clave:
        ya = db.query(Cobro).filter(
            Cobro.empresa_id == user.empresa_id,
            Cobro.idempotency_key == clave,
        ).first()
        if ya:
            logger.info("[COBRO] Reintento ignorado, ya existia el cobro %s (clave=%s)", ya.id, clave[:12])
            return JSONResponse({
                "ok": True, "duplicado": True, "cobro_id": ya.id,
                "mensaje": f"Ese cobro ya estaba registrado (#{ya.id}) — no se duplicó.",
            })

    cuota = _lock_for_update(
        db.query(Cuota).filter(Cuota.id == cuota_id, Cuota.empresa_id == user.empresa_id)
    ).first()
    if not cuota:
        return JSONResponse({"error": "Cuota no encontrada"}, 404)

    prestamo = db.query(Prestamo).filter(
        Prestamo.id == cuota.prestamo_id,
        Prestamo.empresa_id == user.empresa_id,
    ).first()
    if not prestamo:
        return JSONResponse({"error": "Prestamo no encontrado"}, 404)
    if not require_zone_access(db, user, prestamo.zona_id):
        return JSONResponse({"error": "No tienes permisos para esa zona"}, 403)

    cliente = db.query(Cliente).filter(
        Cliente.id == prestamo.cliente_id,
        Cliente.empresa_id == user.empresa_id,
    ).first()
    if not cliente:
        return JSONResponse({"error": "Cliente no encontrado"}, 404)

    valor_cobrado_dec = money(valor_cobrado)
    restante = money(cuota.valor) - money(cuota.valor_pagado)
    if restante <= 0:
        return JSONResponse({"error": "La cuota ya esta pagada"}, 400)

    # Fecha real del pago. Por defecto hoy; se permite hacia atras para
    # registrar un cobro que se recibio otro dia, nunca hacia adelante.
    hoy = hoy_local()
    if fecha_cobro.strip():
        try:
            fecha_pago = datetime.date.fromisoformat(fecha_cobro.strip())
        except ValueError:
            return JSONResponse({"error": "Fecha invalida. Usa el formato AAAA-MM-DD."}, 400)
        if fecha_pago > hoy:
            return JSONResponse({"error": "La fecha del pago no puede ser futura"}, 400)
        if (hoy - fecha_pago).days > MAX_DIAS_RETROACTIVO:
            return JSONResponse(
                {"error": f"No se puede registrar un pago de hace mas de {MAX_DIAS_RETROACTIVO} dias"},
                400,
            )
    else:
        fecha_pago = hoy

    # Si pagan de mas, el excedente va a las cuotas siguientes del MISMO
    # prestamo en orden. Antes se rechazaba el cobro entero: si la cuota era
    # de 50.000 y el cliente daba 60.000, el cobrador no podia registrarlo y
    # terminaba anotando 50.000 y quedandose con la diferencia sin registrar.
    reparto = [(cuota, min(valor_cobrado_dec, restante))]
    excedente = valor_cobrado_dec - restante
    if excedente > 0:
        siguientes = _lock_for_update(
            db.query(Cuota).filter(
                Cuota.prestamo_id == cuota.prestamo_id,
                Cuota.empresa_id == user.empresa_id,
                Cuota.id != cuota.id,
                Cuota.numero > cuota.numero,
                Cuota.estado.in_(["Pendiente", "Vencida", "Parcial"]),
            )
        ).order_by(Cuota.numero.asc()).all()
        for siguiente in siguientes:
            if excedente <= 0:
                break
            saldo_sig = money(siguiente.valor) - money(siguiente.valor_pagado)
            if saldo_sig <= 0:
                continue
            aplicar = min(excedente, saldo_sig)
            reparto.append((siguiente, aplicar))
            excedente -= aplicar
        if excedente > 0:
            # Cobrar mas de lo que el cliente debe dejaria un sobrante sin
            # dueno en la contabilidad. El caso real es el ultimo pago con
            # un billete redondo, asi que en vez de repetir "el saldo
            # pendiente" se dice cuanto es y cuanto hay que devolver, que es
            # justo lo que el cobrador necesita saber con el cliente delante.
            maximo = valor_cobrado_dec - excedente
            return JSONResponse(
                {"error": f"Este prestamo solo debe {cop(maximo)}. "
                          f"Registra {cop(maximo)} y devuelve {cop(excedente)} de cambio.",
                 "maximo": float(maximo),
                 "cambio": float(excedente)},
                400,
            )

    # Coordenadas opcionales: validar antes de tocar la base
    try:
        lat_val = float(lat) if lat.strip() else None
        lng_val = float(lng) if lng.strip() else None
        if lat_val is not None and not -90 <= lat_val <= 90:
            return JSONResponse({"error": "Latitud invalida"}, 400)
        if lng_val is not None and not -180 <= lng_val <= 180:
            return JSONResponse({"error": "Longitud invalida"}, 400)
    except ValueError:
        return JSONResponse({"error": "Coordenadas invalidas"}, 400)

    # Guardar foto solo despues de validar el resto (evita escribir basura)
    foto_path = None
    if foto and foto.filename:
        contenido = await foto.read()
        ext, contenido = sanitizar_imagen_subida(foto.filename, contenido)
        foto_path = guardar_imagen(db, user.empresa_id, contenido, ext, "cobro")

    try:
        for cuota_destino, importe in reparto:
            if not aplicar_cobro_atomico(db, cuota_destino, importe, fecha_pago):
                db.rollback()
                return JSONResponse(
                    {"error": "La cuota fue actualizada por otra operacion. Recarga e intenta de nuevo."},
                    status_code=409,
                )

        cobro = Cobro(
            empresa_id=user.empresa_id,
            cuota_id=cuota_id,
            prestamo_id=prestamo.id,
            cliente_id=cliente.id,
            zona_id=prestamo.zona_id,
            valor_cobrado=valor_cobrado_dec,
            fecha=fecha_pago,
            hora=datetime.datetime.now(),
            cobrador=user.nombre or user.username,
            metodo_pago=metodo_pago,
            observaciones=observaciones or None,
            usuario_id=user.id,
            lat_cobro=lat_val,
            lng_cobro=lng_val,
            idempotency_key=clave,
            foto_path=foto_path,
        )
        db.add(cobro)

        # Un pago con fecha atrasada puede dejar detras registros de "no pago"
        # posteriores a esa fecha. Si la cuota queda saldada, esos registros
        # afirman que el cliente no pago un dia en que la cuota ya estaba
        # pagada, lo cual no pudo ocurrir: se retiran y se avisa, para que el
        # historial no diga dos cosas contrarias sobre la misma cuota.
        no_pagos_retirados = 0
        for cuota_destino, _ in reparto:
            if cuota_destino.estado != "Pagada":
                continue
            no_pagos_retirados += (
                db.query(NoPago)
                .filter(
                    NoPago.cuota_id == cuota_destino.id,
                    NoPago.empresa_id == user.empresa_id,
                    NoPago.fecha > fecha_pago,
                )
                .delete(synchronize_session=False)
            )

        cuotas_pend = db.query(func.count(Cuota.id)).filter(
            Cuota.prestamo_id == prestamo.id,
            Cuota.estado.in_(["Pendiente", "Vencida", "Parcial"]),
        ).scalar() or 0
        prestamo.estado = "Pagado" if cuotas_pend == 0 else get_estado_prestamo(prestamo)

        db.commit()
    except Exception:
        db.rollback()
        logger.exception("[COBRO-REGISTRAR] Error registrando cobro cuota=%s usuario=%s",
                         cuota_id, user.username)
        return JSONResponse({"error": "No se pudo registrar el cobro"}, status_code=500)

    # Si el pago se repartio entre varias cuotas hay que decirlo: el cobrador
    # entrego un importe y tiene que poder comprobar donde quedo aplicado.
    mensaje = f"Cobro de {cop(valor_cobrado_dec)} registrado"
    if len(reparto) > 1:
        partes = ", ".join(f"cuota {c.numero}: {cop(v)}" for c, v in reparto)
        mensaje += f" — se repartio en {partes}"
    if fecha_pago != hoy:
        mensaje += f" — con fecha {fecha_pago.strftime('%d/%m/%Y')}"
    if no_pagos_retirados:
        mensaje += (f" — se quitaron {no_pagos_retirados} registro(s) de 'no pago'"
                    f" posteriores a esa fecha")

    return JSONResponse({
        "ok": True,
        "mensaje": mensaje,
        "cuota_estado": cuota.estado,
        "fecha": fecha_pago.isoformat(),
        "no_pagos_retirados": no_pagos_retirados,
        "reparto": [{"cuota": c.numero, "valor": float(v)} for c, v in reparto],
    })


@router.get("/proxima-cuota/{cliente_id}")
async def proxima_cuota_cliente(
    request: Request,
    cliente_id: int,
    db: Session = Depends(get_db),
):
    """Cual es la siguiente cuota a cobrar de este cliente -- sin cobrarla.

    El boton "Cobrar" de la pantalla de Clientes abre el mismo modal completo
    que el modulo de Cobros (valor, metodo, GPS, foto). Ese modal necesita
    saber de antemano que cuota es y cuanto se debe, cosa que antes no hacia
    falta porque el boton registraba a ciegas la proxima cuota con solo el
    metodo de pago. La seleccion es identica a la de registrar-cliente para
    que lo que muestra el modal sea exactamente lo que se va a cobrar.
    """
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "No autorizado"}, status_code=401)

    q = (
        db.query(Cuota, Prestamo, Cliente)
        .join(Prestamo, Cuota.prestamo_id == Prestamo.id)
        .join(Cliente, Prestamo.cliente_id == Cliente.id)
        .filter(
            Cliente.id == cliente_id,
            Cliente.empresa_id == user.empresa_id,
            Prestamo.empresa_id == user.empresa_id,
            Cuota.empresa_id == user.empresa_id,
            Cuota.estado.in_(["Pendiente", "Vencida", "Parcial"]),
        )
    )
    allowed_zones = get_allowed_zone_ids(db, user)
    if allowed_zones is not None:
        q = q.filter(Prestamo.zona_id.in_(allowed_zones or [-1]))

    row = q.order_by(Cuota.fecha_vencimiento.asc(), Cuota.numero.asc()).first()
    if not row:
        return JSONResponse({"error": "Este cliente no tiene cuotas pendientes"}, status_code=404)
    cuota, prestamo, cliente = row

    saldo = money(cuota.valor) - money(cuota.valor_pagado)
    if saldo <= 0:
        return JSONResponse({"error": "La cuota ya esta pagada"}, status_code=400)

    return JSONResponse({
        "ok": True,
        "cuota_id": cuota.id,
        "numero": cuota.numero,
        "saldo": float(saldo),
        "cliente": cliente.nombre,
        "vencimiento": cuota.fecha_vencimiento.strftime("%d/%m/%Y") if cuota.fecha_vencimiento else "",
    })


@router.post("/registrar-cliente/{cliente_id}")
async def registrar_cobro_cliente_rapido(
    request: Request,
    cliente_id: int,
    metodo_pago: str = Form("Efectivo"),
    db: Session = Depends(get_db),
):
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "No autorizado"}, status_code=401)
    try:
        metodo_pago = validar_metodo_pago(metodo_pago)
    except HTTPException as e:
        return JSONResponse({"error": e.detail}, status_code=e.status_code)

    hoy = hoy_local()
    base_query = (
        db.query(Cuota, Prestamo, Cliente)
        .join(Prestamo, Cuota.prestamo_id == Prestamo.id)
        .join(Cliente, Prestamo.cliente_id == Cliente.id)
        .filter(
            Cliente.id == cliente_id,
            Cliente.empresa_id == user.empresa_id,
            Prestamo.empresa_id == user.empresa_id,
            Cuota.empresa_id == user.empresa_id,
            Cuota.estado.in_(["Pendiente", "Vencida", "Parcial"]),
        )
    )
    allowed_zones = get_allowed_zone_ids(db, user)
    if allowed_zones is not None:
        base_query = base_query.filter(Prestamo.zona_id.in_(allowed_zones or [-1]))

    base_query = _lock_for_update(base_query)
    row = base_query.order_by(Cuota.fecha_vencimiento.asc(), Cuota.numero.asc()).first()
    if not row:
        return JSONResponse({"error": "Este cliente no tiene cuotas pendientes"}, status_code=404)
    cuota, prestamo, cliente = row

    valor_cobrado = money(cuota.valor) - money(cuota.valor_pagado)
    if valor_cobrado <= 0:
        return JSONResponse({"error": "La cuota ya esta pagada"}, status_code=400)

    try:
        if not aplicar_cobro_atomico(db, cuota, valor_cobrado):
            db.rollback()
            return JSONResponse(
                {"error": "La cuota fue actualizada por otra operacion. Recarga e intenta de nuevo."},
                status_code=409,
            )

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

        cuotas_pend = db.query(func.count(Cuota.id)).filter(
            Cuota.prestamo_id == prestamo.id,
            Cuota.estado.in_(["Pendiente", "Vencida", "Parcial"]),
        ).scalar() or 0
        prestamo.estado = "Pagado" if cuotas_pend == 0 else get_estado_prestamo(prestamo)

        db.commit()
    except Exception:
        db.rollback()
        logger.exception("[COBRO-RAPIDO] Error registrando cobro cliente=%s usuario=%s",
                         cliente_id, user.username)
        return JSONResponse({"error": "No se pudo registrar el cobro"}, status_code=500)

    return JSONResponse({
        "ok": True,
        "mensaje": f"Cobro registrado a {cliente.nombre}: {cop(valor_cobrado)}",
        "cuota_id": cuota.id,
        "valor_cobrado": float(valor_cobrado),
    })


@router.post("/no-pago/deshacer")
async def deshacer_no_pago(
    request: Request,
    cuota_id: int = Form(...),
    fecha: str = Form(""),
    db: Session = Depends(get_db),
):
    """Quita la marca de "no pago" de un dia.

    Marcar por equivocacion a quien si pago dejaba la cuota apartada en la
    lista sin ninguna forma de devolverla a las pendientes por cobrar.
    """
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "No autorizado"}, 401)

    try:
        dia = datetime.date.fromisoformat(fecha.strip()) if fecha.strip() else hoy_local()
    except ValueError:
        return JSONResponse({"error": "Fecha invalida. Usa el formato AAAA-MM-DD."}, 400)

    cuota = db.query(Cuota).filter(
        Cuota.id == cuota_id, Cuota.empresa_id == user.empresa_id
    ).first()
    if not cuota:
        return JSONResponse({"error": "Cuota no encontrada"}, 404)

    prestamo = db.query(Prestamo).filter(
        Prestamo.id == cuota.prestamo_id, Prestamo.empresa_id == user.empresa_id
    ).first()
    if not prestamo:
        return JSONResponse({"error": "Prestamo no encontrado"}, 404)
    if not require_zone_access(db, user, prestamo.zona_id):
        return JSONResponse({"error": "No tienes permisos para esa zona"}, 403)

    quitados = (
        db.query(NoPago)
        .filter(NoPago.cuota_id == cuota.id,
                NoPago.empresa_id == user.empresa_id,
                NoPago.fecha == dia)
        .delete(synchronize_session=False)
    )
    db.commit()
    if not quitados:
        return JSONResponse({"error": f"No habia marca de no pago el {dia.strftime('%d/%m/%Y')}"}, 404)
    return JSONResponse({
        "ok": True,
        "mensaje": f"Se quito la marca de no pago del {dia.strftime('%d/%m/%Y')}",
    })


@router.post("/no-pago")
async def registrar_no_pago(
    request: Request,
    cuota_id: int = Form(...),
    fecha: str = Form(""),
    motivo: str = Form(""),
    db: Session = Depends(get_db),
):
    """Deja constancia de que se visito al cliente y no pago.

    Un dia sin cobro no dice nada por si solo: puede ser que el cobrador
    fuera y el cliente no tuviera, o que nadie pasara. Esto distingue las dos
    cosas y queda en el historial de la cuota junto a los pagos.
    """
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "No autorizado"}, 401)
    try:
        motivo = sin_html(motivo, "Motivo", 300)
    except HTTPException as e:
        return JSONResponse({"error": e.detail}, status_code=e.status_code)

    hoy = hoy_local()
    if fecha.strip():
        try:
            dia = datetime.date.fromisoformat(fecha.strip())
        except ValueError:
            return JSONResponse({"error": "Fecha invalida. Usa el formato AAAA-MM-DD."}, 400)
        if dia > hoy:
            return JSONResponse({"error": "La fecha no puede ser futura"}, 400)
        if (hoy - dia).days > MAX_DIAS_RETROACTIVO:
            return JSONResponse(
                {"error": f"No se puede registrar hace mas de {MAX_DIAS_RETROACTIVO} dias"}, 400)
    else:
        dia = hoy

    cuota = db.query(Cuota).filter(
        Cuota.id == cuota_id, Cuota.empresa_id == user.empresa_id
    ).first()
    if not cuota:
        return JSONResponse({"error": "Cuota no encontrada"}, 404)
    if cuota.estado == "Pagada":
        return JSONResponse({"error": "Esa cuota ya esta pagada"}, 400)

    prestamo = db.query(Prestamo).filter(
        Prestamo.id == cuota.prestamo_id, Prestamo.empresa_id == user.empresa_id
    ).first()
    if not prestamo:
        return JSONResponse({"error": "Prestamo no encontrado"}, 404)
    if not require_zone_access(db, user, prestamo.zona_id):
        return JSONResponse({"error": "No tienes permisos para esa zona"}, 403)

    ya = db.query(NoPago).filter(
        NoPago.cuota_id == cuota.id, NoPago.fecha == dia
    ).first()
    if ya:
        return JSONResponse({
            "ok": True, "duplicado": True,
            "mensaje": f"Ya estaba registrado que no pago el {dia.strftime('%d/%m/%Y')}",
        })

    db.add(NoPago(
        empresa_id=user.empresa_id,
        cuota_id=cuota.id,
        prestamo_id=prestamo.id,
        cliente_id=prestamo.cliente_id,
        zona_id=prestamo.zona_id,
        fecha=dia,
        motivo=motivo or None,
        usuario_id=user.id,
        registrado_por=user.nombre or user.username,
    ))
    try:
        db.commit()
    except Exception:
        db.rollback()
        logger.exception("[NO-PAGO] Error registrando cuota=%s", cuota_id)
        return JSONResponse({"error": "No se pudo registrar"}, 500)

    log_action(db, user, "no_pago", "cobros", f"cuota_id={cuota.id} fecha={dia}")
    return JSONResponse({
        "ok": True,
        "mensaje": f"Registrado: no pago el {dia.strftime('%d/%m/%Y')}",
        "fecha": dia.isoformat(),
    })
