"""Que puede hacer cada rol, decidido en un solo sitio.

Hasta ahora lo unico que limitaba a un cobrador era el filtro por zona: veia
solo sus clientes, pero sobre ellos podia hacer de todo -- crear, editar la
direccion, cambiar la foto, mover la ubicacion. Ninguna comprobacion de rol
en `clientes.py`, ninguna en `prestamos.py`, ninguna en `reportes.py`.

La regla del negocio es que el cobrador **solo cobra y consulta**: registra
pagos, marca que alguien no pago, y mira el estado de los clientes de las
zonas que le tocan ese dia. Nada mas.

Un matiz que conviene no confundir: la foto y la ubicacion que se guardan
**con cada cobro** son del cobro, no del cliente, y ahi si las aporta el
cobrador -- son la evidencia de donde y como se recibio el dinero. Lo que se
cierra aqui es la ficha del cliente.

Las funciones se llaman como la pregunta que responden, para que en el
endpoint se lea igual que la regla: `if not puede_gestionar_clientes(user)`.
"""
from __future__ import annotations

from app.database import Usuario

# Quien administra la empresa. superadmin entra porque es el dueno de la
# plataforma y necesita poder arreglar las cosas de cualquier empresa.
ROLES_ADMIN = ("admin", "superadmin")


def es_admin(user: Usuario | None) -> bool:
    return bool(user and user.rol in ROLES_ADMIN)


def puede_gestionar_clientes(user: Usuario | None) -> bool:
    """Crear clientes, editar sus datos, su direccion, su foto, su ubicacion.

    Una ficha de cliente es el expediente de una deuda: quien es, donde vive
    y como se le encuentra. Cambiarlo desde la calle, con prisa y sin
    supervision, es como se pierde la direccion de alguien que debe dinero.
    """
    return es_admin(user)


def puede_gestionar_prestamos(user: Usuario | None) -> bool:
    """Crear o modificar prestamos. El cobrador recoge, no presta."""
    return es_admin(user)


def puede_gestionar_usuarios(user: Usuario | None) -> bool:
    return es_admin(user)


def puede_gestionar_zonas(user: Usuario | None) -> bool:
    return es_admin(user)


def puede_ver_reportes(user: Usuario | None) -> bool:
    """Los informes de la empresa, incluidas las descargas de Excel.

    Filtran por zona, asi que un cobrador no veia datos ajenos, pero un
    listado descargable de la cartera no es algo que necesite para trabajar
    y si es algo que puede acabar fuera.
    """
    return es_admin(user)


def puede_ver_whatsapp(user: Usuario | None) -> bool:
    return es_admin(user)


def puede_registrar_cobros(user: Usuario | None) -> bool:
    """Lo que el cobrador si hace. Tambien el admin, que cobra cuando toca."""
    return bool(user)


def puede_escribir_notas(user: Usuario | None) -> bool:
    """Dejar un aviso sobre un cliente. La unica escritura que le queda.

    Es deliberado y es lo que hace viable el resto de restricciones: si el
    cobrador no puede corregir la ficha, necesita poder decir que hay que
    corregirla. La nota no cambia ningun dato, solo deja constancia.
    """
    return bool(user)


def puede_atender_notas(user: Usuario | None) -> bool:
    """Marcar una nota como resuelta. Quien la resuelve es quien corrige."""
    return es_admin(user)


def puede_ver_cuadre_de(user: Usuario | None, usuario_id: int) -> bool:
    """El cuadre de caja: el cobrador ve el suyo, el admin ve el de todos.

    Que el cobrador vea el suyo es deliberado y es lo que hace util el
    cuadre: si solo lo viera el administrador, el cobrador se enteraria de
    que va descuadrado cuando ya no puede reconstruir el dia.
    """
    if not user:
        return False
    return es_admin(user) or user.id == usuario_id


def puede_registrar_movimientos_caja(user: Usuario | None) -> bool:
    """Anotar la base, la entrega del dia o una correccion.

    Solo el administrador. Un cobrador que pueda escribir su propia base
    puede hacerse cuadrar cualquier dia: seria pedirle la cuenta a quien la
    rinde. El cobrador ve su caja, no la escribe.
    """
    return es_admin(user)
