"""Las cuentas que ve el cobrador tienen que cuadrar a la vista, cuota a cuota.

Reproduce el caso real que se reporto en produccion: un cliente con DOS
prestamos activos -- uno de 200.000 creado un dia antes y otro de 500.000 --
al que se le cobraba el de 500.000. La fila de la ruta enseñaba el "le
falta" y la cuota del de 200.000, porque habia una fila por cliente y se
elegia el prestamo que vencia antes. Ninguna cuenta estaba mal en la base:
lo que estaba mal era mezclar en una fila cifras de dos prestamos. Parecia
que el porcentaje o la resta fallaban, y lo que fallaba era de que prestamo
salia cada numero.

Aqui se cobra el de 500.000 cuota a cuota y en cada paso se exige que:
- cada fila sea de UN prestamo (todas sus cifras del mismo),
- "le falta" baje exactamente lo que se cobro,
- prestado + interes = total, y total - cobrado = le falta.
"""
import datetime
import tempfile
from decimal import Decimal
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="module")
def entorno():
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    bd = Path(tempfile.gettempdir()) / "creditospro_cuentas_test.db"
    if bd.exists():
        bd.unlink()

    from app.database import Base, Cliente, Empresa, Usuario, Zona, hoy_local
    from app.main import app
    from app.utils.company_activation import assign_company_key
    from app.utils.security import get_password_hash

    motor = create_engine(f"sqlite:///{bd}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(motor)
    Sesion = sessionmaker(bind=motor, autoflush=False)

    def _sesion():
        db = Sesion()
        try:
            yield db
        finally:
            db.close()

    from conftest import sustituir_sesion, vaciar_limitador
    claves = sustituir_sesion(app, _sesion)

    d = {"hoy": hoy_local()}
    db = Sesion()
    try:
        e = Empresa(nombre="CuentasSA", activa=True)
        db.add(e); db.flush()
        d["clave"] = assign_company_key(db, e)
        z = Zona(empresa_id=e.id, codigo="CU1", nombre="Castilla")
        db.add(z); db.flush()
        d["zona"] = z.id
        u = Usuario(empresa_id=e.id, username="cuentas", nombre="Cuentas",
                    rol="cobrador", activo=True,
                    password_hash=get_password_hash("ClaveDePrueba123!"))
        db.add(u); db.flush()
        u.zonas_asignadas.append(z)
        c = Cliente(empresa_id=e.id, cedula="1234", nombre="Johan Prueba",
                    telefono="3001112233", zona_id=z.id, activo=True)
        db.add(c); db.flush()
        d["cliente"] = c.id
        db.commit()
    finally:
        db.close()

    vaciar_limitador()
    cli = TestClient(app)
    cli.__enter__()
    assert cli.post("/license/activate", data={"license_key": d["clave"]}).status_code == 200
    assert cli.post("/auth/login", data={"username": "cuentas",
                                         "password": "ClaveDePrueba123!"}).status_code == 200
    cli.get("/ruta")
    cli.headers["x-csrf-token"] = cli.cookies.get("cp_csrf", "")
    yield cli, d, Sesion

    cli.__exit__(None, None, None)
    for clave in claves:
        app.dependency_overrides.pop(clave, None)
    motor.dispose()
    bd.unlink(missing_ok=True)


def _prestar(cli, d, capital, fecha):
    """Presta al cliente por el camino de la calle, con 4 cuotas semanales."""
    r = cli.post("/ruta/prestar", data={
        "zona_id": d["zona"], "cliente_id": d["cliente"], "capital": str(capital),
        "tasa_interes": "20", "num_cuotas": "4", "plazo_dias": "7",
        "fecha_inicio": fecha.isoformat()})
    assert r.status_code == 200, r.text
    return r.json()["prestamo_id"]


def _filas(cli, d):
    """Los prestamos del cliente, tal como vienen dentro de su tarjeta: una
    tarjeta por cliente, y cada prestamo con sus propias cifras."""
    r = cli.get("/ruta/zona", params={"zona_id": d["zona"]})
    assert r.status_code == 200, r.text
    tarjetas = [f for f in r.json()["clientes"] if f["cliente_id"] == d["cliente"]]
    assert len(tarjetas) <= 1, "un cliente sale en una sola tarjeta"
    return tarjetas[0]["prestamos"] if tarjetas else []


def _fila_de(cli, d, prestamo_id):
    for f in _filas(cli, d):
        if f["prestamo_id"] == prestamo_id:
            return f
    return None


def test_el_caso_real_cuota_a_cuota(entorno):
    cli, d, Sesion = entorno
    # El de 200.000, un dia antes: sus cuotas vencen ANTES que las del otro.
    p200 = _prestar(cli, d, 200000, d["hoy"] - datetime.timedelta(days=1))
    p500 = _prestar(cli, d, 500000, d["hoy"])

    filas = _filas(cli, d)
    assert len(filas) == 2, "un cliente con dos prestamos trae los dos en su tarjeta"
    assert {f["prestamo_id"] for f in filas} == {p200, p500}

    fila = _fila_de(cli, d, p500)
    # 500.000 al 20 % en 4 cuotas: 100.000 de interes, 600.000 en total,
    # cuotas de 150.000. Todo de ESTE prestamo, no del de 200.000.
    assert fila["prestado"] == 500000.0
    assert fila["total"] == 600000.0
    assert fila["restante"] == 600000.0
    assert fila["pendiente"]["cuota"] == 150000.0
    assert fila["pendiente"]["total_cuotas"] == 4

    # Se cobran las cuatro cuotas del de 500.000, una a una, tocando SU fila.
    esperado_falta = 600000.0
    for n in range(1, 5):
        fila = _fila_de(cli, d, p500)
        assert fila is not None, f"la fila del prestamo de 500.000 desaparecio en la cuota {n}"
        assert fila["pendiente"]["cuota_num"] == n, \
            f"iba a cobrar la cuota {n} y la fila ofrece la {fila['pendiente']['cuota_num']}"
        assert fila["pendiente"]["cuota"] == 150000.0, \
            f"cuota {n}: la fila enseña {fila['pendiente']['cuota']} en vez de 150.000"
        assert fila["restante"] == esperado_falta, \
            f"antes de la cuota {n}: le falta {fila['restante']}, deberia {esperado_falta}"
        # La cuenta que el cobrador hace de cabeza: total - cobrado = le falta.
        assert fila["total"] - (600000.0 - fila["restante"]) == fila["restante"]

        r = cli.post("/cobros/registrar", data={
            "cuota_id": fila["pendiente"]["cuota_id"],
            "valor_cobrado": str(int(fila["pendiente"]["falta"])),
            "metodo_pago": "Efectivo"})
        assert r.status_code == 200, r.text
        esperado_falta -= 150000.0

    # Pagado el de 500.000: su fila ya no esta, y la del de 200.000 sigue
    # intacta -- no se le desconto nada que no fuera suyo.
    assert _fila_de(cli, d, p500) is None, "el prestamo pagado sigue en la lista"
    fila200 = _fila_de(cli, d, p200)
    assert fila200["prestado"] == 200000.0
    assert fila200["total"] == 240000.0
    assert fila200["restante"] == 240000.0, "se le desconto al de 200.000 lo del otro"
    assert fila200["pendiente"]["cuota"] == 60000.0
    assert len(_filas(cli, d)) == 1

    # Y en la base, el de 500.000 esta pagado entero y el de 200.000 intacto.
    from app.database import Cuota, Prestamo
    db = Sesion()
    try:
        assert db.query(Prestamo).filter(Prestamo.id == p500).first().estado == "Pagado"
        pagado200 = sum(money_(c.valor_pagado) for c in
                        db.query(Cuota).filter(Cuota.prestamo_id == p200).all())
        assert pagado200 == Decimal("0")
    finally:
        db.close()


def money_(v):
    return Decimal(str(v or 0))


def test_el_resumen_cuenta_personas_no_prestamos(entorno):
    """Un cliente con dos prestamos es un cliente, no dos."""
    cli, d, _ = entorno
    r = cli.get("/ruta/zona", params={"zona_id": d["zona"]}).json()
    assert r["resumen"]["clientes"] == 1


@pytest.mark.parametrize("capital,tasa,cuotas", [
    (500000, 20, 4),     # el caso real: cuotas redondas
    (500000, 20, 7),     # 600.000 / 7 no es exacto
    (300000, 20, 30),
    (333333, 17.5, 13),  # nada es redondo
    (100000, 0, 3),      # sin interes
])
def test_las_cuotas_suman_exactamente_el_total(capital, tasa, cuotas):
    """El interes se aplica una vez sobre el capital, y el redondeo de dividir
    en cuotas va a la ultima: las cuotas tienen que sumar EXACTAMENTE lo que
    el cliente debe, ni un peso mas ni uno menos."""
    from decimal import ROUND_HALF_UP
    from app.services.prestamo_service import calcular_cuotas
    calc = calcular_cuotas(capital, tasa, cuotas, datetime.date(2026, 10, 1), 7)
    capital_d = Decimal(str(capital))
    # En pesos enteros, a proposito: el peso colombiano no circula en
    # centavos, y una cuota de 58.333,28 no se puede entregar ni recibir.
    interes = (capital_d * Decimal(str(tasa)) / 100).quantize(
        Decimal("1"), rounding=ROUND_HALF_UP)
    total = Decimal(str(calc["total_pagar"]))
    assert Decimal(str(calc["interes_total"])) == interes, \
        f"interes {calc['interes_total']}, esperado {interes}"
    assert total == capital_d + interes
    suma = sum(Decimal(str(c["valor"])) for c in calc["cuotas"])
    assert suma == total, f"las cuotas suman {suma} y el total es {total}"
    assert len(calc["cuotas"]) == cuotas
    # Ninguna cuota puede salir en cero o negativa.
    assert min(Decimal(str(c["valor"])) for c in calc["cuotas"]) > 0


@pytest.mark.parametrize("capital,tasa,cuotas", [
    (1000, 0, 365),     # 3 pesos x 364 dias ya pasa del total
    (5000, 0, 300),
])
def test_un_plan_que_dejaria_cuotas_negativas_se_rechaza(capital, tasa, cuotas):
    """Antes se guardaba: la ultima cuota salia en -92 pesos."""
    from app.services.prestamo_service import calcular_cuotas
    with pytest.raises(ValueError, match="por debajo de un peso"):
        calcular_cuotas(capital, tasa, cuotas, datetime.date(2026, 10, 1), 1)


def test_el_plan_imposible_se_rechaza_tambien_desde_la_calle(entorno):
    """Y el cobrador recibe el motivo, no un error del servidor."""
    cli, d, Sesion = entorno
    from app.database import Prestamo
    db = Sesion()
    try:
        antes = db.query(Prestamo).count()
    finally:
        db.close()
    r = cli.post("/ruta/prestar", data={
        "zona_id": d["zona"], "cliente_id": d["cliente"], "capital": "1000",
        "tasa_interes": "0", "num_cuotas": "365", "plazo_dias": "1"})
    assert r.status_code == 400, f"devolvio {r.status_code}: {r.text[:200]}"
    assert "peso" in r.json()["error"]
    db = Sesion()
    try:
        assert db.query(Prestamo).count() == antes, "guardo el prestamo igualmente"
    finally:
        db.close()


def test_el_plan_imposible_tambien_se_explica_en_el_modulo_de_prestamos(entorno):
    """En el modulo original acababa como un 500 generico con traza en el
    registro, y el motivo se perdia."""
    cli, d, _ = entorno
    r = cli.post("/prestamos/nuevo", data={
        "cliente_id": d["cliente"], "zona_id": d["zona"], "capital": "1000",
        "tasa_interes": "0", "num_cuotas": "365", "plazo_dias": "1",
        "fecha_inicio": d["hoy"].isoformat()})
    assert r.status_code == 400, f"devolvio {r.status_code}: {r.text[:200]}"
    assert "peso" in r.json()["error"]
