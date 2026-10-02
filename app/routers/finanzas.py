"""Finanzas del dueño: liquidacion por ciclos de 6 semanas y caja general.

Solo el administrador. Las cuentas viven en app/utils/finanzas.py; aqui solo
se validan permisos y datos, y se guardan las decisiones (fecha de inicio de
los ciclos, saldo inicial, movimientos a mano y el reparto de cada ciclo).
"""
import datetime
import json
from decimal import Decimal, InvalidOperation

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import (Empresa, Liquidacion, MovimientoCajaGeneral, Usuario,
                          get_db, hoy_local)
from app.routers.auth import get_current_user
from app.templates import templates
from app.utils import finanzas as fz
from app.utils.audit import log_action
from app.utils.money import money
from app.utils.permisos_rol import es_admin
from app.utils.validators import validar_descripcion

router = APIRouter()

# Un valor por encima de esto es casi seguro un error de tecleo (un cero de
# mas). No es un limite del negocio: es un aviso que obliga a revisar.
MAXIMO = Decimal("10000000000")


def _admin(request: Request, db: Session):
    user = get_current_user(request, db)
    if not user:
        return None, JSONResponse({"error": "No autorizado"}, status_code=401)
    if not es_admin(user):
        return None, JSONResponse({"error": "Solo el administrador ve las finanzas."},
                                  status_code=403)
    return user, None


def _pesos(texto, campo: str, cero_ok: bool = True) -> Decimal:
    try:
        v = money(str(texto or "0").replace(".", "").replace(",", "").replace("$", "").strip() or "0")
    except (InvalidOperation, ValueError):
        raise ValueError(f"{campo}: no es un numero")
    if v < 0 or (v == 0 and not cero_ok):
        raise ValueError(f"{campo}: debe ser mayor que cero")
    if v > MAXIMO:
        raise ValueError(f"{campo}: ese valor parece un error de tecleo")
    return v


def _f(d: Decimal) -> float:
    return float(money(d))


def _resumen_json(r: dict) -> dict:
    return {
        "desde": r["desde"].isoformat(), "hasta": r["hasta"].isoformat(),
        "zonas": [{"zona_id": z["zona_id"], "zona": z["zona"], "cobrado": _f(z["cobrado"]),
                   "prestado": _f(z["prestado"]), "intereses": _f(z["intereses"]),
                   "flujo": _f(z["flujo"])} for z in r["zonas"]],
        "gastos_por_cobrador": [{"usuario_id": g["usuario_id"], "nombre": g["nombre"],
                                 "gastos": _f(g["gastos"])} for g in r["gastos_por_cobrador"]],
        "cobrado": _f(r["cobrado"]), "prestado": _f(r["prestado"]),
        "intereses": _f(r["intereses"]), "gastos": _f(r["gastos"]),
        "resultado": _f(r["resultado"]), "ganancia": _f(r["ganancia"]),
    }


@router.get("/finanzas")
async def pagina(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse("/auth/login?next=/finanzas", status_code=302)
    if not es_admin(user):
        return RedirectResponse("/dashboard", status_code=302)
    return templates.TemplateResponse(request, "finanzas.html", {
        "page": "finanzas", "current_user": user, "hoy": hoy_local().isoformat(),
    })


@router.get("/finanzas/datos")
async def datos(request: Request, ciclo: int = 0, db: Session = Depends(get_db)):
    user, error = _admin(request, db)
    if error:
        return error
    eid = user.empresa_id
    hoy = hoy_local()
    empresa = db.get(Empresa, eid)
    cobradores = [{"id": u.id, "nombre": u.nombre or u.username} for u in
                  db.query(Usuario).filter(Usuario.empresa_id == eid, Usuario.activo == True,
                                           Usuario.rol.notin_(("admin", "superadmin")))
                  .order_by(Usuario.nombre)]

    caja = fz.caja_general(db, eid, hoy)
    caja_json = {"activa": caja["activa"], "movimientos": []}
    if caja["activa"]:
        caja_json.update({
            "desde": caja["desde"].isoformat(), "saldo_inicial": _f(caja["saldo_inicial"]),
            "entregas": _f(caja["entregas"]), "bases": _f(caja["bases"]),
            "caja": _f(caja["caja"]), "reserva": _f(caja["reserva"]),
            "en_calle": _f(caja["en_calle"]),
            "movimientos": [dict(m, fecha=m["fecha"].isoformat(), valor=_f(m["valor"]))
                            for m in caja["movimientos"]],
        })

    salida = {"configurado": bool(empresa.ciclo_inicio), "hoy": hoy.isoformat(),
              "cobradores": cobradores, "caja": caja_json, "tipos_manuales": [
                  {"tipo": t, "nombre": fz.NOMBRES_GENERAL[t]} for t in fz.TIPOS_MANUALES]}
    if not empresa.ciclo_inicio:
        return JSONResponse(salida)

    inicio = empresa.ciclo_inicio
    actual = max(1, fz.numero_de(inicio, hoy))
    cerradas = {l.numero: l for l in db.query(Liquidacion).filter(Liquidacion.empresa_id == eid)}
    ciclos = []
    for n in range(actual, 0, -1):
        d, h = fz.ciclo(inicio, n)
        estado = "cerrado" if n in cerradas else ("en_curso" if h >= hoy else "por_cerrar")
        ciclos.append({"numero": n, "desde": d.isoformat(), "hasta": h.isoformat(),
                       "estado": estado})
    n = ciclo if 1 <= ciclo <= actual else actual
    d, h = fz.ciclo(inicio, n)
    if n in cerradas:
        liq = cerradas[n]
        detalle = fz.detalle_guardado(liq)
        detalle.update({"cerrado": True, "cerrado_por": liq.cerrado_por,
                        "reparto": {"base": _f(liq.base), "retiro": _f(liq.retiro),
                                    "reserva": _f(liq.reserva),
                                    "pagos_cobradores": _f(liq.pagos_cobradores),
                                    "pagos": detalle.get("pagos", [])}})
        datos_ciclo = detalle
    else:
        datos_ciclo = _resumen_json(fz.resumen(db, eid, d, min(h, hoy)))
        datos_ciclo["cerrado"] = False
    datos_ciclo.update({"numero": n, "desde": d.isoformat(), "hasta": h.isoformat(),
                        "se_puede_cerrar": n not in cerradas and h < hoy})
    salida.update({"ciclo_inicio": inicio.isoformat(), "ciclos": ciclos,
                   "ciclo": datos_ciclo})
    return JSONResponse(salida)


@router.post("/finanzas/config")
async def configurar(request: Request, ciclo_inicio: str = Form(""),
                     db: Session = Depends(get_db)):
    user, error = _admin(request, db)
    if error:
        return error
    try:
        inicio = datetime.date.fromisoformat(ciclo_inicio.strip())
    except ValueError:
        return JSONResponse({"error": "Fecha invalida"}, status_code=400)
    if db.query(Liquidacion).filter(Liquidacion.empresa_id == user.empresa_id).first():
        return JSONResponse(
            {"error": "Ya hay ciclos cerrados: cambiar la fecha de inicio los descuadraria."},
            status_code=400)
    empresa = db.get(Empresa, user.empresa_id)
    empresa.ciclo_inicio = inicio
    db.commit()
    log_action(db, user, "finanzas_config", "finanzas", f"ciclo_inicio={inicio}")
    return JSONResponse({"ok": True, "mensaje": "Ciclos configurados"})


@router.post("/finanzas/caja/inicial")
async def saldo_inicial(request: Request, valor: str = Form(""),
                        db: Session = Depends(get_db)):
    user, error = _admin(request, db)
    if error:
        return error
    try:
        v = _pesos(valor, "Saldo inicial")
    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    ya = db.query(MovimientoCajaGeneral).filter(
        MovimientoCajaGeneral.empresa_id == user.empresa_id,
        MovimientoCajaGeneral.tipo == "saldo_inicial").first()
    if ya:
        return JSONResponse(
            {"error": "La caja general ya tiene saldo inicial. Para corregirlo usa un ajuste."},
            status_code=400)
    db.add(MovimientoCajaGeneral(
        empresa_id=user.empresa_id, fecha=hoy_local(), tipo="saldo_inicial", valor=v,
        concepto="Saldo con el que arranca la caja general",
        registrado_por_id=user.id, registrado_por=user.nombre or user.username))
    db.commit()
    log_action(db, user, "caja_general_inicial", "finanzas", f"valor={v}")
    return JSONResponse({"ok": True, "mensaje": "Caja general activada"})


@router.post("/finanzas/caja/movimiento")
async def movimiento(request: Request, tipo: str = Form(""), valor: str = Form(""),
                     concepto: str = Form(""), db: Session = Depends(get_db)):
    user, error = _admin(request, db)
    if error:
        return error
    if tipo not in fz.TIPOS_MANUALES:
        return JSONResponse({"error": "Tipo de movimiento invalido"}, status_code=400)
    if not db.query(MovimientoCajaGeneral).filter(
            MovimientoCajaGeneral.empresa_id == user.empresa_id,
            MovimientoCajaGeneral.tipo == "saldo_inicial").first():
        return JSONResponse({"error": "Primero activa la caja general con su saldo inicial."},
                            status_code=400)
    try:
        v = _pesos(valor, "Valor", cero_ok=False)
        concepto = validar_descripcion(concepto, "Concepto", 300)
    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    except Exception as e:      # HTTPException del validador
        return JSONResponse({"error": getattr(e, "detail", "Concepto invalido")}, status_code=400)
    db.add(MovimientoCajaGeneral(
        empresa_id=user.empresa_id, fecha=hoy_local(), tipo=tipo, valor=v,
        concepto=concepto or None, registrado_por_id=user.id,
        registrado_por=user.nombre or user.username))
    db.commit()
    log_action(db, user, "caja_general_movimiento", "finanzas", f"{tipo}={v}")
    return JSONResponse({"ok": True, "mensaje": f"{fz.NOMBRES_GENERAL[tipo]}: anotado"})


@router.post("/finanzas/caja/movimiento/{movimiento_id}/borrar")
async def borrar(request: Request, movimiento_id: int, db: Session = Depends(get_db)):
    user, error = _admin(request, db)
    if error:
        return error
    m = db.query(MovimientoCajaGeneral).filter(
        MovimientoCajaGeneral.id == movimiento_id,
        MovimientoCajaGeneral.empresa_id == user.empresa_id).first()
    if not m:
        return JSONResponse({"error": "Movimiento no encontrado"}, status_code=404)
    if m.tipo == "saldo_inicial" or m.liquidacion_id:
        return JSONResponse(
            {"error": "Este movimiento no se retira: corrígelo con un ajuste."}, status_code=400)
    db.delete(m)
    db.commit()
    log_action(db, user, "caja_general_borrar", "finanzas", f"id={movimiento_id}")
    return JSONResponse({"ok": True, "mensaje": "Movimiento retirado"})


@router.post("/finanzas/ciclo/{numero}/cerrar")
async def cerrar_ciclo(request: Request, numero: int,
                       base: str = Form("0"), retiro: str = Form("0"),
                       reserva: str = Form("0"), pagos: str = Form("{}"),
                       db: Session = Depends(get_db)):
    """Reparte el resultado del ciclo y lo deja cerrado."""
    user, error = _admin(request, db)
    if error:
        return error
    eid = user.empresa_id
    empresa = db.get(Empresa, eid)
    if not empresa.ciclo_inicio:
        return JSONResponse({"error": "Primero configura la fecha de inicio de los ciclos."},
                            status_code=400)
    hoy = hoy_local()
    desde, hasta = fz.ciclo(empresa.ciclo_inicio, numero)
    if numero < 1 or hasta >= hoy:
        return JSONResponse({"error": "El ciclo aun no ha terminado."}, status_code=400)
    if db.query(Liquidacion).filter(Liquidacion.empresa_id == eid,
                                    Liquidacion.numero == numero).first():
        return JSONResponse({"error": "Ese ciclo ya esta cerrado."}, status_code=400)

    try:
        v_base = _pesos(base, "Base")
        v_retiro = _pesos(retiro, "Retiro")
        v_reserva = _pesos(reserva, "Reserva")
        crudo = json.loads(pagos or "{}")
        if not isinstance(crudo, dict):
            raise ValueError("Pagos invalidos")
    except (ValueError, TypeError) as e:
        return JSONResponse({"error": str(e)}, status_code=400)

    cobradores = {u.id: (u.nombre or u.username) for u in db.query(Usuario).filter(
        Usuario.empresa_id == eid, Usuario.rol.notin_(("admin", "superadmin")))}
    pagos_ok = []
    for clave, valor in crudo.items():
        try:
            uid = int(clave)
            v = _pesos(valor, "Pago")
        except (TypeError, ValueError) as e:
            return JSONResponse({"error": str(e) or "Pago invalido"}, status_code=400)
        if uid not in cobradores:
            return JSONResponse({"error": "Uno de los cobradores no es de la empresa."},
                                status_code=400)
        if v > 0:
            pagos_ok.append((uid, v))
    total_pagos = sum((v for _, v in pagos_ok), Decimal("0"))

    r = fz.resumen(db, eid, desde, hasta)
    resultado = money(r["resultado"])
    repartido = v_base + v_retiro + v_reserva + total_pagos
    if resultado <= 0:
        if repartido != 0:
            return JSONResponse(
                {"error": "El ciclo no dejo resultado positivo: no hay nada que repartir."},
                status_code=400)
    elif repartido != resultado:
        return JSONResponse({
            "error": f"El reparto suma {repartido:,.0f} y el resultado es {resultado:,.0f}. "
                     f"Deben ser iguales.".replace(",", "."),
            "resultado": float(resultado), "repartido": float(repartido)}, status_code=400)

    detalle = _resumen_json(r)
    detalle["pagos"] = [{"usuario_id": uid, "nombre": cobradores[uid], "valor": float(v)}
                        for uid, v in pagos_ok]
    quien = user.nombre or user.username
    liq = Liquidacion(
        empresa_id=eid, numero=numero, desde=desde, hasta=hasta,
        cobrado=r["cobrado"], prestado=r["prestado"], gastos=r["gastos"],
        intereses=r["intereses"], resultado=resultado,
        base=v_base, retiro=v_retiro, reserva=v_reserva, pagos_cobradores=total_pagos,
        detalle=json.dumps(detalle, ensure_ascii=False),
        cerrado_por_id=user.id, cerrado_por=quien)
    db.add(liq)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        return JSONResponse({"error": "Ese ciclo ya esta cerrado."}, status_code=400)

    # Lo que sale de la caja general con el reparto. La base se queda en
    # caja: no es un movimiento.
    def mov(tipo, valor, concepto, uid=None):
        if valor > 0:
            db.add(MovimientoCajaGeneral(
                empresa_id=eid, fecha=hoy, tipo=tipo, valor=valor, concepto=concepto,
                usuario_id=uid, liquidacion_id=liq.id,
                registrado_por_id=user.id, registrado_por=quien))
    mov("retiro", v_retiro, f"Retiro del ciclo {numero}")
    mov("a_reserva", v_reserva, f"Reserva del ciclo {numero}")
    for uid, v in pagos_ok:
        mov("pago_cobrador", v, f"Pago del ciclo {numero} a {cobradores[uid]}", uid)
    db.commit()
    log_action(db, user, "ciclo_cerrado", "finanzas",
               f"ciclo={numero} resultado={resultado} retiro={v_retiro} reserva={v_reserva} "
               f"pagos={total_pagos} base={v_base}")
    return JSONResponse({"ok": True, "mensaje": f"Ciclo {numero} cerrado y repartido"})
