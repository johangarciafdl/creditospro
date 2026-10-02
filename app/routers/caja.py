"""El cuadre de caja: cuanto dinero deberia tener encima cada cobrador.

El calculo vive entero en `app/utils/caja.py` -- aqui solo se decide quien
puede mirar que y quien puede escribir. La separacion importa: la misma cifra
la miran el cobrador y el administrador, y si cada pantalla la calculara por
su cuenta acabarian dando numeros distintos.

Quien escribe y quien lee no es lo mismo. El administrador anota la base y la
entrega; el cobrador solo mira la suya. Si el cobrador pudiera escribir su
propia base, cualquier dia le cuadraria.
"""
import datetime

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.database import CierreCaja, MovimientoCaja, Usuario, ahora_utc, get_db, hoy_local
from app.routers.auth import get_current_user
from app.templates import templates
from app.utils.audit import log_action
from app.utils.caja import (NOMBRES, TIPOS, TIPOS_DEL_COBRADOR, caja_cerrada,
                            cierre_de, cuadre, cuadre_de_todos)
from app.utils.money import money
from app.utils.permisos_rol import (es_admin, puede_anotar_gastos,
                                    puede_registrar_movimientos_caja,
                                    puede_ver_cuadre_de)
from app.utils.validators import validar_descripcion

router = APIRouter()

# Un movimiento de caja no puede ser cualquier cifra: por encima de esto es
# casi seguro un cero de mas al teclear, y en un cuadre eso descuadra el mes.
MAXIMO_MOVIMIENTO = 50_000_000


def _fecha(texto: str) -> datetime.date | None:
    if not texto.strip():
        return hoy_local()
    try:
        return datetime.date.fromisoformat(texto.strip())
    except ValueError:
        return None


@router.get("/caja")
async def pagina_caja(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse("/auth/login?next=/caja", status_code=302)

    # El admin elige a quien mira; el cobrador solo se ve a si mismo, asi que
    # no se le manda una lista de companeros que no puede abrir.
    cobradores = []
    if es_admin(user):
        cobradores = (
            db.query(Usuario)
            .filter(Usuario.empresa_id == user.empresa_id,
                    Usuario.activo == True,
                    Usuario.rol.notin_(("admin", "superadmin")))
            .order_by(Usuario.nombre)
            .all()
        )

    return templates.TemplateResponse(request, "caja.html", {
        "page": "caja",
        "current_user": user,
        "es_admin": es_admin(user),
        "cobradores": cobradores,
        "hoy": hoy_local().isoformat(),
    })


@router.get("/caja/resumen")
async def resumen(request: Request, usuario_id: int = None, fecha: str = "",
                  db: Session = Depends(get_db)):
    """El cuadre de un cobrador, o el de todos si lo pide un administrador."""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "No autorizado"}, status_code=401)

    dia = _fecha(fecha)
    if dia is None:
        return JSONResponse({"error": "Fecha invalida. Usa AAAA-MM-DD."},
                            status_code=400)
    if dia > hoy_local():
        return JSONResponse({"error": "Todavia no se puede cuadrar un dia que no ha pasado."},
                            status_code=400)
    # El cobrador cuadra el dia que esta viviendo. Mirar los de atras no le
    # sirve para trabajar -- lo que se hizo, hecho esta -- y si invita a
    # discutir un cuadre viejo en la puerta de un cliente. El administrador
    # si los ve: es quien tiene que revisarlos.
    if not es_admin(user) and dia != hoy_local():
        return JSONResponse(
            {"error": "Solo puedes ver tu caja de hoy."}, status_code=403)

    if usuario_id is None:
        if es_admin(user):
            return JSONResponse({"fecha": dia.isoformat(),
                                 "cuadres": cuadre_de_todos(db, user.empresa_id, dia)})
        usuario_id = user.id

    if not puede_ver_cuadre_de(user, usuario_id):
        return JSONResponse({"error": "Solo puedes ver tu propia caja"},
                            status_code=403)

    # El objetivo tiene que ser de la misma empresa. Sin esto, un admin
    # podria pedir el id de un cobrador de otra empresa y recibir su cuadre.
    objetivo = (
        db.query(Usuario)
        .filter(Usuario.id == usuario_id, Usuario.empresa_id == user.empresa_id)
        .first()
    )
    if not objetivo:
        return JSONResponse({"error": "Usuario no encontrado"}, status_code=404)

    datos = cuadre(db, user.empresa_id, objetivo.id, dia)
    datos["nombre"] = objetivo.nombre or objetivo.username
    return JSONResponse({"fecha": dia.isoformat(), "cuadre": datos})


@router.post("/caja/movimiento")
async def registrar_movimiento(
    request: Request,
    usuario_id: int = Form(...),
    tipo: str = Form(...),
    # Form("") y no Form(...): con el obligatorio, un valor vacio se lleva el
    # 422 de FastAPI, que al administrador no le dice nada. Vacio entra y sale
    # por la comprobacion de abajo con un mensaje en castellano.
    valor: str = Form(""),
    fecha: str = Form(""),
    concepto: str = Form(""),
    db: Session = Depends(get_db),
):
    """Anota un gasto, la base del dia, la entrega de la tarde o una correccion.

    Dos permisos distintos conviven aqui, y la diferencia es de quien es el
    dinero que se mueve:

    - Un **gasto** lo anota el propio cobrador, en su propia caja. Quien tuvo
      el gasto es el unico que sabe cuanto fue, y hacerle esperar a que
      alguien en la oficina lo escriba deja su caja descuadrada hasta el dia
      siguiente. Queda a la vista con su concepto, que es el control.
    - La **base**, las **entregas** y los **ajustes** los pone el
      administrador: quien recibe la base no puede ser quien la escribe.
    """
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "No autorizado"}, status_code=401)

    if tipo not in TIPOS:
        return JSONResponse({"error": "Tipo de movimiento invalido"}, status_code=400)

    propio = tipo in TIPOS_DEL_COBRADOR and usuario_id == user.id
    if not (puede_registrar_movimientos_caja(user)
            or (propio and puede_anotar_gastos(user))):
        if tipo in TIPOS_DEL_COBRADOR:
            return JSONResponse(
                {"error": "Solo puedes anotar gastos en tu propia caja."},
                status_code=403)
        return JSONResponse(
            {"error": "Solo el administrador anota la base, las entregas y los ajustes."},
            status_code=403)

    try:
        cantidad = money(str(valor).replace(",", "").strip())
    except Exception:
        return JSONResponse({"error": "El valor no es un numero"}, status_code=400)
    if cantidad <= 0:
        return JSONResponse({"error": "El valor debe ser mayor que cero"},
                            status_code=400)
    if cantidad > MAXIMO_MOVIMIENTO:
        return JSONResponse(
            {"error": "Ese valor parece un error de tecleo. Revisalo."},
            status_code=400)

    dia = _fecha(fecha)
    if dia is None:
        return JSONResponse({"error": "Fecha invalida. Usa AAAA-MM-DD."},
                            status_code=400)
    if dia > hoy_local():
        return JSONResponse({"error": "No se puede anotar un movimiento en el futuro."},
                            status_code=400)

    objetivo = (
        db.query(Usuario)
        .filter(Usuario.id == usuario_id, Usuario.empresa_id == user.empresa_id)
        .first()
    )
    if not objetivo:
        return JSONResponse({"error": "Usuario no encontrado"}, status_code=404)
    if caja_cerrada(db, objetivo.id, dia):
        return JSONResponse(
            {"error": "La caja de ese día ya está cerrada: no se le anotan más movimientos."},
            status_code=409)

    try:
        # El gasto sin "en que" no se puede revisar: es obligatorio. En el
        # resto (base, entrega, ajustes) es opcional, pero con forma de texto.
        concepto = validar_descripcion(
            concepto, "En que" if tipo == "gasto" else "Concepto", 300,
            requerido=(tipo == "gasto"))
    except HTTPException as e:
        return JSONResponse({"error": e.detail}, status_code=e.status_code)

    movimiento = MovimientoCaja(
        empresa_id=user.empresa_id,
        usuario_id=objetivo.id,
        fecha=dia,
        tipo=tipo,
        valor=cantidad,
        concepto=concepto or None,
        registrado_por_id=user.id,
        registrado_por=user.nombre or user.username,
    )
    db.add(movimiento)
    db.commit()
    log_action(db, user, "movimiento_caja", "caja",
               f"{tipo}={cantidad} usuario={objetivo.username} fecha={dia}")

    return JSONResponse({
        "ok": True,
        "mensaje": f"{NOMBRES.get(tipo, tipo)}: {cantidad:.0f} anotado a {objetivo.nombre or objetivo.username}",
        "cuadre": cuadre(db, user.empresa_id, objetivo.id, dia),
    })


@router.post("/caja/movimiento/{movimiento_id}/borrar")
async def borrar_movimiento(request: Request, movimiento_id: int,
                            db: Session = Depends(get_db)):
    """Retira un movimiento mal anotado.

    Se borra en vez de anularse con un contramovimiento porque lo que se
    corrige aqui es un error de tecleo del mismo dia, y una caja con la base
    anotada dos veces y su contrapartida es una caja que ya no se entiende.
    Queda en la auditoria.
    """
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "No autorizado"}, status_code=401)

    movimiento = (
        db.query(MovimientoCaja)
        .filter(MovimientoCaja.id == movimiento_id,
                MovimientoCaja.empresa_id == user.empresa_id)
        .first()
    )
    if not movimiento:
        return JSONResponse({"error": "Movimiento no encontrado"}, status_code=404)

    # Un cobrador puede retirar un gasto suyo mal tecleado -- es el mismo
    # permiso con el que lo anoto. Lo que no puede tocar es la base ni la
    # entrega, que no las escribio el.
    propio = (movimiento.tipo in TIPOS_DEL_COBRADOR
              and movimiento.usuario_id == user.id)
    if not (puede_registrar_movimientos_caja(user)
            or (propio and puede_anotar_gastos(user))):
        return JSONResponse(
            {"error": "Solo puedes retirar gastos que anotaste tu."},
            status_code=403)

    usuario_id, dia = movimiento.usuario_id, movimiento.fecha
    if caja_cerrada(db, usuario_id, dia):
        return JSONResponse(
            {"error": "La caja de ese día ya está cerrada: no se retiran movimientos."},
            status_code=409)
    detalle = f"{movimiento.tipo}={movimiento.valor} usuario_id={usuario_id} fecha={dia}"
    db.delete(movimiento)
    db.commit()
    log_action(db, user, "movimiento_caja_borrado", "caja", detalle)

    return JSONResponse({
        "ok": True,
        "mensaje": "Movimiento retirado",
        "cuadre": cuadre(db, user.empresa_id, usuario_id, dia),
    })


# ── CIERRE DEL DIA ────────────────────────────────────────────────────────
# El cobrador declara cuanto entrega; el administrador cuenta y confirma.
# Al confirmar se anota la entrega (de ahi la toma tambien la caja general),
# queda la diferencia contra lo esperado y el dia se cierra.

def _pesos_form(texto: str):
    limpio = "".join(ch for ch in str(texto or "") if ch.isdigit())
    if not limpio:
        return None
    v = money(limpio)
    if v > MAXIMO_MOVIMIENTO:
        raise ValueError("Ese valor parece un error de tecleo. Revisalo.")
    return v


@router.post("/caja/cierre/declarar")
async def declarar_cierre(request: Request, entrego: str = Form(""), nota: str = Form(""),
                          db: Session = Depends(get_db)):
    """El cobrador dice cuanto entrega hoy. Puede corregirlo hasta que el
    administrador confirme."""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "No autorizado"}, status_code=401)
    if es_admin(user):
        return JSONResponse({"error": "El cierre lo declara el cobrador."}, status_code=400)
    try:
        valor = _pesos_form(entrego)
        nota = validar_descripcion(nota, "Nota", 300)
    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    except HTTPException as e:
        return JSONResponse({"error": e.detail}, status_code=e.status_code)
    if valor is None:
        return JSONResponse({"error": "Escribe cuanto entregas"}, status_code=400)

    hoy = hoy_local()
    c = cierre_de(db, user.id, hoy)
    if c and c.estado == "confirmado":
        return JSONResponse({"error": "Tu caja de hoy ya fue cerrada por el administrador."},
                            status_code=409)
    esperado = money(cuadre(db, user.empresa_id, user.id, hoy)["esperado"])
    if not c:
        c = CierreCaja(empresa_id=user.empresa_id, usuario_id=user.id, fecha=hoy)
        db.add(c)
    c.esperado = esperado
    c.declarado = valor
    c.nota = nota or None
    c.estado = "declarado"
    c.declarado_en = ahora_utc()
    db.commit()
    log_action(db, user, "cierre_declarado", "caja", f"entrega={valor} esperado={esperado}")
    return JSONResponse({"ok": True, "mensaje": "Entrega declarada. Falta que el administrador la confirme.",
                         "cuadre": cuadre(db, user.empresa_id, user.id, hoy)})


@router.post("/caja/cierre/confirmar")
async def confirmar_cierre(request: Request, usuario_id: int = Form(...), fecha: str = Form(""),
                           recibido: str = Form(""), nota: str = Form(""),
                           db: Session = Depends(get_db)):
    """El administrador confirma lo que recibio y cierra la caja de ese dia."""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse({"error": "No autorizado"}, status_code=401)
    if not puede_registrar_movimientos_caja(user):
        return JSONResponse({"error": "Solo el administrador cierra la caja."}, status_code=403)
    dia = _fecha(fecha)
    if dia is None or dia > hoy_local():
        return JSONResponse({"error": "Fecha invalida"}, status_code=400)
    objetivo = (db.query(Usuario)
                .filter(Usuario.id == usuario_id, Usuario.empresa_id == user.empresa_id).first())
    if not objetivo or es_admin(objetivo):
        return JSONResponse({"error": "Cobrador no encontrado"}, status_code=404)
    try:
        valor = _pesos_form(recibido)
        nota = validar_descripcion(nota, "Nota", 300)
    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    except HTTPException as e:
        return JSONResponse({"error": e.detail}, status_code=e.status_code)
    if valor is None:
        return JSONResponse({"error": "Escribe cuanto recibiste"}, status_code=400)

    c = cierre_de(db, objetivo.id, dia)
    if c and c.estado == "confirmado":
        return JSONResponse({"error": "Esa caja ya esta cerrada."}, status_code=409)
    esperado = money(cuadre(db, user.empresa_id, objetivo.id, dia)["esperado"])
    if not c:
        c = CierreCaja(empresa_id=user.empresa_id, usuario_id=objetivo.id, fecha=dia)
        db.add(c)
    quien = user.nombre or user.username
    if valor > 0:
        db.add(MovimientoCaja(
            empresa_id=user.empresa_id, usuario_id=objetivo.id, fecha=dia, tipo="entrega",
            valor=valor, concepto="Entrega del cierre del dia",
            registrado_por_id=user.id, registrado_por=quien))
    c.esperado = esperado
    c.recibido = valor
    c.diferencia = valor - esperado
    if nota:
        c.nota = ((c.nota + " · ") if c.nota else "") + nota
    c.estado = "confirmado"
    c.confirmado_por_id = user.id
    c.confirmado_por = quien
    c.confirmado_en = ahora_utc()
    db.commit()
    log_action(db, user, "cierre_confirmado", "caja",
               f"usuario={objetivo.username} fecha={dia} recibido={valor} esperado={esperado}")
    dif = valor - esperado
    texto = ("Caja cerrada: cuadra exacto." if dif == 0 else
             f"Caja cerrada con {'sobrante' if dif > 0 else 'faltante'} de {abs(dif):,.0f}".replace(",", "."))
    return JSONResponse({"ok": True, "mensaje": texto,
                         "cuadre": cuadre(db, user.empresa_id, objetivo.id, dia)})
