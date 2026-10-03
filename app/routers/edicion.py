"""Correcciones del administrador: cobros, prestamos y clientes.

Solo el admin. Cada cambio queda en la auditoria con lo que habia antes y
lo que quedo. La logica vive en app/services/edicion_admin.py.
"""
import datetime

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.database import Cliente, Cobro, Prestamo, get_db
from app.routers.auth import get_current_user
from app.services import edicion_admin as ed
from app.utils.audit import log_action
from app.utils.money import cop, money
from app.utils.permisos_rol import es_admin
from app.utils.validators import (validar_descripcion, validar_entero_positivo,
                                  validar_numero_positivo)

router = APIRouter()


def _admin(request: Request, db: Session):
    user = get_current_user(request, db)
    if not user:
        return None, JSONResponse({"error": "No autorizado"}, status_code=401)
    if not es_admin(user):
        return None, JSONResponse({"error": "Solo el administrador puede corregir datos."},
                                  status_code=403)
    return user, None


def _motivo(texto: str) -> str:
    return validar_descripcion(texto, "Motivo", 300)


def _resultado(db: Session, user, accion: str, detalle: str, mensaje: str):
    db.commit()
    log_action(db, user, accion, "edicion_admin", detalle)
    return JSONResponse({"ok": True, "mensaje": mensaje})


@router.post("/admin/cobros/{cobro_id}/editar")
async def editar_cobro(request: Request, cobro_id: int, valor: str = Form(...),
                       db: Session = Depends(get_db)):
    user, error = _admin(request, db)
    if error:
        return error
    cobro = db.query(Cobro).filter(Cobro.id == cobro_id, Cobro.empresa_id == user.empresa_id).first()
    if not cobro:
        return JSONResponse({"error": "Cobro no encontrado"}, status_code=404)
    try:
        nuevo = money(validar_numero_positivo(valor.replace(".", "").replace(",", ""), "valor"))
        antes = money(cobro.valor_cobrado)
        ed.editar_cobro(db, cobro, nuevo)
    except (HTTPException,) as e:
        db.rollback()
        return JSONResponse({"error": e.detail}, status_code=400)
    except ed.EdicionInvalida as e:
        db.rollback()
        return JSONResponse({"error": str(e)}, status_code=400)
    return _resultado(db, user, "cobro_editado",
                      f"cobro={cobro.id} prestamo={cobro.prestamo_id} antes={antes} ahora={nuevo}",
                      f"Cobro corregido: {cop(antes)} → {cop(nuevo)}")


@router.post("/admin/cobros/{cobro_id}/eliminar")
async def eliminar_cobro(request: Request, cobro_id: int, db: Session = Depends(get_db)):
    user, error = _admin(request, db)
    if error:
        return error
    cobro = db.query(Cobro).filter(Cobro.id == cobro_id, Cobro.empresa_id == user.empresa_id).first()
    if not cobro:
        return JSONResponse({"error": "Cobro no encontrado"}, status_code=404)
    detalle = (f"cobro={cobro.id} prestamo={cobro.prestamo_id} valor={cobro.valor_cobrado} "
               f"fecha={cobro.fecha} cobrador={cobro.cobrador}")
    try:
        ed.eliminar_cobro(db, cobro)
    except ed.EdicionInvalida as e:
        db.rollback()
        return JSONResponse({"error": str(e)}, status_code=400)
    return _resultado(db, user, "cobro_eliminado", detalle, "Cobro eliminado y saldo recalculado")


@router.post("/admin/prestamos/{prestamo_id}/editar")
async def editar_prestamo(request: Request, prestamo_id: int,
                          capital: str = Form(...), tasa_interes: str = Form(...),
                          num_cuotas: str = Form(...), plazo_dias: str = Form(...),
                          fecha_inicio: str = Form(...), db: Session = Depends(get_db)):
    user, error = _admin(request, db)
    if error:
        return error
    p = db.query(Prestamo).filter(Prestamo.id == prestamo_id,
                                  Prestamo.empresa_id == user.empresa_id).first()
    if not p:
        return JSONResponse({"error": "Prestamo no encontrado"}, status_code=404)
    try:
        capital_v = validar_numero_positivo(capital.replace(".", "").replace(",", ""), "capital",
                                            maximo=100_000_000)
        tasa_v = validar_numero_positivo(tasa_interes, "interes", minimo=0, maximo=100)
        cuotas_v = validar_entero_positivo(num_cuotas, "cuotas", minimo=1, maximo=365)
        plazo_v = validar_entero_positivo(plazo_dias, "plazo", minimo=1, maximo=365)
        inicio = datetime.date.fromisoformat(fecha_inicio.strip())
    except HTTPException as e:
        return JSONResponse({"error": e.detail}, status_code=400)
    except ValueError:
        return JSONResponse({"error": "Fecha invalida"}, status_code=400)
    antes = (f"capital={p.capital} tasa={p.tasa_interes} cuotas={p.num_cuotas} "
             f"plazo={p.plazo_dias} inicio={p.fecha_inicio}")
    try:
        ed.editar_prestamo(db, p, capital_v, tasa_v, cuotas_v, plazo_v, inicio)
    except (ed.EdicionInvalida, ValueError) as e:
        db.rollback()
        return JSONResponse({"error": str(e)}, status_code=400)
    return _resultado(db, user, "prestamo_editado",
                      f"prestamo={p.id} antes: {antes} | ahora: capital={capital_v} tasa={tasa_v} "
                      f"cuotas={cuotas_v} plazo={plazo_v} inicio={inicio}",
                      f"Préstamo corregido: {cop(capital_v)} en {cuotas_v} cuotas")


@router.post("/admin/prestamos/{prestamo_id}/anular")
async def anular_prestamo(request: Request, prestamo_id: int, motivo: str = Form(""),
                          db: Session = Depends(get_db)):
    user, error = _admin(request, db)
    if error:
        return error
    p = db.query(Prestamo).filter(Prestamo.id == prestamo_id,
                                  Prestamo.empresa_id == user.empresa_id).first()
    if not p:
        return JSONResponse({"error": "Prestamo no encontrado"}, status_code=404)
    try:
        motivo = _motivo(motivo)
        ed.anular_prestamo(db, p, user.nombre or user.username, motivo)
    except HTTPException as e:
        return JSONResponse({"error": e.detail}, status_code=400)
    except ed.EdicionInvalida as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    return _resultado(db, user, "prestamo_anulado",
                      f"prestamo={p.id} cliente={p.cliente_id} capital={p.capital} motivo={motivo}",
                      "Préstamo anulado: sale de la ruta y de la cartera; queda en el historial")


@router.post("/admin/clientes/{cliente_id}/retirar")
async def retirar_cliente(request: Request, cliente_id: int, motivo: str = Form(""),
                          db: Session = Depends(get_db)):
    user, error = _admin(request, db)
    if error:
        return error
    c = db.query(Cliente).filter(Cliente.id == cliente_id,
                                 Cliente.empresa_id == user.empresa_id).first()
    if not c:
        return JSONResponse({"error": "Cliente no encontrado"}, status_code=404)
    try:
        motivo = _motivo(motivo)
        n = ed.retirar_cliente(db, c, user.nombre or user.username, motivo)
    except HTTPException as e:
        return JSONResponse({"error": e.detail}, status_code=400)
    except ed.EdicionInvalida as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    return _resultado(db, user, "cliente_retirado",
                      f"cliente={c.id} cedula={c.cedula} prestamos_anulados={n} motivo={motivo}",
                      f"Cliente retirado{f' y {n} préstamo(s) anulado(s)' if n else ''}")
