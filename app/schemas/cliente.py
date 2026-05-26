from typing import Optional

from pydantic import BaseModel, Field


class ClienteBase(BaseModel):
    cedula: str = Field(min_length=4, max_length=20)
    nombre: str = Field(min_length=2, max_length=200)
    telefono: str = Field(min_length=7, max_length=20)
    whatsapp: Optional[str] = Field(default=None, max_length=20)
    zona_id: int
    direccion: Optional[str] = Field(default=None, max_length=300)
    barrio: Optional[str] = Field(default=None, max_length=100)
    tipo_cliente: str = Field(default="Regular", max_length=50)


class ClienteCreate(ClienteBase):
    pass


class ClienteUpdate(BaseModel):
    nombre: str = Field(min_length=2, max_length=200)
    telefono: str = Field(min_length=7, max_length=20)
    whatsapp: Optional[str] = Field(default=None, max_length=20)
    zona_id: int
    direccion: Optional[str] = Field(default=None, max_length=300)
    barrio: Optional[str] = Field(default=None, max_length=100)
    tipo_cliente: str = Field(default="Regular", max_length=50)
