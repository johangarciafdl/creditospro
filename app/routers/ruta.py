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
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import (Cliente, Cobro, Cuota, NoPago, Prestamo, Zona, get_db,
                          hoy_local)
from app.routers.auth import get_current_user
from app.services.prestamo_service import calcular_cuotas
from app.templates import templates
from app.utils.audit import log_action
from app.utils.caja import cuadre
from app.utils.money import cop, money
from app.utils.permisos_rol import es_admin, puede_gestionar_prestamos
from app.utils.validators import (filtro_busqueda, sin_html, validar_cedula,
                                  validar_entero_positivo, validar_nombre,
                                  validar_numero_positivo, validar_telefono)
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
    })


def _semaforo(vence: datetime.date | None, dia: datetime.date, tiene_deuda: bool) -> str:
    """Tres colores y nada mas: rojo debe, amarillo le toca hoy, verde al dia.

    Habia un cuarto, gris, para quien no debia nada. Se quito: para el
    cobrador que mira la lista, "no debe nada" y "esta al dia" son lo mismo
    -- ninguno de los dos le hace parar -- y dos grises que significan casi
    lo mismo es justo lo que hace que un semaforo deje de leerse de un
    vistazo.

    Se calcula en el servidor porque si cada pantalla lo dedujera por su
    cuenta, el mismo cliente podria salir amarillo en una y verde en otra.
    """
    if not tiene_deuda or vence is None:
        return "verde"
    if vence < dia:
        return "rojo"
    if vence == dia:
        return "amarillo"
    return "verde"


@router.get("/ruta/zona")
async def datos_de_la_zona(
    request: Request,
    zona_id: int = None,
    fecha: str = "",
    q: str = "",
    db: Session = Depends(get_db),
):
    """Todos los clientes de la zona con su estado del dia, y el resumen.

    Una sola peticion y no una por pestaña: las tres pestañas (Por cobrar,
    Todos, Cobrados) son tres vistas del mismo conjunto, y pedirlas por
    separado obligaria al cobrador a esperar cada vez que cambia de pestaña,
    con tres respuestas que pueden no coincidir entre si.
    """
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
    # El cobrador recorre la ruta de hoy. Poder mirar otro dia le obligaba a
    # comprobar cada vez que la fecha era la buena, y un semaforo calculado
    # para otro dia le pinta de rojo a quien hoy esta al corriente. Revisar
    # dias pasados es del administrador.
    if not es_admin(user):
        dia = hoy_local()

    # ── Los clientes de la zona ────────────────────────────────────────────
    consulta = db.query(Cliente).filter(Cliente.empresa_id == eid,
                                        Cliente.activo == True)
    if zona_id:
        consulta = consulta.filter(Cliente.zona_id == zona_id)
    elif permitidas is not None:
        consulta = consulta.filter(Cliente.zona_id.in_(permitidas or [-1]))
    if q.strip():
        from app.utils.validators import filtro_busqueda
        consulta = consulta.filter(filtro_busqueda(q.strip(), Cliente.nombre,
                                                   Cliente.cedula))
    clientes = consulta.order_by(Cliente.nombre).limit(MAX_CLIENTES).all()
    if not clientes:
        return JSONResponse({"clientes": [], "resumen": _resumen_vacio()})

    ids = [c.id for c in clientes]

    # ── Lo que se debe, PRESTAMO A PRESTAMO ───────────────────────────────
    # Una fila por prestamo activo, no por cliente. Con una por cliente, un
    # cliente con dos prestamos enseñaba las cifras del que vencia antes: en
    # produccion, un cobrador estaba cobrando uno de 500.000 y la fila le
    # mostraba el "le falta" y la cuota de otro de 200.000 del mismo cliente,
    # sin ningun aviso. Ninguna cuenta estaba mal en la base; lo que estaba
    # mal era mezclar en una fila cifras de dos prestamos. Y tocar la fila
    # cobraba el que vencia antes, no el que el cobrador creia.
    #
    # Se traen las cuotas pendientes de todos de una vez y se agrupan aqui:
    # una consulta por cliente serian ochenta idas y vueltas a la base.
    filas = (
        db.query(Cuota, Prestamo)
        .join(Prestamo, Cuota.prestamo_id == Prestamo.id)
        .filter(Prestamo.empresa_id == eid,
                Prestamo.cliente_id.in_(ids),
                Cuota.estado.in_(ESTADOS_PENDIENTES))
        .order_by(Cuota.fecha_vencimiento, Cuota.numero)
        .all()
    )
    # La cuota mas urgente de cada prestamo (la consulta viene ordenada por
    # vencimiento, asi que la primera que aparece es esa).
    siguiente: dict[int, tuple] = {}
    # Los prestamos de cada cliente, en el orden en que vencen.
    prestamos_de: dict[int, list[int]] = {}
    for cu, pr in filas:
        if pr.id not in siguiente:
            siguiente[pr.id] = (cu, pr)
            prestamos_de.setdefault(pr.cliente_id, []).append(pr.id)

    # Total y saldo de cada prestamo, con TODAS sus cuotas -- tambien las ya
    # pagadas y las que aun no vencen. El total se suma de las cuotas y no se
    # lee de prestamos.total_pagar porque los prestamos importados de antes no
    # lo tienen guardado; las cuotas si, siempre.
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

    # ── Lo que ya se cobro ese dia ─────────────────────────────────────────
    # Por prestamo para las filas, y por cliente para el que ya no debe nada
    # (si termino de pagar hoy, su fila tiene que decir que hoy pago).
    cobrado_prestamo: dict[int, Decimal] = {}
    cobrado_cliente: dict[int, Decimal] = {}
    for cliente_id, prestamo_id, valor in (
        db.query(Cobro.cliente_id, Cobro.prestamo_id, Cobro.valor_cobrado)
        .filter(Cobro.empresa_id == eid, Cobro.fecha == dia,
                Cobro.cliente_id.in_(ids))
        .all()
    ):
        cobrado_prestamo[prestamo_id] = cobrado_prestamo.get(prestamo_id, Decimal("0")) + money(valor)
        cobrado_cliente[cliente_id] = cobrado_cliente.get(cliente_id, Decimal("0")) + money(valor)

    # ── Y por donde ya se paso sin cobrar ──────────────────────────────────
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

    # ── Armar la lista ─────────────────────────────────────────────────────
    salida = []
    resumen = _resumen_vacio()
    for c in clientes:
        base_fila = {
            "cliente_id": c.id,
            "nombre": c.nombre,
            "whatsapp": c.whatsapp or c.telefono or "",
            # El nombre del archivo, no la foto: la lista pide las miniaturas
            # una a una al hacer scroll.
            "miniatura": (c.foto_path or "").replace("fotos/", "") or None,
        }
        pids = prestamos_de.get(c.id, [])
        luces_del_cliente = []

        if not pids:
            # No debe nada: una sola fila, verde, sin cifras.
            fila = dict(base_fila, fila_id=f"{c.id}-0", semaforo="verde",
                        prestamo_id=None, prestamo_n=0, prestamos_total=0,
                        prestado=0.0, total=0.0, restante=0.0,
                        cobrado_hoy=float(cobrado_cliente.get(c.id, Decimal("0"))),
                        no_pago_hoy=c.id in no_pago_cliente, pendiente=None)
            salida.append(fila)
            luces_del_cliente.append("verde")
        else:
            for n, pid in enumerate(pids, start=1):
                cu, pr = siguiente[pid]
                falta = max(Decimal("0"), money(cu.valor) - money(cu.valor_pagado or 0))
                luz = _semaforo(cu.fecha_vencimiento, dia, True)
                fila = dict(
                    base_fila,
                    fila_id=f"{c.id}-{pid}",
                    semaforo=luz,
                    prestamo_id=pid,
                    # "Prestamo 2 de 3": cuando un cliente tiene mas de uno,
                    # la pantalla lo dice, para que no parezca repetido.
                    prestamo_n=n,
                    prestamos_total=len(pids),
                    # Las cifras de la fila, TODAS del mismo prestamo: lo que
                    # se le presto, lo que tiene que devolver con el interes,
                    # lo que le queda, y la cuota en la que va.
                    prestado=float(money(pr.capital or 0)),
                    total=float(total_de.get(pid, Decimal("0"))),
                    restante=float(restante_de.get(pid, Decimal("0"))),
                    cobrado_hoy=float(cobrado_prestamo.get(pid, Decimal("0"))),
                    no_pago_hoy=pid in no_pago_prestamo,
                    pendiente={
                        "cuota_id": cu.id,
                        "cuota_num": cu.numero,
                        "total_cuotas": pr.num_cuotas,
                        "cuota": float(money(cu.valor)),
                        # Lo que queda de ESTA cuota: si abono una parte,
                        # es menos que la cuota, y es lo que se le cobra.
                        "falta": float(falta),
                    },
                )
                salida.append(fila)
                luces_del_cliente.append(luz)
                if luz in ("rojo", "amarillo"):
                    resumen["esperado"] += float(falta)

        # El resumen cuenta CLIENTES, no filas: un cliente con dos prestamos
        # vencidos es una persona que debe, no dos.
        resumen["clientes"] += 1
        if "rojo" in luces_del_cliente or "amarillo" in luces_del_cliente:
            resumen["por_cobrar"] += 1
        if "rojo" in luces_del_cliente:
            resumen["vencidos"] += 1
        cobrado = cobrado_cliente.get(c.id, Decimal("0"))
        if cobrado > 0:
            resumen["cobrados"] += 1
            resumen["cobrado"] += float(cobrado)
        if c.id in no_pago_cliente:
            resumen["no_pagos"] += 1

    # Una sola lista, ordenada por lo que hay que hacer: primero lo que se
    # debe, luego lo que toca hoy, y al final lo que esta al dia. Los
    # prestamos de un mismo cliente quedan juntos dentro de cada color.
    urgencia = {"rojo": 0, "amarillo": 1, "verde": 2}
    salida.sort(key=lambda f: (urgencia.get(f["semaforo"], 3),
                               (f["nombre"] or "").lower(),
                               f["prestamo_n"]))

    resumen["esperado"] = round(resumen["esperado"], 2)
    resumen["cobrado"] = round(resumen["cobrado"], 2)
    resumen["recortada"] = len(clientes) >= MAX_CLIENTES
    # El total que falta por cobrar en la zona es una cifra de negocio, no
    # una herramienta de trabajo: el cobrador necesita saber cuanto le debe
    # el cliente que tiene delante -- eso sigue en cada fila -- y no cuanto
    # le falta por recoger a la empresa. Al cobrador no se le oculta en la
    # pantalla: no se le manda.
    if not es_admin(user):
        resumen["esperado"] = None

    return JSONResponse({"clientes": salida, "resumen": resumen,
                         "fecha": dia.isoformat()})


def _resumen_vacio() -> dict:
    return {"clientes": 0, "por_cobrar": 0, "cobrados": 0, "vencidos": 0,
            "no_pagos": 0, "esperado": 0.0, "cobrado": 0.0, "recortada": False}


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

    return JSONResponse({"clientes": [{
        "id": c.id, "nombre": c.nombre, "cedula": c.cedula,
        "telefono": c.telefono or "", "zona_id": c.zona_id,
    } for c in consulta.order_by(Cliente.nombre).limit(15).all()]})


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
            cedula_v = validar_cedula(cedula)
            nombre_v = validar_nombre(nombre)
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

        cliente = Cliente(
            empresa_id=user.empresa_id, cedula=cedula_v, nombre=nombre_v,
            telefono=telefono_v, whatsapp=telefono_v,
            direccion=direccion_v or None, zona_id=zona_id, activo=True,
        )
        db.add(cliente)
        db.flush()
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
        observaciones=sin_html(observaciones, "Observaciones", 500) or None,
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
