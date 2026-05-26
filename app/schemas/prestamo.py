from datetime import date
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, Field


class PrestamoCreate(BaseModel):
    cliente_id: int
    zona_id: int
    capital: Decimal = Field(gt=0, max_digits=12, decimal_places=2)
    tasa_interes: Decimal = Field(default=Decimal("20.00"), ge=0, le=200, max_digits=5, decimal_places=2)
    num_cuotas: int = Field(ge=1, le=365)
    plazo_dias: int = Field(default=1, ge=1, le=365)
    fecha_inicio: Optional[date] = None
    observaciones: Optional[str] = Field(default=None, max_length=1000)
