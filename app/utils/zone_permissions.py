from sqlalchemy.orm import Session

from app.database import RutaCobro, Usuario, Zona, dia_semana_local


ADMIN_ROLES = {"admin", "superadmin"}

# Cuantas zonas puede recorrer un cobrador en un mismo dia.
MAX_ZONAS_POR_DIA = 3

DIAS_SEMANA = ("Lunes", "Martes", "Miercoles", "Jueves", "Viernes", "Sabado", "Domingo")


def zonas_asignadas_ids(user: Usuario) -> list[int]:
    """Todas las zonas del usuario, sin mirar el dia."""
    ids = [z.id for z in getattr(user, "zonas_asignadas", []) if z.empresa_id == user.empresa_id and z.activa]
    if user.zona_id and user.zona_id not in ids:
        ids.append(user.zona_id)
    return ids


def ruta_semanal(db: Session, usuario_id: int) -> dict[int, list[int]]:
    """{dia_semana: [zona_id, ...]} configurado para ese usuario."""
    filas = (
        db.query(RutaCobro.dia_semana, RutaCobro.zona_id)
        .filter(RutaCobro.usuario_id == usuario_id)
        .all()
    )
    ruta: dict[int, list[int]] = {}
    for dia, zona_id in filas:
        ruta.setdefault(dia, []).append(zona_id)
    return ruta


def get_allowed_zone_ids(db: Session, user: Usuario) -> list[int] | None:
    """Zonas que este usuario puede ver y cobrar AHORA.

    Un administrador las ve todas (None). Un cobrador ve sus zonas asignadas,
    salvo que tenga una ruta semanal configurada: entonces solo las zonas que
    le tocan hoy. Si tiene ruta pero hoy no le toca ninguna, no ve ninguna.

    Sin ruta configurada no se restringe nada, para que activar esta funcion
    no deje de golpe sin trabajo a los cobradores que ya existian.
    """
    if user.rol in ADMIN_ROLES:
        return None

    asignadas = zonas_asignadas_ids(user)

    # Una peticion puede preguntar esto varias veces; la ruta no cambia
    # dentro de la misma peticion, asi que se resuelve una sola vez.
    cache = getattr(user, "_ruta_hoy_cache", None)
    if cache is None:
        ruta = ruta_semanal(db, user.id)
        cache = (ruta, dia_semana_local())
        try:
            user._ruta_hoy_cache = cache
        except Exception:
            pass
    ruta, hoy = cache

    if not ruta:
        return asignadas

    permitidas = ruta.get(hoy, [])
    # La ruta nunca puede ampliar los permisos: si al cobrador le quitaron
    # una zona, el dia que la tenia en la ruta tampoco puede entrar.
    return [z for z in permitidas if z in asignadas]


def require_zone_access(db: Session, user: Usuario, zona_id: int) -> bool:
    allowed = get_allowed_zone_ids(db, user)
    return allowed is None or zona_id in allowed


def visible_zonas_query(db: Session, user: Usuario):
    query = db.query(Zona).filter(Zona.empresa_id == user.empresa_id, Zona.activa == True)
    allowed = get_allowed_zone_ids(db, user)
    if allowed is not None:
        if not allowed:
            return query.filter(Zona.id == -1)
        query = query.filter(Zona.id.in_(allowed))
    return query


def validate_user_zones(db: Session, empresa_id: int, zona_ids: list[int]) -> list[Zona]:
    clean_ids = []
    for zid in zona_ids:
        if zid not in clean_ids:
            clean_ids.append(zid)
    if len(clean_ids) > 5:
        raise ValueError("Un cobrador puede tener maximo 5 zonas")

    zonas = db.query(Zona).filter(
        Zona.empresa_id == empresa_id,
        Zona.id.in_(clean_ids),
        Zona.activa == True,
    ).all() if clean_ids else []
    if len(zonas) != len(clean_ids):
        raise ValueError("Una o mas zonas no existen o estan inactivas")
    return zonas
