"""
CreditosPro Cloud - Database
PostgreSQL (Supabase) + Multi-tenant por empresa
"""

import os
from sqlalchemy import create_engine, Column, Integer, String, Float, Date, DateTime, Boolean, Text, ForeignKey
from sqlalchemy.orm import DeclarativeBase, sessionmaker, relationship
from sqlalchemy.sql import func
import datetime

# ── CONNECTION STRING ─────────────────────────────────────────────────────────
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://postgres:Jo681192*creditos@db.ivhcmdxwmeabwmnmjuhm.supabase.co:5432/postgres"
)

# Railway a veces entrega postgres:// en vez de postgresql://
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

engine = create_engine(DATABASE_URL, pool_pre_ping=True, pool_recycle=300)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


# ── MODELOS ───────────────────────────────────────────────────────────────────

class Empresa(Base):
    __tablename__ = "empresas"
    id             = Column(Integer, primary_key=True, index=True)
    nombre         = Column(String(200), nullable=False)
    nit            = Column(String(20), nullable=True)
    direccion      = Column(String(300), nullable=True)
    telefono       = Column(String(20), nullable=True)
    email          = Column(String(200), nullable=True)
    plan           = Column(String(20), default="trial")   # trial, basic, pro
    activo         = Column(Boolean, default=True)
    setup_completo = Column(Boolean, default=False)
    creado         = Column(DateTime, default=func.now())

    usuarios  = relationship("Usuario", back_populates="empresa_rel")
    zonas     = relationship("Zona",    back_populates="empresa_rel")
    clientes  = relationship("Cliente", back_populates="empresa_rel")


class Usuario(Base):
    __tablename__ = "usuarios"
    id              = Column(Integer, primary_key=True, index=True)
    empresa_id      = Column(Integer, ForeignKey("empresas.id"), nullable=False)
    username        = Column(String(50), unique=True, nullable=False, index=True)
    nombre_completo = Column(String(200), nullable=False)
    email           = Column(String(200), nullable=True)
    password_hash   = Column(String(300), nullable=False)
    rol             = Column(String(30), default="cobrador")  # admin, cobrador, viewer
    zona_id         = Column(Integer, ForeignKey("zonas.id"), nullable=True)
    activo          = Column(Boolean, default=True)
    ultimo_login    = Column(DateTime, nullable=True)
    creado          = Column(DateTime, default=func.now())

    empresa_rel = relationship("Empresa", back_populates="usuarios")
    zona_rel    = relationship("Zona", foreign_keys=[zona_id])


class Zona(Base):
    __tablename__ = "zonas"
    id              = Column(Integer, primary_key=True, index=True)
    empresa_id      = Column(Integer, ForeignKey("empresas.id"), nullable=False)
    codigo          = Column(String(50), nullable=False)
    nombre          = Column(String(100), nullable=False)
    ciudad          = Column(String(100), default="Medellín")
    departamento    = Column(String(100), default="Antioquia")
    pais            = Column(String(100), default="Colombia")
    cobrador_nombre = Column(String(200))
    cobrador_tel    = Column(String(20))
    cobrador_moto   = Column(String(50))
    activa          = Column(Boolean, default=True)
    lat             = Column(Float, nullable=True)
    lng             = Column(Float, nullable=True)
    creado          = Column(DateTime, default=func.now())

    empresa_rel = relationship("Empresa", back_populates="zonas")
    clientes    = relationship("Cliente", back_populates="zona_rel")


class Cliente(Base):
    __tablename__ = "clientes"
    id               = Column(Integer, primary_key=True, index=True)
    empresa_id       = Column(Integer, ForeignKey("empresas.id"), nullable=False)
    cedula           = Column(String(20), nullable=False, index=True)
    nombre           = Column(String(200), nullable=False)
    telefono         = Column(String(20), nullable=False)
    whatsapp         = Column(String(20), nullable=True)
    direccion        = Column(String(300))
    barrio           = Column(String(100))
    zona_id          = Column(Integer, ForeignKey("zonas.id"))
    foto_path        = Column(String(300), nullable=True)
    lat              = Column(Float, nullable=True)
    lng              = Column(Float, nullable=True)
    codeudor_nombre  = Column(String(200), nullable=True)
    codeudor_cedula  = Column(String(20), nullable=True)
    codeudor_tel     = Column(String(20), nullable=True)
    tipo_cliente     = Column(String(50), default="Regular")
    activo           = Column(Boolean, default=True)
    creado           = Column(DateTime, default=func.now())

    empresa_rel = relationship("Empresa", back_populates="clientes")
    zona_rel    = relationship("Zona", back_populates="clientes")
    prestamos   = relationship("Prestamo", back_populates="cliente")


class Prestamo(Base):
    __tablename__ = "prestamos"
    id            = Column(Integer, primary_key=True, index=True)
    empresa_id    = Column(Integer, ForeignKey("empresas.id"), nullable=False)
    cliente_id    = Column(Integer, ForeignKey("clientes.id"), nullable=False)
    zona_id       = Column(Integer, ForeignKey("zonas.id"), nullable=False)
    capital       = Column(Float, nullable=False)
    tasa_interes  = Column(Float, default=20.0)
    interes_total = Column(Float)
    total_pagar   = Column(Float)
    num_cuotas    = Column(Integer, nullable=False)
    valor_cuota   = Column(Float)
    plazo_dias    = Column(Integer, default=30)
    fecha_inicio  = Column(Date, default=datetime.date.today)
    fecha_fin     = Column(Date)
    estado        = Column(String(30), default="Activo")
    cobrador      = Column(String(200))
    observaciones = Column(Text, nullable=True)
    creado        = Column(DateTime, default=func.now())

    empresa_rel = relationship("Empresa")
    cliente     = relationship("Cliente", back_populates="prestamos")
    cuotas      = relationship("Cuota", back_populates="prestamo", cascade="all, delete-orphan")


class Cuota(Base):
    __tablename__ = "cuotas"
    id                 = Column(Integer, primary_key=True, index=True)
    empresa_id         = Column(Integer, ForeignKey("empresas.id"), nullable=False)
    prestamo_id        = Column(Integer, ForeignKey("prestamos.id"), nullable=False)
    numero             = Column(Integer, nullable=False)
    valor              = Column(Float, nullable=False)
    fecha_vencimiento  = Column(Date, nullable=False)
    fecha_pago         = Column(Date, nullable=True)
    valor_pagado       = Column(Float, default=0.0)
    estado             = Column(String(20), default="Pendiente")
    creado             = Column(DateTime, default=func.now())

    empresa_rel = relationship("Empresa")
    prestamo    = relationship("Prestamo", back_populates="cuotas")


class Cobro(Base):
    __tablename__ = "cobros"
    id            = Column(Integer, primary_key=True, index=True)
    empresa_id    = Column(Integer, ForeignKey("empresas.id"), nullable=False)
    cuota_id      = Column(Integer, ForeignKey("cuotas.id"), nullable=False)
    prestamo_id   = Column(Integer, ForeignKey("prestamos.id"), nullable=False)
    cliente_id    = Column(Integer, ForeignKey("clientes.id"), nullable=False)
    zona_id       = Column(Integer, ForeignKey("zonas.id"), nullable=False)
    valor_cobrado = Column(Float, nullable=False)
    fecha         = Column(Date, default=datetime.date.today)
    hora          = Column(DateTime, default=func.now())
    cobrador      = Column(String(200))
    usuario_id    = Column(Integer, ForeignKey("usuarios.id"), nullable=True)
    metodo_pago   = Column(String(50), default="Efectivo")
    observaciones = Column(Text, nullable=True)
    foto_novedad  = Column(String(300), nullable=True)
    lat_cobro     = Column(Float, nullable=True)
    lng_cobro     = Column(Float, nullable=True)
    creado        = Column(DateTime, default=func.now())


# ── HELPERS ──────────────────────────────────────────────────────────────────

def init_db():
    Base.metadata.create_all(bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
