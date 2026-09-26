"""Que interfaz ve cada quien, decidido en un solo sitio.

Las restricciones de rol (`app/utils/permisos_rol.py`) son iguales para todo
el software: un cobrador solo cobra y consulta, tenga la interfaz que tenga.
Lo que cambia aqui es **la pantalla**, no los permisos:

- `completa`: los modulos de siempre (Dashboard, Clientes, Cobros).
- `simple`: una sola vista con la ruta del dia, pensada para un celular en
  la calle.

Es una decision de la empresa, no del usuario: la costumbre es del equipo, y
asi el admin no tiene que elegirla cada vez que crea un cobrador. Y no toca
al admin en ningun caso -- el interruptor solo redirige a quien no
administra.

Un valor desconocido en la columna (una empresa que se creo antes de que
esto existiera, un script que escribio cualquier cosa) se lee como
`completa`: lo peor que puede pasar es que el cobrador siga viendo lo de
siempre, nunca que se quede sin pantalla.
"""
from __future__ import annotations

from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.database import Empresa, Usuario
from app.utils.permisos_rol import es_admin

INTERFAZ_COMPLETA = "completa"
INTERFAZ_SIMPLE = "simple"
INTERFACES = (INTERFAZ_COMPLETA, INTERFAZ_SIMPLE)

# La unica pantalla de la interfaz simple.
RUTA_VISTA_SIMPLE = "/ruta"

# Como se llama cada una para el admin que mueve el interruptor.
NOMBRES = {
    INTERFAZ_COMPLETA: "Completa",
    INTERFAZ_SIMPLE: "Simple",
}


def normalizar(valor: str | None) -> str:
    """Cualquier cosa que no sea una interfaz conocida es `completa`."""
    if valor in INTERFACES:
        return valor
    return INTERFAZ_COMPLETA


def interfaz_de_empresa(db: Session, empresa_id: int | None) -> str:
    """La interfaz configurada para esa empresa.

    Pide solo la columna, no la fila entera: esto se consulta al abrir
    cualquier pagina y no hace falta traer el logo ni las claves de
    activacion para responder una palabra.
    """
    if not empresa_id:
        return INTERFAZ_COMPLETA
    valor = (
        db.query(Empresa.interfaz_cobrador)
        .filter(Empresa.id == empresa_id)
        .scalar()
    )
    return normalizar(valor)


def usa_vista_simple(db: Session, user: Usuario | None) -> bool:
    """Si a este usuario le toca la vista unica en vez de los modulos."""
    if not user or es_admin(user):
        return False
    return interfaz_de_empresa(db, user.empresa_id) == INTERFAZ_SIMPLE


def redirigir_a_vista_simple(db: Session, user: Usuario | None):
    """La redireccion desde un modulo viejo, o None si no hay que redirigir.

    Se pone al principio de las paginas que un cobrador puede abrir. Devolver
    la respuesta en vez de lanzar una excepcion es deliberado: el cobrador no
    ha hecho nada mal -- su empresa simplemente trabaja con la otra pantalla,
    y lo que debe pasar es que llegue a ella, no que vea un error.
    """
    if usa_vista_simple(db, user):
        return RedirectResponse(RUTA_VISTA_SIMPLE, status_code=302)
    return None
