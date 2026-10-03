"""Los reportes del administrador, en Excel.

- Semanal: el cuadre de cada zona esa semana (domingo a sabado), su
  movimiento y la lista de cobros.
- Cierre de cartera: un ciclo de 6 semanas -- resumen por zona, semana por
  semana y movimiento de cartera.
- Clientes y prestamos: una fila por prestamo, con su saldo partido en
  capital e interes.

Las cifras salen de las mismas cuentas que las pantallas (el cuadre semanal,
finanzas.resumen y el tablero), para que el Excel nunca diga otra cosa que
el sistema. Una semana sin cuadre verificado se muestra con lo que el
sistema sabe (cobro, prestamos, intereses) y el resto en blanco, marcada
"Sin verificar".
"""
from __future__ import annotations

import datetime
import io
from decimal import Decimal

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill
from openpyxl.utils import get_column_letter
from sqlalchemy import case, func
from sqlalchemy.orm import Session

from app.database import (Cliente, Cobro, CuadreSemanal, Cuota, Empresa, NoPago, Prestamo,
                          TZ_NEGOCIO, Zona, a_hora_local, hoy_local)
from app.services.excel_service import (COLOR_VERDE, COLOR_VERDE_CLARO, encabezado_reporte,
                                        estilo_fila, estilo_header)
from app.utils import cuadre_semanal as cs
from app.utils import finanzas as fz
from app.utils.money import money, money_int
from app.utils.tablero import PREFIJO_RENOVACION, tablero_zona

CERO = Decimal("0")
FUERA = ("Anulado", "anulado")
PENDIENTES = ("Pendiente", "Vencida", "Parcial")
ESTADOS_CLIENTES = {
    "con_saldo": "Con saldo",
    "todos": "Todos",
    "pagados": "Pagados",
    "anulados": "Anulados",
}


# ── Utilidades de la hoja ─────────────────────────────────────────────────

def _pesos(v):
    return int(money_int(v)) if v is not None and v != "" else ""


def _fecha(d: datetime.date | None) -> str:
    return d.strftime("%d/%m/%Y") if d else "—"


def _nombre_empresa(db: Session, empresa_id: int) -> str:
    e = db.get(Empresa, empresa_id)
    return (e.nombre if e else None) or "CreditosPro"


def _hoja(wb, nombre, titulo, subtitulo, empresa, columnas):
    """Una hoja con encabezado y cabecera de columnas. Devuelve la hoja."""
    ws = wb.create_sheet(nombre)
    ws.sheet_view.showGridLines = False
    encabezado_reporte(ws, titulo, subtitulo, empresa)
    ultima = get_column_letter(max(len(columnas), 1))
    for r in (1, 2, 3):
        ws.merge_cells(f"A{r}:{ultima}{r}")
    estilo_header(ws, 5, list(range(1, len(columnas) + 1)), [c for c, _, _ in columnas])
    ws.row_dimensions[5].height = 30
    for i, (_, ancho, _) in enumerate(columnas, start=1):
        ws.column_dimensions[get_column_letter(i)].width = ancho
    ws.freeze_panes = "A6"
    ws._cp_columnas = columnas
    ws._cp_fila = 6
    return ws


def _fila(ws, valores, destacar=False):
    r = ws._cp_fila
    estilo_fila(ws, r, valores, par=(r % 2 == 0))
    for i, (_, _, es_plata) in enumerate(ws._cp_columnas, start=1):
        if es_plata:
            ws.cell(row=r, column=i).number_format = "#,##0"
    if destacar:
        fondo = PatternFill(start_color=COLOR_VERDE_CLARO, end_color=COLOR_VERDE_CLARO,
                            fill_type="solid")
        for i in range(1, len(ws._cp_columnas) + 1):
            celda = ws.cell(row=r, column=i)
            celda.font = Font(bold=True, size=10, name="Calibri", color=COLOR_VERDE)
            celda.fill = fondo
    ws._cp_fila += 1


def _nota(ws, texto):
    ws._cp_fila += 1
    ws.cell(row=ws._cp_fila, column=1, value=texto).font = Font(
        italic=True, size=9, name="Calibri", color="666666")
    ws._cp_fila += 1


def _total(ws, etiqueta, filas, desde_col=2):
    """Fila de totales: suma las columnas de plata y las de conteo."""
    vals = [etiqueta] + [""] * (len(ws._cp_columnas) - 1)
    for i, (_, _, es_plata) in enumerate(ws._cp_columnas, start=1):
        if i < desde_col:
            continue
        numeros = [f[i - 1] for f in filas if isinstance(f[i - 1], (int, float, Decimal))
                   and not isinstance(f[i - 1], bool)]
        if numeros and (es_plata or all(isinstance(n, int) for n in numeros)):
            vals[i - 1] = sum(numeros)
    _fila(ws, vals, destacar=True)


def _guardar(wb) -> bytes:
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _libro():
    wb = Workbook()
    wb.remove(wb.active)
    return wb


def _zonas(db: Session, empresa_id: int, zona_id: int | None, zona_ids: list[int] | None):
    q = db.query(Zona).filter(Zona.empresa_id == empresa_id)
    if zona_id:
        q = q.filter(Zona.id == zona_id)
    else:
        q = q.filter(Zona.activa == True)  # noqa: E712
    if zona_ids is not None:
        q = q.filter(Zona.id.in_(zona_ids or [-1]))
    return sorted(q.all(), key=lambda z: (z.nombre or "").lower())


def _utc(d: datetime.date) -> datetime.datetime:
    """Medianoche de Colombia de ese dia, en UTC sin zona (como se guarda)."""
    try:
        from zoneinfo import ZoneInfo
        m = datetime.datetime.combine(d, datetime.time.min, tzinfo=ZoneInfo(TZ_NEGOCIO))
        return m.astimezone(datetime.timezone.utc).replace(tzinfo=None)
    except Exception:
        return datetime.datetime.combine(d, datetime.time.min)


# ── Cuadre de una zona una semana (verificado o lo que se sabe) ───────────

def _cuadre(db: Session, empresa_id: int, zona_id: int, lunes: datetime.date) -> dict:
    c = (db.query(CuadreSemanal)
         .filter(CuadreSemanal.empresa_id == empresa_id, CuadreSemanal.zona_id == zona_id,
                 CuadreSemanal.semana == lunes).first())
    if c:
        cuando = a_hora_local(c.verificado_en)
        return {
            "cobro": c.cobro, "prestamos": c.prestamos, "gastos": c.gastos,
            "salarios": c.salarios, "base": c.base, "descuento": c.descuento,
            "efectivo": c.efectivo, "esperado": c.esperado, "diferencia": c.diferencia,
            "intereses": c.intereses, "utilidad": c.utilidad,
            "estado": (f"Verificado por {c.verificado_por or '—'}"
                       + (f" el {cuando.strftime('%d/%m/%Y')}" if cuando else "")),
            "verificado": True, "nota": c.nota or "",
        }
    p = cs.propuesta(db, empresa_id, zona_id, lunes)
    return {"cobro": p["cobro"], "prestamos": p["prestamos"], "intereses": p["intereses"],
            "gastos": "", "salarios": "", "base": "", "descuento": "", "efectivo": "",
            "esperado": "", "diferencia": "", "utilidad": "",
            "estado": "Sin verificar", "verificado": False, "nota": ""}


COLS_CUADRE = ("cobro", "prestamos", "gastos", "salarios", "base", "descuento", "efectivo",
               "esperado", "diferencia", "intereses", "utilidad")
CAB_CUADRE = [("Cobro", 13, True), ("Préstamos", 13, True), ("Gastos", 12, True),
              ("Salarios", 12, True), ("Base", 12, True), ("Descuento", 12, True),
              ("Efectivo", 13, True), ("Esperado", 13, True), ("Diferencia", 12, True),
              ("Intereses", 12, True), ("Utilidad", 12, True)]


# ── Movimiento de cartera de un periodo, por zona ─────────────────────────

def movimiento(db: Session, empresa_id: int, desde: datetime.date,
               hasta: datetime.date) -> dict[int, dict]:
    """Por zona: cobros, prestamos nuevos, renovaciones, tarjetas canceladas,
    anulados, clientes nuevos y retirados, y visitas sin pago."""
    m: dict[int, dict] = {}

    def fila(zid):
        return m.setdefault(zid, {"cobros": 0, "nuevos": 0, "nuevos_valor": CERO,
                                  "renovaciones": 0, "renovaciones_valor": CERO,
                                  "canceladas": 0, "anulados": 0, "clientes_nuevos": 0,
                                  "clientes_retirados": 0, "no_pagaron": 0})

    for zid, n in (db.query(Cobro.zona_id, func.count(Cobro.id))
                   .filter(Cobro.empresa_id == empresa_id, Cobro.fecha >= desde,
                           Cobro.fecha <= hasta, Cobro.metodo_pago != "Renovacion")
                   .group_by(Cobro.zona_id)):
        fila(zid)["cobros"] = n

    dia_salida = func.coalesce(Prestamo.fecha_desembolso, Prestamo.fecha_inicio)
    for zid, capital, obs in (db.query(Prestamo.zona_id, Prestamo.capital, Prestamo.observaciones)
                              .filter(Prestamo.empresa_id == empresa_id,
                                      Prestamo.estado.notin_(FUERA),
                                      dia_salida >= desde, dia_salida <= hasta)):
        f = fila(zid)
        if (obs or "").startswith(PREFIJO_RENOVACION):
            f["renovaciones"] += 1
            f["renovaciones_valor"] += money(capital or 0)
        else:
            f["nuevos"] += 1
            f["nuevos_valor"] += money(capital or 0)

    # Tarjeta cancelada: prestamo pagado cuyo ultimo cobro en efectivo cae en
    # el periodo (los saldados por una renovacion cuentan como renovacion).
    ultimo = (db.query(Cobro.prestamo_id, func.max(Cobro.fecha).label("ultimo"))
              .filter(Cobro.empresa_id == empresa_id, Cobro.metodo_pago != "Renovacion")
              .group_by(Cobro.prestamo_id).subquery())
    for zid, n in (db.query(Prestamo.zona_id, func.count(Prestamo.id))
                   .join(ultimo, ultimo.c.prestamo_id == Prestamo.id)
                   .filter(Prestamo.empresa_id == empresa_id,
                           Prestamo.estado.in_(("Pagado", "pagado")),
                           ultimo.c.ultimo >= desde, ultimo.c.ultimo <= hasta)
                   .group_by(Prestamo.zona_id)):
        fila(zid)["canceladas"] = n

    ini, fin = _utc(desde), _utc(hasta + datetime.timedelta(days=1))
    for zid, n in (db.query(Prestamo.zona_id, func.count(Prestamo.id))
                   .filter(Prestamo.empresa_id == empresa_id, Prestamo.estado.in_(FUERA),
                           Prestamo.anulado_en >= ini, Prestamo.anulado_en < fin)
                   .group_by(Prestamo.zona_id)):
        fila(zid)["anulados"] = n
    for zid, n in (db.query(Cliente.zona_id, func.count(Cliente.id))
                   .filter(Cliente.empresa_id == empresa_id,
                           Cliente.creado >= ini, Cliente.creado < fin)
                   .group_by(Cliente.zona_id)):
        fila(zid)["clientes_nuevos"] = n
    for zid, n in (db.query(Cliente.zona_id, func.count(Cliente.id))
                   .filter(Cliente.empresa_id == empresa_id,
                           Cliente.retirado_en >= ini, Cliente.retirado_en < fin)
                   .group_by(Cliente.zona_id)):
        fila(zid)["clientes_retirados"] = n
    for zid, n in (db.query(NoPago.zona_id, func.count(NoPago.id))
                   .filter(NoPago.empresa_id == empresa_id, NoPago.fecha >= desde,
                           NoPago.fecha <= hasta)
                   .group_by(NoPago.zona_id)):
        fila(zid)["no_pagaron"] = n
    return m


CAB_MOV = [("Zona", 18, False), ("Cobros", 9, False), ("Préstamos nuevos", 10, False),
           ("Valor nuevos", 14, True), ("Renovaciones", 11, False),
           ("Valor renovaciones", 14, True), ("Tarjetas canceladas", 11, False),
           ("Anulados", 9, False), ("Clientes nuevos", 9, False),
           ("Clientes retirados", 10, False), ("Visitas sin pago", 10, False)]


def _filas_movimiento(zonas, mov) -> list[list]:
    filas = []
    for z in zonas:
        f = mov.get(z.id) or {}
        filas.append([z.nombre, f.get("cobros", 0), f.get("nuevos", 0),
                      _pesos(f.get("nuevos_valor", 0)), f.get("renovaciones", 0),
                      _pesos(f.get("renovaciones_valor", 0)), f.get("canceladas", 0),
                      f.get("anulados", 0), f.get("clientes_nuevos", 0),
                      f.get("clientes_retirados", 0), f.get("no_pagaron", 0)])
    return filas


# ── Reporte semanal ───────────────────────────────────────────────────────

def reporte_semanal(db: Session, empresa_id: int, semana: datetime.date,
                    zona_id: int | None = None, zona_ids: list[int] | None = None) -> bytes:
    lunes = cs.inicio_semana(semana)
    domingo = lunes + datetime.timedelta(days=6)
    empresa = _nombre_empresa(db, empresa_id)
    zonas = _zonas(db, empresa_id, zona_id, zona_ids)
    periodo = f"Semana del {_fecha(lunes)} al {_fecha(domingo)}"
    wb = _libro()

    ws = _hoja(wb, "Cuadre por zona", "CUADRE SEMANAL POR ZONA", periodo, empresa,
               [("Zona", 18, False)] + CAB_CUADRE + [("Estado", 30, False)])
    filas, pendientes = [], 0
    for z in zonas:
        c = _cuadre(db, empresa_id, z.id, lunes)
        pendientes += 0 if c["verificado"] else 1
        f = [z.nombre] + [_pesos(c[k]) for k in COLS_CUADRE] + [c["estado"]]
        filas.append(f)
        _fila(ws, f)
    _total(ws, "TOTAL", filas)
    _nota(ws, "Esperado = Base + Cobro − Préstamos − Gastos − Salarios − Descuento. "
              "Diferencia = Efectivo − Esperado. Utilidad = Intereses − Gastos − Salarios − Descuento.")
    if pendientes:
        _nota(ws, f"{pendientes} zona(s) sin cuadre verificado: se muestra lo que el sistema "
                  "sabe (cobro, préstamos, intereses); el resto queda en blanco.")

    ws = _hoja(wb, "Movimiento", "MOVIMIENTO DE LA SEMANA", periodo, empresa, CAB_MOV)
    filas = _filas_movimiento(zonas, movimiento(db, empresa_id, lunes, domingo))
    for f in filas:
        _fila(ws, f)
    _total(ws, "TOTAL", filas)

    ws = _hoja(wb, "Cobros", "COBROS DE LA SEMANA", periodo, empresa,
               [("Fecha", 11, False), ("Hora", 7, False), ("Zona", 16, False),
                ("Cliente", 28, False), ("Cédula", 13, False), ("Valor", 13, True),
                ("Método", 12, False), ("Cobrador", 20, False)])
    nombres = {z.id: z.nombre for z in zonas}
    filas = []
    for co, nombre, cedula in (
        db.query(Cobro, Cliente.nombre, Cliente.cedula)
        .join(Cliente, Cobro.cliente_id == Cliente.id)
        .filter(Cobro.empresa_id == empresa_id, Cobro.fecha >= lunes, Cobro.fecha <= domingo,
                Cobro.zona_id.in_(list(nombres) or [-1]))
        .order_by(Cobro.fecha, Cobro.hora, Cobro.id)
    ):
        f = [_fecha(co.fecha), a_hora_local(co.hora).strftime("%H:%M") if co.hora else "—",
             nombres.get(co.zona_id, "—"), nombre, cedula, _pesos(co.valor_cobrado),
             co.metodo_pago or "Efectivo", co.cobrador or "—"]
        filas.append(f)
        _fila(ws, f)
    _total(ws, f"{len(filas)} cobros", filas, desde_col=6)
    return _guardar(wb)


# ── Cierre de cartera (6 semanas) ─────────────────────────────────────────

def reporte_cierre(db: Session, empresa_id: int, numero: int,
                   zona_ids: list[int] | None = None) -> bytes:
    empresa_obj = db.get(Empresa, empresa_id)
    if not empresa_obj or not empresa_obj.ciclo_inicio:
        raise ValueError("Primero configura el inicio de los ciclos en Finanzas.")
    desde, hasta = fz.ciclo(empresa_obj.ciclo_inicio, numero)
    hoy = hoy_local()
    corte = min(hasta, hoy)
    empresa = empresa_obj.nombre or "CreditosPro"
    zonas = _zonas(db, empresa_id, None, zona_ids)
    periodo = (f"Ciclo {numero}: del {_fecha(desde)} al {_fecha(hasta)}"
               + ("" if hasta < hoy else f" (en curso, datos hasta el {_fecha(hoy)})"))
    wb = _libro()

    # Resumen por zona: el mismo calculo de Finanzas + lo que queda por cobrar.
    r = fz.resumen(db, empresa_id, desde, corte)
    por_zona = {f["zona_id"]: f for f in r["zonas"]}
    ws = _hoja(wb, "Resumen por zona", "CIERRE DE CARTERA — RESUMEN POR ZONA", periodo, empresa,
               [("Zona", 18, False), ("Cobrado", 14, True), ("Prestado", 14, True),
                ("Intereses", 13, True), ("Gastos", 12, True), ("Salarios", 12, True),
                ("Descuento", 12, True), ("Flujo", 14, True), ("Resultado", 14, True),
                ("Utilidad", 13, True), ("Semanas cuadradas", 10, False),
                ("Capital por cobrar", 15, True), ("Interés por cobrar", 14, True),
                ("Clientes con saldo", 10, False), ("En mora (rojos)", 9, False)])
    semanas = r["semanas"]
    filas = []
    for z in zonas:
        f = por_zona.get(z.id, {})
        t = tablero_zona(db, empresa_id, z.id, hoy)
        fila = [z.nombre] + [_pesos(f.get(k, CERO)) for k in (
            "cobrado", "prestado", "intereses", "gastos", "salarios", "descuento",
            "flujo", "resultado", "utilidad")] + [
            f"{f.get('semanas_cuadradas', 0)}/{semanas}",
            _pesos(t["capital_pendiente"]), _pesos(t["interes_pendiente"]),
            t["cartera"]["clientes"], t["cartera"]["rojos"]]
        filas.append(fila)
        _fila(ws, fila)
    _total(ws, "TOTAL", filas)
    _nota(ws, "Flujo = Cobrado − Prestado. Resultado = Flujo − Gastos − Salarios − Descuento. "
              "Utilidad = Intereses − Gastos − Salarios − Descuento.")
    _nota(ws, "Capital e interés por cobrar son los de hoy: lo que los clientes de la zona "
              "todavía deben, partido en la proporción de cada préstamo.")
    if r["cuadres_verificados"] < r["cuadres_esperados"]:
        _nota(ws, f"Faltan cuadres: {r['cuadres_verificados']} de {r['cuadres_esperados']} "
                  "verificados. Los gastos, salarios y descuentos de las semanas sin cuadre no "
                  "están incluidos.")

    # Semana por semana.
    ws = _hoja(wb, "Semana por semana", "CIERRE DE CARTERA — SEMANA POR SEMANA", periodo,
               empresa, [("Semana", 23, False), ("Zona", 16, False)] + CAB_CUADRE
               + [("Estado", 30, False)])
    lunes = cs.inicio_semana(desde)
    while lunes <= corte:
        filas = []
        for z in zonas:
            c = _cuadre(db, empresa_id, z.id, lunes)
            f = [f"{_fecha(lunes)} – {_fecha(lunes + datetime.timedelta(days=6))}", z.nombre] + \
                [_pesos(c[k]) for k in COLS_CUADRE] + [c["estado"]]
            filas.append(f)
            _fila(ws, f)
        _total(ws, "Total semana", filas, desde_col=3)
        lunes += datetime.timedelta(days=7)

    # Movimiento de cartera.
    ws = _hoja(wb, "Movimiento de cartera", "CIERRE DE CARTERA — MOVIMIENTO", periodo, empresa,
               CAB_MOV)
    filas = _filas_movimiento(zonas, movimiento(db, empresa_id, desde, corte))
    for f in filas:
        _fila(ws, f)
    _total(ws, "TOTAL", filas)
    _nota(ws, "Tarjeta cancelada: préstamo que terminó de pagarse en el ciclo. Las "
              "renovaciones se cuentan aparte; los anulados no suman en préstamos.")
    return _guardar(wb)


# ── Clientes y prestamos (una fila por prestamo) ──────────────────────────

def reporte_clientes(db: Session, empresa_id: int, zona_id: int | None = None,
                     estado: str = "con_saldo", zona_ids: list[int] | None = None) -> bytes:
    hoy = hoy_local()
    empresa = _nombre_empresa(db, empresa_id)
    zonas = {z.id: z.nombre for z in db.query(Zona.id, Zona.nombre)
             .filter(Zona.empresa_id == empresa_id)}

    pendiente = Cuota.estado.in_(PENDIENTES)
    agregado = (
        db.query(Cuota.prestamo_id.label("pid"),
                 func.sum(Cuota.valor).label("total"),
                 func.sum(Cuota.valor_pagado).label("pagado"),
                 func.count(Cuota.id).label("cuotas"),
                 func.sum(case((Cuota.estado == "Pagada", 1), else_=0)).label("pagadas"),
                 func.sum(case(((Cuota.fecha_vencimiento < hoy) & pendiente, 1), else_=0))
                 .label("atrasadas"))
        .filter(Cuota.empresa_id == empresa_id)
        .group_by(Cuota.prestamo_id).subquery())
    q = (db.query(Prestamo, Cliente, agregado.c.total, agregado.c.pagado, agregado.c.cuotas,
                  agregado.c.pagadas, agregado.c.atrasadas)
         .join(Cliente, Prestamo.cliente_id == Cliente.id)
         .outerjoin(agregado, agregado.c.pid == Prestamo.id)
         .filter(Prestamo.empresa_id == empresa_id))
    if zona_id:
        q = q.filter(Prestamo.zona_id == zona_id)
    if zona_ids is not None:
        q = q.filter(Prestamo.zona_id.in_(zona_ids or [-1]))
    if estado == "con_saldo":
        q = q.filter(Prestamo.estado.notin_(FUERA + ("Pagado", "pagado", "Cancelado")))
    elif estado == "pagados":
        q = q.filter(Prestamo.estado.in_(("Pagado", "pagado", "Cancelado")))
    elif estado == "anulados":
        q = q.filter(Prestamo.estado.in_(FUERA))
    filas_bd = q.all()
    filas_bd.sort(key=lambda t: ((zonas.get(t[0].zona_id) or "").lower(),
                                 (t[1].nombre or "").lower(), t[0].fecha_inicio or hoy))

    filtro = ESTADOS_CLIENTES.get(estado, "Todos")
    sub = f"{filtro} — {zonas.get(zona_id, 'todas las zonas') if zona_id else 'todas las zonas'}"
    wb = _libro()
    ws = _hoja(wb, "Clientes y préstamos", "CLIENTES Y PRÉSTAMOS", sub, empresa,
               [("Zona", 15, False), ("Cliente", 26, False), ("Cédula", 13, False),
                ("Teléfono", 13, False), ("Dirección", 26, False), ("Préstamo", 9, False),
                ("Fecha inicio", 11, False), ("Capital", 13, True), ("Interés %", 8, False),
                ("Total", 13, True), ("Pagado", 13, True), ("Saldo", 13, True),
                ("Saldo capital", 13, True), ("Saldo interés", 12, True),
                ("Cuotas pagadas", 9, False), ("Cuotas", 7, False),
                ("Cuotas atrasadas", 9, False), ("Semáforo", 10, False),
                ("Estado", 12, False), ("Situación", 10, False)])
    filas = []
    for p, c, total, pagado, cuotas, pagadas, atrasadas in filas_bd:
        total = money(total or p.total_pagar or 0)
        pagado = money(pagado or 0)
        capital = money(p.capital or 0)
        anulado = p.estado in FUERA
        saldo = CERO if anulado else max(CERO, total - pagado)
        if estado == "con_saldo" and saldo <= 0:
            continue                      # dice "Activo" pero ya no debe nada
        saldo_cap = money(saldo * capital / total) if total > capital and total > 0 else saldo
        atrasadas = int(atrasadas or 0)
        if anulado or saldo <= 0:
            semaforo = "—"
        else:
            semaforo = "Rojo" if atrasadas >= 4 else ("Amarillo" if atrasadas >= 1 else "Verde")
        f = [zonas.get(p.zona_id, "Sin zona"), c.nombre, c.cedula, c.telefono or "",
             c.direccion or "", p.id, _fecha(p.fecha_inicio), _pesos(capital),
             float(p.tasa_interes or 0), _pesos(total), _pesos(pagado), _pesos(saldo),
             _pesos(saldo_cap), _pesos(saldo - saldo_cap), int(pagadas or 0), int(cuotas or 0),
             atrasadas, semaforo, p.estado, "Activo" if c.activo else "Retirado"]
        filas.append(f)
        _fila(ws, f)
    total_fila = [f"{len(filas)} préstamos"] + [""] * 19
    for i in (7, 9, 10, 11, 12, 13):          # columnas de plata (base 0)
        total_fila[i] = sum(f[i] for f in filas if isinstance(f[i], int))
    _fila(ws, total_fila, destacar=True)
    ws.auto_filter.ref = f"A5:{get_column_letter(20)}{max(5, ws._cp_fila - 2)}"
    return _guardar(wb)
