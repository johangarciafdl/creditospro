from sqlalchemy.orm import Session

from app.database import Usuario, Zona


ADMIN_ROLES = {"admin", "superadmin"}


def get_allowed_zone_ids(db: Session, user: Usuario) -> list[int] | None:
    if user.rol in ADMIN_ROLES:
        return None

    ids = [z.id for z in getattr(user, "zonas_asignadas", []) if z.empresa_id == user.empresa_id and z.activa]
    if user.zona_id and user.zona_id not in ids:
        ids.append(user.zona_id)
    return ids


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
