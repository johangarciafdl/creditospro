"""La vista unica del cobrador: su ruta del dia y nada mas.

Es la pantalla de la interfaz `simple` (ver `app/utils/interfaz.py`). No
añade ningun permiso: cobrar y consultar es lo mismo que puede hacer en la
interfaz completa, solo que aqui lo tiene todo en una pantalla de celular en
vez de repartido en tres modulos.

La diferencia de fondo con el modulo de Cobros no es el diseño: Cobros lista
**cuotas** que vencen pronto, y esta lista **clientes de una zona**. Un
cobrador no recorre cuotas, recorre una calle: necesita ver a todos los de la
zona -- incluidos los que estan al dia -- porque pasa por su puerta igual, y
necesita distinguirlos de un vistazo. De ahi el semaforo.

El admin tambien puede abrirla. No es un descuido: si va a encender esta
interfaz para su equipo, necesita poder ver antes lo que van a ver ellos.
"""
import datetime
from decimal import Decimal

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy import func, nulls_last, or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import (Cliente, Cobro, Cuota, NoPago, Prestamo, Usuario, Zona,
                          get_db, hoy_local)
from app.routers.auth import get_current_user
from app.services.prestamo_service import calcular_cuotas
from app.templates import templates
from app.utils.audit import log_action
from app.utils.caja import caja_cerrada, cuadre
from app.utils.money import cop, money
from app.utils.permisos_rol import es_admin, puede_gestionar_prestamos
from app.utils import orden_ruta
from app.utils.ubicacion import leer_coordenadas
from app.utils.validators import (filtro_busqueda, sin_html, validar_cedula_persona,
                                  validar_descripcion, validar_entero_positivo,
                                  validar_nombre_persona, validar_numero_positivo,
                                  validar_telefono)
from app.utils.zone_permissions import (get_allowed_zone_ids, require_zone_access,
                                        visible_zonas_query)

router = APIRouter()

# Cuotas que siguen debiendo algo. "Parcial" tiene que estar: una cuota con un
# abono sigue pendiente, y si se cae de la lista el cobrador no vuelve a pasar.
ESTADOS_PENDIENTES = ("Pendiente", "Vencida", "Parcial")

# Tope de seguridad. Una zona real tiene decenas de clientes; si alguna llega
# a tener miles, es mejor recortar la lista que mandar al celular una pagina
# que no acaba de cargar nunca.
MAX_CLIENTES = 400

# Cuanto tiempo un alta cuenta como "nueva" (sale arriba y marcada).
RECIENTE = orden_ruta.RECIENTE


@router.get("/ruta")
async def mi_ruta(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse("/auth/login?next=/ruta", status_code=302)

    # Las zonas que puede elegir hoy. Para un cobrador con ruta semanal
    # configurada son solo las que le tocan hoy (lo resuelve
    # get_allowed_zone_ids); para un admin, todas las de la empresa.
    zonas = visible_zonas_query(db, user).all()
    zonas.sort(key=lambda z: (z.nombre or "").lower())

    return templates.TemplateResponse(request, "app_cobrador.html", {
        "page": "ruta",
        "current_user": user,
        "zonas": zonas,
        # Con una sola zona no tiene sentido obligar a elegirla: se
        # preselecciona y la pantalla carga con ella.
        "zona_unica": zonas[0].id if len(zonas) == 1 else None,
        "sin_zonas": not zonas and get_allowed_zone_ids(db, user) is not None,
        "hoy": hoy_local().isoformat(),
        # El selector de dia solo lo tiene el administrador.
        "es_admin": es_admin(user),
        # Y el de "orden de que cobrador".
        "cobradores": (
            db.query(Usuario).filter(Usuario.empresa_id == user.empresa_id,
                                     Usuario.activo == True,
                                     Usuario.rol.notin_(("admin", "superadmin")))
            .order_by(Usuario.nombre).all()
            if es_admin(user) else []),
    })


# Desde cuantas cuotas atrasadas un cliente pasa a rojo.
ROJO_DESDE = 4


def _estado(atrasadas: int, tiene_deuda: bool, sin_empezar: bool = False) -> str:
    """El semaforo del cliente en la ruta del cobrador. Solo tres colores:

    - gris: no hay nada que cobrarle todavia -- nunca le prestaron, ya
      termino de pagar, o es nuevo: su prestamo aun no llega a la primera
      cuota.
    - rojo: debe 4 cuotas o mas.
    - verde: todos los demas. Si debe 1 a 3 cuotas sigue verde y la tarjeta
      dice cuantas debe, junto a "Cobrado" o "Por cobrar".

    Se calcula en el servidor porque si cada pantalla lo dedujera por su
    cuenta, el mismo cliente podria salir de un color en una y de otro en
    otra.
    """
    if not tiene_deuda:
        return "gris"
    if atrasadas >= ROJO_DESDE:
        return "rojo"
    if sin_empezar and atrasadas == 0:
        return "gris"
    return "verde"


def _orden_de(db: Session, user, cobrador_id: int | None):
    """De quien es el orden que se mira: el del propio cobrador, o el del
    cobrador que el administrador elige. (usuario, puede_moverlo)."""
    if not es_admin(user):
        return user, True
    if not cobrador_id:
        return None, False
    otro = db.query(Usuario).filter(Usuario.id == cobrador_id,
                                    Usuario.empresa_id == user.empresa_id,
                                    Usuario.activo == True).first()
    if not otro or es_admin(otro):
        return None, False
    return otro, True


@router.get("/ruta/zona")
async def datos_de_la_zona(
    request: Request,
    zona_id: int = None,
    fecha: str = "",
    q: str = "",
    cobrador_id: int = None,
    db: Session = Depends(get_db),
):
    """Los clientes de la zona, una tarjeta por cliente, en el orden del
    cobrador, con su semaforo y lo que se le cobra de cada prestamo."""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "No autorizado"}, status_code=401)
    eid = user.empresa_id

    permitidas = get_allowed_zone_ids(db, user)
    if zona_id and permitidas is not None and zona_id not in permitidas:
        # Ni un error ni los datos: la zona no es suya hoy.
        return JSONResponse({"clientes": [], "resumen": _resumen_vacio()})

    try:
        dia = datetime.date.fromisoformat(fecha.strip()) if fecha.strip() else hoy_local()
    except ValueError:
        return JSONResponse({"error": "Fecha invalida. Usa AAAA-MM-DD."}, status_code=400)
    # El cobrador recorre la ruta de hoy. Revisar dias pasados es del admin.
    if not es_admin(user):
        dia = hoy_local()

    dueno, ordenable = _orden_de(db, user, cobrador_id)

    # ── Los clientes de la zona ────────────────────────────────────────────
    consulta = db.query(Cliente).filter(Cliente.empresa_id == eid,
                                        Cliente.activo == True)
    if zona_id:
        consulta = consulta.filter(Cliente.zona_id == zona_id)
    elif permitidas is not None:
        consulta = consulta.filter(Cliente.zona_id.in_(permitidas or [-1]))
    if q.strip():
        consulta = consulta.filter(filtro_busqueda(q.strip(), Cliente.nombre,
                                                   Cliente.cedula))
    # Si la lista se recorta, que no se lleve por delante a los nuevos.
    clientes = (consulta.order_by(nulls_last(Cliente.creado.desc()), Cliente.nombre)
                .limit(MAX_CLIENTES).all())
    if not clientes:
        return JSONResponse({"clientes": [], "resumen": _resumen_vacio(),
                             "ordenable": ordenable})

    ids = [c.id for c in clientes]
    zonas = {z.id: z.nombre for z in db.query(Zona.id, Zona.nombre).filter(
        Zona.id.in_({c.zona_id for c in clientes if c.zona_id}))}

    # ── Lo que se debe, PRESTAMO A PRESTAMO ───────────────────────────────
    # Las cifras van por prestamo, nunca mezcladas: un cliente con dos
    # prestamos enseñaba las de uno y cobraba el otro. La tarjeta es por
    # cliente (es una sola parada), con sus prestamos dentro.
    filas = (
        db.query(Cuota, Prestamo)
        .join(Prestamo, Cuota.prestamo_id == Prestamo.id)
        .filter(Prestamo.empresa_id == eid,
                Prestamo.cliente_id.in_(ids),
                Cuota.estado.in_(ESTADOS_PENDIENTES))
        .order_by(Cuota.fecha_vencimiento, Cuota.numero)
        .all()
    )
    siguiente: dict[int, tuple] = {}            # la cuota mas urgente de cada prestamo
    prestamos_de: dict[int, list[int]] = {}     # los prestamos de cada cliente
    atrasadas_de: dict[int, int] = {}           # cuotas vencidas sin pagar, por prestamo
    hoy_de: set[int] = set()                    # prestamos con cuota que vence ese dia
    for cu, pr in filas:
        if pr.id not in siguiente:
            siguiente[pr.id] = (cu, pr)
            prestamos_de.setdefault(pr.cliente_id, []).append(pr.id)
        saldo = money(cu.valor) - money(cu.valor_pagado or 0)
        if saldo > 0 and cu.fecha_vencimiento:
            if cu.fecha_vencimiento < dia:
                atrasadas_de[pr.id] = atrasadas_de.get(pr.id, 0) + 1
            elif cu.fecha_vencimiento == dia:
                hoy_de.add(pr.id)

    # Total y saldo de cada prestamo con TODAS sus cuotas (los importados no
    # tienen total_pagar guardado; las cuotas si).
    total_de: dict[int, Decimal] = {}
    restante_de: dict[int, Decimal] = {}
    if siguiente:
        for pid, total, pagado in (
            db.query(Cuota.prestamo_id, func.sum(Cuota.valor),
                     func.sum(func.coalesce(Cuota.valor_pagado, 0)))
            .filter(Cuota.empresa_id == eid, Cuota.prestamo_id.in_(list(siguiente)))
            .group_by(Cuota.prestamo_id)
            .all()
        ):
            total_de[pid] = money(total or 0)
            restante_de[pid] = max(Decimal("0"), money(total or 0) - money(pagado or 0))

    # ── Lo que ya se cobro ese dia, y por donde se paso sin cobrar ─────────
    # Solo efectivo: lo que se descuenta al renovar no es plata que el
    # cobrador recibio (le salia "cobrado 90.000" a quien pago 15.000 y renovo).
    cobrado_prestamo: dict[int, Decimal] = {}
    cobrado_cliente: dict[int, Decimal] = {}
    for cliente_id, prestamo_id, valor in (
        db.query(Cobro.cliente_id, Cobro.prestamo_id, Cobro.valor_cobrado)
        .filter(Cobro.empresa_id == eid, Cobro.fecha == dia,
                Cobro.cliente_id.in_(ids),
                or_(Cobro.metodo_pago.is_(None), Cobro.metodo_pago != "Renovacion"))
        .all()
    ):
        cobrado_prestamo[prestamo_id] = cobrado_prestamo.get(prestamo_id, Decimal("0")) + money(valor)
        cobrado_cliente[cliente_id] = cobrado_cliente.get(cliente_id, Decimal("0")) + money(valor)

    no_pago_prestamo: set[int] = set()
    no_pago_cliente: set[int] = set()
    for np in (
        db.query(NoPago)
        .filter(NoPago.empresa_id == eid, NoPago.fecha == dia,
                NoPago.cliente_id.in_(ids))
        .all()
    ):
        no_pago_prestamo.add(np.prestamo_id)
        no_pago_cliente.add(np.cliente_id)

    # ── El orden: zona por zona, y dentro de cada una el del cobrador ──────
    pos = orden_ruta.posiciones(db, dueno.id if dueno else None,
                                {c.zona_id for c in clientes})
    clientes.sort(key=lambda c: ((zonas.get(c.zona_id) or "").lower(), c.zona_id or 0,
                                 orden_ruta.clave_de_orden(c, pos)))

    # ── Armar las tarjetas ─────────────────────────────────────────────────
    salida = []
    resumen = _resumen_vacio()
    for c in clientes:
        pids = prestamos_de.get(c.id, [])
        prestamos = []
        atrasadas = 0
        for n, pid in enumerate(pids, start=1):
            cu, pr = siguiente[pid]
            falta = max(Decimal("0"), money(cu.valor) - money(cu.valor_pagado or 0))
            atr = atrasadas_de.get(pid, 0)
            atrasadas += atr
            # Nuevo: aun no llega la primera cuota, no hay nada que cobrar.
            sin_empezar = (cu.numero == 1 and not money(cu.valor_pagado or 0)
                           and cu.fecha_vencimiento is not None and cu.fecha_vencimiento > dia)
            prestamos.append({
                "prestamo_id": pid,
                "n": n,
                "estado": _estado(atr, True, sin_empezar),
                "sin_empezar": sin_empezar,
                "atrasadas": atr,
                "cobrar_hoy": pid in hoy_de,
                "nuevo": orden_ruta.es_reciente(pr.creado),
                # Las cifras, TODAS del mismo prestamo.
                "prestado": float(money(pr.capital or 0)),
                "total": float(total_de.get(pid, Decimal("0"))),
                "restante": float(restante_de.get(pid, Decimal("0"))),
                "cobrado_hoy": float(cobrado_prestamo.get(pid, Decimal("0"))),
                "no_pago_hoy": pid in no_pago_prestamo,
                "pendiente": {
                    "cuota_id": cu.id,
                    "cuota_num": cu.numero,
                    "total_cuotas": pr.num_cuotas,
                    "cuota": float(money(cu.valor)),
                    # Lo que queda de ESTA cuota: si abono una parte, es
                    # menos que la cuota, y es lo que se le cobra.
                    "falta": float(falta),
                },
            })
            if atr or pid in hoy_de:
                resumen["esperado"] += float(falta)

        estado = _estado(atrasadas, bool(prestamos),
                         bool(prestamos) and all(p["sin_empezar"] for p in prestamos))
        cobrado = cobrado_cliente.get(c.id, Decimal("0"))
        salida.append({
            "cliente_id": c.id,
            "nombre": c.nombre,
            "whatsapp": c.whatsapp or c.telefono or "",
            # El nombre del archivo, no la foto: se piden una a una al hacer scroll.
            "miniatura": (c.foto_path or "").replace("fotos/", "") or None,
            "zona_id": c.zona_id,
            "zona": zonas.get(c.zona_id) or "",
            "nuevo": orden_ruta.es_reciente(c.creado),
            "estado": estado,
            "atrasadas": atrasadas,
            "cobrar_hoy": any(p["cobrar_hoy"] for p in prestamos),
            "cobrado_hoy": float(cobrado),
            "no_pago_hoy": c.id in no_pago_cliente,
            "prestamos": prestamos,
        })

        resumen["clientes"] += 1
        if atrasadas:
            resumen["vencidos"] += 1
        if atrasadas or salida[-1]["cobrar_hoy"]:
            resumen["por_cobrar"] += 1
        if cobrado > 0:
            resumen["cobrados"] += 1
            resumen["cobrado"] += float(cobrado)
        if c.id in no_pago_cliente:
            resumen["no_pagos"] += 1

    resumen["esperado"] = round(resumen["esperado"], 2)
    resumen["cobrado"] = round(resumen["cobrado"], 2)
    resumen["recortada"] = len(clientes) >= MAX_CLIENTES
    # El total que falta por cobrar en la zona es una cifra de negocio: al
    # cobrador no se le oculta en la pantalla, no se le manda.
    if not es_admin(user):
        resumen["esperado"] = None

    return JSONResponse({"clientes": salida, "resumen": resumen,
                         "fecha": dia.isoformat(), "ordenable": ordenable})


def _resumen_vacio() -> dict:
    return {"clientes": 0, "por_cobrar": 0, "cobrados": 0, "vencidos": 0,
            "no_pagos": 0, "esperado": 0.0, "cobrado": 0.0, "recortada": False}


# ── EL ORDEN DEL COBRADOR ─────────────────────────────────────────────────
@router.post("/ruta/orden")
async def guardar_orden(
    request: Request,
    zona_id: int = Form(...),
    cliente_ids: str = Form(""),
    cobrador_id: str = Form(""),
    db: Session = Depends(get_db),
):
    """Guarda el orden en que el cobrador quiere ver la zona.

    `cliente_ids` llega en el orden nuevo, separados por comas. Puede ser solo
    una parte de la zona (lo que la pantalla muestra): el resto conserva su
    lugar (ver orden_ruta.guardar).
    """
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "No autorizado"}, status_code=401)

    try:
        cid_cobrador = int(cobrador_id) if cobrador_id.strip() else None
    except ValueError:
        return JSONResponse({"error": "Cobrador invalido"}, status_code=400)
    dueno, ordenable = _orden_de(db, user, cid_cobrador)
    if not ordenable:
        return JSONResponse(
            {"error": "Elige primero de que cobrador es el orden."}, status_code=400)

    zona = db.query(Zona).filter(Zona.id == zona_id,
                                 Zona.empresa_id == user.empresa_id).first()
    if not zona:
        return JSONResponse({"error": "Zona no encontrada"}, status_code=404)
    if not require_zone_access(db, user, zona_id):
        return JSONResponse({"error": "Hoy no cobras en esa zona"}, status_code=403)

    ordenados = []
    for parte in cliente_ids.split(","):
        parte = parte.strip()
        if parte.isdigit():
            ordenados.append(int(parte))
    if not ordenados:
        return JSONResponse({"error": "No llego ningun cliente"}, status_code=400)

    todos = db.query(Cliente).filter(Cliente.empresa_id == user.empresa_id,
                                     Cliente.zona_id == zona_id,
                                     Cliente.activo == True).all()
    try:
        total = orden_ruta.guardar(db, user.empresa_id, dueno.id, zona_id, todos, ordenados)
        db.commit()
    except IntegrityError:
        # Dos guardados del mismo orden a la vez (dos pestañas, un doble
        # arrastre): gana el otro, y este se puede repetir sin perder nada.
        db.rollback()
        return JSONResponse({"error": "No se pudo guardar el orden. Intenta de nuevo."},
                            status_code=409)
    return JSONResponse({"ok": True, "guardados": total})


# ── HISTORIAL DEL CLIENTE ─────────────────────────────────────────────────
@router.get("/ruta/cliente/{cliente_id}/historial")
async def historial_del_cliente(request: Request, cliente_id: int,
                                db: Session = Depends(get_db)):
    """Los prestamos que ha tenido un cliente y los pagos de cada uno.

    Solo lectura. Es lo que reemplaza, en la tarjeta compacta de un cliente
    que no debe nada, a las cifras que ya no se enseñan.
    """
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "No autorizado"}, status_code=401)
    cliente = db.query(Cliente).filter(Cliente.id == cliente_id,
                                       Cliente.empresa_id == user.empresa_id).first()
    if not cliente or not require_zone_access(db, user, cliente.zona_id):
        return JSONResponse({"error": "Cliente no encontrado"}, status_code=404)

    prestamos = (db.query(Prestamo)
                 .filter(Prestamo.empresa_id == user.empresa_id,
                         Prestamo.cliente_id == cliente.id)
                 .order_by(Prestamo.fecha_inicio.desc(), Prestamo.id.desc())
                 .limit(50).all())
    pids = [p.id for p in prestamos]
    pagos: dict[int, list] = {}
    if pids:
        for co in (db.query(Cobro)
                   .filter(Cobro.empresa_id == user.empresa_id, Cobro.prestamo_id.in_(pids))
                   .order_by(Cobro.fecha.desc(), Cobro.id.desc())
                   .all()):
            pagos.setdefault(co.prestamo_id, []).append({
                "fecha": co.fecha.isoformat() if co.fecha else None,
                "valor": float(money(co.valor_cobrado or 0)),
                "metodo": co.metodo_pago or "Efectivo",
            })
    totales = {}
    if pids:
        for pid, total, pagado in (
            db.query(Cuota.prestamo_id, func.sum(Cuota.valor),
                     func.sum(func.coalesce(Cuota.valor_pagado, 0)))
            .filter(Cuota.empresa_id == user.empresa_id, Cuota.prestamo_id.in_(pids))
            .group_by(Cuota.prestamo_id).all()
        ):
            totales[pid] = (money(total or 0), money(pagado or 0))

    return JSONResponse({
        "cliente": {"id": cliente.id, "nombre": cliente.nombre},
        "prestamos": [{
            "id": p.id,
            "fecha": p.fecha_inicio.isoformat() if p.fecha_inicio else None,
            "prestado": float(money(p.capital or 0)),
            "total": float(totales.get(p.id, (money(p.total_pagar or 0), 0))[0]),
            "pagado": float(totales.get(p.id, (0, money(0)))[1]),
            "cuotas": p.num_cuotas,
            "estado": p.estado or "",
            "pagos": pagos.get(p.id, []),
        } for p in prestamos],
    })


# ── PRESTAR DESDE LA CALLE ────────────────────────────────────────────────
# Un cobrador que encuentra a alguien nuevo tiene que poder registrarlo y
# prestarle sin salir de su pantalla. Los dos pasos van en UNA sola peticion a
# proposito: si fueran dos, una señal que se cae entre medias deja un cliente
# dado de alta sin el prestamo que justificaba darlo de alta, y el cobrador no
# sabe si repetir o no.


@router.get("/ruta/buscar-cliente")
async def buscar_cliente(request: Request, q: str = "",
                         db: Session = Depends(get_db)):
    """Busca por cedula o nombre, para no dar de alta a quien ya existe."""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "No autorizado"}, status_code=401)
    if len(q.strip()) < 3:
        return JSONResponse({"clientes": []})

    permitidas = get_allowed_zone_ids(db, user)
    consulta = db.query(Cliente).filter(
        Cliente.empresa_id == user.empresa_id,
        filtro_busqueda(q.strip(), Cliente.nombre, Cliente.cedula),
    )
    # Un cliente de una zona que hoy no cobra no le sirve, y ensenarselo le
    # invita a prestar donde no le toca.
    if permitidas is not None:
        consulta = consulta.filter(Cliente.zona_id.in_(permitidas or [-1]))

    clientes = consulta.order_by(Cliente.nombre).limit(15).all()
    # Lo que debe cada uno de su prestamo activo mas reciente: si debe, el
    # formulario ofrece renovar en vez de prestar aparte.
    deuda = _deudas(db, user.empresa_id, [c.id for c in clientes])
    return JSONResponse({"clientes": [{
        "id": c.id, "nombre": c.nombre, "cedula": c.cedula,
        "telefono": c.telefono or "", "zona_id": c.zona_id,
        "debe": float(deuda[c.id][1]) if c.id in deuda else 0.0,
        "prestamo_activo_id": deuda[c.id][0] if c.id in deuda else None,
    } for c in clientes]})


def _deudas(db: Session, empresa_id: int, cliente_ids: list[int]) -> dict:
    """{cliente_id: (prestamo_id, saldo)} del prestamo activo con saldo mas
    reciente de cada cliente."""
    if not cliente_ids:
        return {}
    filas = (
        db.query(Prestamo.cliente_id, Prestamo.id,
                 func.sum(Cuota.valor - func.coalesce(Cuota.valor_pagado, 0)))
        .join(Cuota, Cuota.prestamo_id == Prestamo.id)
        .filter(Prestamo.empresa_id == empresa_id, Prestamo.cliente_id.in_(cliente_ids),
                Cuota.estado.in_(ESTADOS_PENDIENTES))
        .group_by(Prestamo.cliente_id, Prestamo.id)
        .order_by(Prestamo.id)
        .all()
    )
    salida = {}
    for cid, pid, saldo in filas:
        saldo = money(saldo or 0)
        if saldo > 0:
            salida[cid] = (pid, saldo)      # el ultimo (mas reciente) gana
    return salida


@router.post("/ruta/prestar")
async def prestar(
    request: Request,
    zona_id: int = Form(...),
    capital: str = Form(...),
    tasa_interes: str = Form("20"),
    num_cuotas: str = Form(...),
    plazo_dias: str = Form("1"),
    fecha_inicio: str = Form(""),
    observaciones: str = Form(""),
    # O uno o el otro: un cliente que ya existe, o los datos de uno nuevo.
    cliente_id: str = Form(""),
    cedula: str = Form(""),
    nombre: str = Form(""),
    telefono: str = Form(""),
    direccion: str = Form(""),
    # Donde se le da de alta, si es nuevo. A uno que ya existe no se le toca.
    lat: str = Form(""),
    lng: str = Form(""),
    db: Session = Depends(get_db),
):
    """Da de alta al cliente si hace falta y le presta, todo en una."""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "No autorizado"}, status_code=401)
    if not puede_gestionar_prestamos(user):
        return JSONResponse({"error": "No tienes permiso para prestar"},
                            status_code=403)

    zona = db.query(Zona).filter(Zona.id == zona_id,
                                 Zona.empresa_id == user.empresa_id).first()
    if not zona or not zona.activa:
        return JSONResponse({"error": "Zona no encontrada"}, status_code=404)
    if not require_zone_access(db, user, zona_id):
        return JSONResponse({"error": "Hoy no cobras en esa zona"}, status_code=403)

    try:
        capital_v = validar_numero_positivo(capital, "capital", maximo=100_000_000)
        tasa_v = validar_numero_positivo(tasa_interes, "tasa de interes",
                                         minimo=0, maximo=200)
        cuotas_v = validar_entero_positivo(num_cuotas, "cuotas", minimo=1, maximo=365)
        plazo_v = validar_entero_positivo(plazo_dias, "plazo", minimo=1, maximo=365)
        observaciones_v = validar_descripcion(observaciones, "Observaciones", 500)
    except HTTPException as e:
        return JSONResponse({"error": e.detail}, status_code=e.status_code)

    try:
        dia = (datetime.date.fromisoformat(fecha_inicio.strip())
               if fecha_inicio.strip() else hoy_local())
    except ValueError:
        return JSONResponse({"error": "Fecha invalida"}, status_code=400)
    if dia > hoy_local():
        return JSONResponse({"error": "No se puede prestar con fecha futura"},
                            status_code=400)
    if caja_cerrada(db, user.id, dia):
        return JSONResponse({"error": "Tu caja de ese día ya está cerrada: no se puede prestar con esa fecha."},
                            status_code=409)

    # ── El cliente: el que ya esta, o uno nuevo ───────────────────────────
    if cliente_id.strip():
        try:
            cid = validar_entero_positivo(cliente_id, "Cliente")
        except HTTPException as e:
            return JSONResponse({"error": e.detail}, status_code=e.status_code)
        cliente = db.query(Cliente).filter(
            Cliente.id == cid, Cliente.empresa_id == user.empresa_id).first()
        if not cliente:
            return JSONResponse({"error": "Cliente no encontrado"}, status_code=404)
        if not require_zone_access(db, user, cliente.zona_id):
            return JSONResponse({"error": "Ese cliente no es de tus zonas de hoy"},
                                status_code=403)
        # Deliberadamente NO se le tocan los datos aunque vengan en el
        # formulario: corregir una ficha que ya existe es del administrador.
        es_nuevo = False
    else:
        try:
            cedula_v = validar_cedula_persona(cedula)
            nombre_v = validar_nombre_persona(nombre)
            telefono_v = validar_telefono(telefono)
            direccion_v = sin_html(direccion, "Direccion", 300)
        except HTTPException as e:
            return JSONResponse({"error": e.detail}, status_code=e.status_code)

        repetido = db.query(Cliente).filter(
            Cliente.empresa_id == user.empresa_id,
            Cliente.cedula == cedula_v).first()
        if repetido:
            # No es un error suyo: es que ya existe. Se le devuelve quien es
            # para que preste sobre ese y no cree un duplicado.
            return JSONResponse({
                "error": f"Esa cedula ya es de {repetido.nombre}. Buscalo y prestale a el.",
                "cliente_id": repetido.id, "duplicado": True,
            }, status_code=409)

        lat_alta, lng_alta = leer_coordenadas(lat, lng)
        cliente = Cliente(
            empresa_id=user.empresa_id, cedula=cedula_v, nombre=nombre_v,
            telefono=telefono_v, whatsapp=telefono_v,
            direccion=direccion_v or None, zona_id=zona_id, activo=True,
            lat=lat_alta, lng=lng_alta,
        )
        db.add(cliente)
        db.flush()
        orden_ruta.poner_arriba(db, user.empresa_id, zona.id, cliente.id)
        es_nuevo = True

    # ── El prestamo ───────────────────────────────────────────────────────
    try:
        calc = calcular_cuotas(capital_v, tasa_v, cuotas_v, dia, plazo_v)
    except ValueError as e:
        db.rollback()
        return JSONResponse({"error": str(e)}, status_code=400)

    prestamo = Prestamo(
        empresa_id=user.empresa_id, cliente_id=cliente.id, zona_id=zona_id,
        capital=money(capital_v), tasa_interes=money(tasa_v),
        interes_total=money(calc.get("interes_total")),
        total_pagar=money(calc.get("total_pagar")),
        num_cuotas=cuotas_v, valor_cuota=money(calc.get("valor_cuota")),
        plazo_dias=plazo_v, fecha_inicio=dia, fecha_fin=calc.get("fecha_fin"),
        estado="Activo", cobrador=user.nombre or user.username,
        # El dinero sale de SU caja, hoy.
        desembolsado_por_id=user.id, fecha_desembolso=dia,
        observaciones=observaciones_v or None,
    )
    db.add(prestamo)
    db.flush()
    for c in calc.get("cuotas", []):
        db.add(Cuota(empresa_id=user.empresa_id, prestamo_id=prestamo.id,
                     numero=int(c["numero"]), valor=money(c.get("valor")),
                     fecha_vencimiento=c["fecha_vencimiento"], estado="Pendiente"))
    db.commit()

    log_action(db, user, "prestamo_en_calle", "prestamos",
               f"prestamo={prestamo.id} cliente={cliente.id} nuevo={es_nuevo} "
               f"capital={capital_v}")

    respuesta = {
        "ok": True, "prestamo_id": prestamo.id, "cliente_id": cliente.id,
        "cliente_nuevo": es_nuevo,
        "mensaje": f"Prestamo de {cop(capital_v)} a {cliente.nombre}",
    }
    # El sobregiro no impide prestar, pero tiene que verlo en el momento.
    estado_caja = cuadre(db, user.empresa_id, user.id, dia)
    if estado_caja["sobregiro"]:
        respuesta["sobregiro"] = estado_caja["sobregiro_valor"]
        respuesta["aviso"] = (
            f"Llevas prestado {cop(estado_caja['prestado'])} y cobrado "
            f"{cop(estado_caja['cobrado'])} hoy: "
            f"{cop(estado_caja['sobregiro_valor'])} de sobregiro.")
    return JSONResponse(respuesta)



# ── RENOVAR ───────────────────────────────────────────────────────────────
@router.post("/ruta/renovar")
async def renovar(
    request: Request,
    prestamo_id: int = Form(...),
    capital: str = Form(...),
    tasa_interes: str = Form("20"),
    num_cuotas: str = Form(...),
    plazo_dias: str = Form("1"),
    db: Session = Depends(get_db),
):
    """Le presta de nuevo a quien aun debe: se descuenta lo que debe y se le
    entrega la diferencia.

    En la base queda asi, para que todas las cuentas cuadren solas:
    - las cuotas pendientes del prestamo viejo se saldan con un cobro de
      metodo "Renovacion" (dinero que no se movio, pero que si se le abona);
    - el prestamo nuevo sale por el capital completo, desembolsado por quien
      renueva.
    En la caja del cobrador: cobrado + saldo, prestado + capital, o sea, sale
    de verdad solo la diferencia que entrega en mano.
    """
    from app.routers.cobros import aplicar_cobro_atomico

    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "No autorizado"}, status_code=401)
    if not puede_gestionar_prestamos(user):
        return JSONResponse({"error": "No tienes permiso para prestar"}, status_code=403)

    viejo = db.query(Prestamo).filter(Prestamo.id == prestamo_id,
                                      Prestamo.empresa_id == user.empresa_id).first()
    if not viejo:
        return JSONResponse({"error": "Prestamo no encontrado"}, status_code=404)
    if not require_zone_access(db, user, viejo.zona_id):
        return JSONResponse({"error": "Hoy no cobras en esa zona"}, status_code=403)
    try:
        capital_v = validar_numero_positivo(capital, "capital", maximo=100_000_000)
        tasa_v = validar_numero_positivo(tasa_interes, "tasa de interes", minimo=0, maximo=200)
        cuotas_v = validar_entero_positivo(num_cuotas, "cuotas", minimo=1, maximo=365)
        plazo_v = validar_entero_positivo(plazo_dias, "plazo", minimo=1, maximo=365)
    except HTTPException as e:
        return JSONResponse({"error": e.detail}, status_code=e.status_code)

    hoy = hoy_local()
    if caja_cerrada(db, user.id, hoy):
        return JSONResponse({"error": "Tu caja de hoy ya está cerrada: no se puede prestar."},
                            status_code=409)
    pendientes = (db.query(Cuota)
                  .filter(Cuota.prestamo_id == viejo.id, Cuota.empresa_id == user.empresa_id,
                          Cuota.estado.in_(ESTADOS_PENDIENTES))
                  .order_by(Cuota.numero).all())
    saldo = sum((max(Decimal("0"), money(c.valor) - money(c.valor_pagado or 0))
                 for c in pendientes), Decimal("0"))
    if saldo <= 0:
        return JSONResponse({"error": "Ese prestamo ya no debe nada: preste normal."},
                            status_code=400)
    capital_d = money(capital_v)
    if capital_d <= saldo:
        return JSONResponse(
            {"error": f"El nuevo prestamo tiene que ser mayor que lo que debe ({cop(saldo)})."},
            status_code=400)
    try:
        calc = calcular_cuotas(capital_v, tasa_v, cuotas_v, hoy, plazo_v)
    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=400)

    cliente = db.get(Cliente, viejo.cliente_id)
    quien = user.nombre or user.username
    try:
        nuevo = Prestamo(
            empresa_id=user.empresa_id, cliente_id=viejo.cliente_id, zona_id=viejo.zona_id,
            capital=capital_d, tasa_interes=money(tasa_v),
            interes_total=money(calc.get("interes_total")),
            total_pagar=money(calc.get("total_pagar")),
            num_cuotas=cuotas_v, valor_cuota=money(calc.get("valor_cuota")),
            plazo_dias=plazo_v, fecha_inicio=hoy, fecha_fin=calc.get("fecha_fin"),
            estado="Activo", cobrador=quien,
            desembolsado_por_id=user.id, fecha_desembolso=hoy,
            observaciones=f"Renovacion del prestamo #{viejo.id}: se descontaron {cop(saldo)}",
        )
        db.add(nuevo)
        db.flush()
        for c in calc.get("cuotas", []):
            db.add(Cuota(empresa_id=user.empresa_id, prestamo_id=nuevo.id,
                         numero=int(c["numero"]), valor=money(c.get("valor")),
                         fecha_vencimiento=c["fecha_vencimiento"], estado="Pendiente"))
        for cu in pendientes:
            falta = money(cu.valor) - money(cu.valor_pagado or 0)
            if falta <= 0:
                continue
            # Mismo cuidado que un cobro: si otro cobro toco la cuota a la
            # vez, se aborta todo en vez de saldarla dos veces.
            if not aplicar_cobro_atomico(db, cu, falta, hoy):
                db.rollback()
                return JSONResponse(
                    {"error": "Se registro otro cobro de ese cliente al mismo tiempo. Intenta de nuevo."},
                    status_code=409)
            db.add(Cobro(empresa_id=user.empresa_id, cuota_id=cu.id, prestamo_id=viejo.id,
                         cliente_id=viejo.cliente_id, zona_id=viejo.zona_id,
                         valor_cobrado=falta, fecha=hoy, cobrador=quien,
                         metodo_pago="Renovacion", usuario_id=user.id,
                         observaciones=f"Saldado con la renovacion (prestamo #{nuevo.id})"))
        viejo.estado = "Pagado"
        db.commit()
    except Exception:
        db.rollback()
        raise
    entregado = capital_d - saldo
    log_action(db, user, "prestamo_renovado", "prestamos",
               f"viejo={viejo.id} nuevo={nuevo.id} saldo={saldo} capital={capital_d}")
    return JSONResponse({
        "ok": True, "prestamo_id": nuevo.id, "saldo_descontado": float(saldo),
        "entregado": float(entregado),
        "mensaje": (f"Renovado: préstamo de {cop(capital_d)} a {cliente.nombre if cliente else ''}. "
                    f"Se descontaron {cop(saldo)}; le entregas {cop(entregado)}."),
    })
