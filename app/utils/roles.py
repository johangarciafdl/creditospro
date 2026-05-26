ALLOWED_ROLES = {"admin", "superadmin", "supervisor", "cobrador"}


def normalize_role(role: str, default: str = "cobrador") -> str:
    value = (role or default).strip().lower()
    if value not in ALLOWED_ROLES:
        raise ValueError("Rol no permitido")
    return value
