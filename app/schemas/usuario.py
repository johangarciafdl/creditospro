from typing import Optional

from pydantic import BaseModel, Field, field_validator

from app.utils.roles import normalize_role


class UsuarioCreate(BaseModel):
    username: str = Field(min_length=3, max_length=100)
    nombre: str = Field(min_length=2, max_length=200)
    password: str = Field(min_length=6, max_length=128)
    rol: str = "cobrador"
    zona_id: Optional[int] = None

    @field_validator("username")
    @classmethod
    def clean_username(cls, value: str) -> str:
        return value.strip().lower()

    @field_validator("nombre")
    @classmethod
    def clean_nombre(cls, value: str) -> str:
        return value.strip()

    @field_validator("rol")
    @classmethod
    def clean_rol(cls, value: str) -> str:
        return normalize_role(value)


class UsuarioUpdate(BaseModel):
    nombre: str = Field(min_length=2, max_length=200)
    rol: str = "cobrador"
    zona_id: Optional[int] = None
    password: Optional[str] = Field(default=None, min_length=6, max_length=128)
    activo: bool = True

    @field_validator("nombre")
    @classmethod
    def clean_nombre(cls, value: str) -> str:
        return value.strip()

    @field_validator("rol")
    @classmethod
    def clean_rol(cls, value: str) -> str:
        return normalize_role(value)
