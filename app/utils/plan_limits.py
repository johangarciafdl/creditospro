"""Limites y funciones habilitadas segun el plan comercial de la empresa.

El plan (Empresa.plan) define el limite de cobradores por defecto.
WhatsApp ya NO depende del plan: en el modelo de venta actual (propuesta
anual) es un adicional que se cobra aparte por cobrador conectado, sin
importar si la empresa es basico, medio o alto -- por eso los tres
planes traen whatsapp=False por defecto. La unica forma de activarlo es
la excepcion puntual (Empresa.overrides), que el superadmin enciende
desde /plataforma para cada cobrador/empresa que sí pagó el adicional.

Empresa.overrides tambien sirve para lo contrario: bloquear una funcion a
una empresa que dejo de pagar, sin tener que bajarle el plan completo.

Agregar una funcion nueva al sistema: solo hace falta agregar su nombre
en PLAN_DEFAULTS (con su valor por cada plan) -- tiene_funcion()/
limite() ya la resuelven automaticamente, incluido el override.
"""
from __future__ import annotations

PLANES_VALIDOS = ("basico", "medio", "alto")

# None en max_cobradores significa "sin limite". whatsapp siempre en False:
# ver nota arriba, ya no es una funcion de plan sino un adicional aparte.
PLAN_DEFAULTS: dict[str, dict] = {
    "basico": {"max_cobradores": 2, "whatsapp": False},
    "medio": {"max_cobradores": 6, "whatsapp": False},
    "alto": {"max_cobradores": None, "whatsapp": False},
}

# Valor por defecto para un plan que no es ninguno de los tres anteriores
# (ej. "trial", el valor que tenian las empresas creadas antes de este
# sistema). Deliberadamente sin restricciones: una empresa que ya operaba
# no debe perder acceso de golpe solo porque este sistema se activo.
_SIN_RESTRICCION = {"max_cobradores": None, "whatsapp": True}


def _defaults_para(plan: str | None) -> dict:
    return PLAN_DEFAULTS.get(plan or "", _SIN_RESTRICCION)


def tiene_funcion(empresa, funcion: str) -> bool:
    """True si la empresa tiene acceso a `funcion` (ej. "whatsapp")."""
    overrides = empresa.overrides or {}
    if funcion in overrides:
        return bool(overrides[funcion])
    return bool(_defaults_para(empresa.plan).get(funcion, True))


def limite_cobradores(empresa) -> int | None:
    """Maximo de usuarios cobrador/supervisor activos. None = sin limite."""
    overrides = empresa.overrides or {}
    if "max_cobradores" in overrides and overrides["max_cobradores"] is not None:
        return overrides["max_cobradores"]
    return _defaults_para(empresa.plan).get("max_cobradores")
