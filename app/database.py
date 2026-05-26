"""
CreditosPro v2.1 - Database Multi-tenant
Cada Empresa tiene datos completamente aislados.
Unique constraints son POR empresa, no globales.
"""
import datetime
import logging
import os
from pathlib import Path

from sqlalchemy import (
    create_engine, Column, Integer, String, Float, Numeric, Date,
    DateTime, Boolean, Text, ForeignKey, UniqueConstraint, Index, Table
)
from sqlalchemy.orm import DeclarativeBase, sessionmaker, relationship
from sqlalchemy.sql import func

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).parent.parent

# ── Conexión a Base de Datos ────────────────────────────────────────────────────
# La URL debe estar en la variable de entorno DATABASE_URL
# NUNCA hardcodear credenciales en el código fuente
SQLALCHEMY_DATABASE_URL = os.getenv("DATABASE_URL")

if not SQLALCHEMY_DATABASE_URL:
    raise EnvironmentError(
        "La variable de entorno DATABASE_URL no está configurada. "
        "Crea un archivo .env a partir de .env.example"
    )

# Normalizar URL de PostgreSQL
if SQLALCHEMY_DATABASE_URL.startswith("postgres://"):
    SQLALCHEMY_DATABASE_URL = SQLALCHEMY_DATABASE_URL.replace("postgres://", "postgresql://", 1)

# Detectar si es SQLite para desarrollo local
IS_SQLITE = SQLALCHEMY_DATABASE_URL.startswith("sqlite://")

# Configuración del engine según el tipo de base de datos
connect_args = {}
engine_kwargs = {"pool_pre_ping": True}
if IS_SQLITE:
    # SQLite necesita check_same_thread=False para usar en hilos
    connect_args = {"check_same_thread": False}
    logger.info("Usando SQLite (modo desarrollo)")
else:
    logger.info("Usando PostgreSQL (producción)")
    engine_kwargs.update({
        "pool_recycle": 300,
        "pool_size": 5,
        "max_overflow": 10,
    })

engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args=connect_args,
    **engine_kwargs,
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


usuario_zonas = Table(
    "usuario_zonas",
    Base.metadata,
    Column("usuario_id", Integer, ForeignKey("usuarios.id", ondelete="CASCADE"), primary_key=True),
    Column("zona_id", Integer, ForeignKey("zonas.id", ondelete="CASCADE"), primary_key=True),
    Index("ix_usuario_zonas_zona_id", "zona_id"),
)


class Empresa(Base):
    __tablename__ = "empresas"
    id = Column(Integer, primary_key=True, index=True)
    nombre = Column(String(200), nullable=False)
    nit = Column(String(50), nullable=True)
    telefono = Column(String(20), nullable=True)
    direccion = Column(String(300), nullable=True)
    ciudad = Column(String(100), default="Medellín")
    pais = Column(String(100), default="Colombia")
    moneda = Column(String(10), default="COP")
    logo_path = Column(String(300), nullable=True)
    activa = Column(Boolean, default=True)
    plan = Column(String(50), default="basico")
    creado = Column(DateTime, default=func.now())

    usuarios = relationship("Usuario", back_populates="empresa", cascade="all, delete-orphan")
    zonas = relationship("Zona", back_populates="empresa", cascade="all, delete-orphan")
    clientes = relationship("Cliente", back_populates="empresa", cascade="all, delete-orphan")
    configuracion = relationship("ConfiguracionApp", back_populates="empresa", uselist=False)


class Usuario(Base):
    __tablename__ = "usuarios"
    id = Column(Integer, primary_key=True, index=True)
    empresa_id = Column(Integer, ForeignKey("empresas.id"), nullable=False, index=True)
    username = Column(String(100), nullable=False, index=True)
    nombre = Column(String(200), nullable=False)
    email = Column(String(200), nullable=True)
    password_hash = Column(String(500), nullable=False)
    rol = Column(String(50), default="cobrador")
    activo = Column(Boolean, default=True)
    zona_id = Column(Integer, ForeignKey("zonas.id"), nullable=True)
    ultimo_login = Column(DateTime, nullable=True)
    creado = Column(DateTime, default=func.now())

    empresa = relationship("Empresa", back_populates="usuarios")
    zonas_asignadas = relationship("Zona", secondary=usuario_zonas, back_populates="usuarios_asignados")
    __table_args__ = (UniqueConstraint("empresa_id", "username", name="uq_user_empresa"),)


class Zona(Base):
    __tablename__ = "zonas"
    id = Column(Integer, primary_key=True, index=True)
    empresa_id = Column(Integer, ForeignKey("empresas.id"), nullable=False, index=True)
    codigo = Column(String(50), nullable=False)
    nombre = Column(String(100), nullable=False)
    ciudad = Column(String(100), default="Medellín")
    departamento = Column(String(100), default="Antioquia")
    pais = Column(String(100), default="Colombia")
    cobrador_nombre = Column(String(200))
    cobrador_tel = Column(String(20))
    cobrador_moto = Column(String(50))
    activa = Column(Boolean, default=True)
    # CallMeBot por zona
    bot_phone = Column(String(20), nullable=True)
    bot_apikey = Column(String(100), nullable=True)
    bot_activo = Column(Boolean, default=False)
    lat = Column(Float, nullable=True)
    lng = Column(Float, nullable=True)
    creado = Column(DateTime, default=func.now())

    empresa = relationship("Empresa", back_populates="zonas")
    clientes = relationship("Cliente", back_populates="zona_rel")
    usuarios_asignados = relationship("Usuario", secondary=usuario_zonas, back_populates="zonas_asignadas")
    __table_args__ = (UniqueConstraint("empresa_id", "codigo", name="uq_zona_empresa"),)


class Cliente(Base):
    __tablename__ = "clientes"
    id = Column(Integer, primary_key=True, index=True)
    empresa_id = Column(Integer, ForeignKey("empresas.id"), nullable=False, index=True)
    cedula = Column(String(20), nullable=False, index=True)
    nombre = Column(String(200), nullable=False)
    telefono = Column(String(20), nullable=False)
    telefono2 = Column(String(20), nullable=True)
    whatsapp = Column(String(20), nullable=True)
    direccion = Column(String(300))
    barrio = Column(String(100))
    zona_id = Column(Integer, ForeignKey("zonas.id"))
    foto_path = Column(String(300), nullable=True)
    lat = Column(Float, nullable=True)
    lng = Column(Float, nullable=True)
    codeudor_nombre = Column(String(200), nullable=True)
    codeudor_cedula = Column(String(20), nullable=True)
    codeudor_tel = Column(String(20), nullable=True)
    tipo_cliente = Column(String(50), default="Regular")
    activo = Column(Boolean, default=True)
    creado = Column(DateTime, default=func.now())
    actualizado = Column(DateTime, default=func.now(), onupdate=func.now())

    empresa = relationship("Empresa", back_populates="clientes")
    zona_rel = relationship("Zona", back_populates="clientes")
    prestamos = relationship("Prestamo", back_populates="cliente")
    __table_args__ = (UniqueConstraint("empresa_id", "cedula", name="uq_cliente_empresa"),)


class Prestamo(Base):
    __tablename__ = "prestamos"
    id = Column(Integer, primary_key=True, index=True)
    empresa_id = Column(Integer, ForeignKey("empresas.id"), nullable=False, index=True)
    cliente_id = Column(Integer, ForeignKey("clientes.id"), nullable=False)
    zona_id = Column(Integer, ForeignKey("zonas.id"), nullable=False)
    capital = Column(Numeric(12, 2), nullable=False)
    tasa_interes = Column(Numeric(5, 2), default=20.0)
    interes_total = Column(Numeric(12, 2))
    total_pagar = Column(Numeric(12, 2))
    num_cuotas = Column(Integer, nullable=False)
    valor_cuota = Column(Numeric(12, 2))
    plazo_dias = Column(Integer, default=30)
    fecha_inicio = Column(Date, default=datetime.date.today)
    fecha_fin = Column(Date)
    estado = Column(String(30), default="Activo")
    cobrador = Column(String(200))
    observaciones = Column(Text, nullable=True)
    creado = Column(DateTime, default=func.now())

    cliente = relationship("Cliente", back_populates="prestamos")
    cuotas = relationship("Cuota", back_populates="prestamo", cascade="all, delete-orphan")
    __table_args__ = (
        Index("ix_prestamos_empresa_cliente", "empresa_id", "cliente_id"),
        Index("ix_prestamos_empresa_zona_estado", "empresa_id", "zona_id", "estado"),
    )


class Cuota(Base):
    __tablename__ = "cuotas"
    id = Column(Integer, primary_key=True, index=True)
    empresa_id = Column(Integer, ForeignKey("empresas.id"), nullable=False, index=True)
    prestamo_id = Column(Integer, ForeignKey("prestamos.id"), nullable=False)
    numero = Column(Integer, nullable=False)
    valor = Column(Numeric(12, 2), nullable=False)
    fecha_vencimiento = Column(Date, nullable=False)
    fecha_pago = Column(Date, nullable=True)
    valor_pagado = Column(Numeric(12, 2), default=0.0, nullable=False)
    estado = Column(String(20), default="Pendiente")
    notificado_wp = Column(Boolean, default=False)
    creado = Column(DateTime, default=func.now())

    prestamo = relationship("Prestamo", back_populates="cuotas")
    __table_args__ = (
        Index("ix_cuotas_empresa_prestamo_estado", "empresa_id", "prestamo_id", "estado"),
        Index("ix_cuotas_empresa_estado_vencimiento", "empresa_id", "estado", "fecha_vencimiento"),
    )


class Cobro(Base):
    __tablename__ = "cobros"
    id = Column(Integer, primary_key=True, index=True)
    empresa_id = Column(Integer, ForeignKey("empresas.id"), nullable=False, index=True)
    cuota_id = Column(Integer, ForeignKey("cuotas.id"), nullable=False)
    prestamo_id = Column(Integer, ForeignKey("prestamos.id"), nullable=False)
    cliente_id = Column(Integer, ForeignKey("clientes.id"), nullable=False)
    zona_id = Column(Integer, ForeignKey("zonas.id"), nullable=False)
    valor_cobrado = Column(Numeric(12, 2), nullable=False)
    fecha = Column(Date, default=datetime.date.today)
    hora = Column(DateTime, default=func.now())
    cobrador = Column(String(200))
    metodo_pago = Column(String(50), default="Efectivo")
    observaciones = Column(Text, nullable=True)
    lat_cobro = Column(Float, nullable=True)
    lng_cobro = Column(Float, nullable=True)
    usuario_id = Column(Integer, ForeignKey("usuarios.id"), nullable=True)
    __table_args__ = (
        Index("ix_cobros_empresa_fecha", "empresa_id", "fecha"),
        Index("ix_cobros_empresa_cliente", "empresa_id", "cliente_id"),
        Index("ix_cobros_empresa_prestamo", "empresa_id", "prestamo_id"),
    )


class NotificacionWP(Base):
    __tablename__ = "notificaciones_wp"
    id = Column(Integer, primary_key=True, index=True)
    empresa_id = Column(Integer, ForeignKey("empresas.id"), nullable=False, index=True)
    cliente_id = Column(Integer, ForeignKey("clientes.id"), nullable=False)
    cuota_id = Column(Integer, ForeignKey("cuotas.id"), nullable=True)
    telefono = Column(String(20), nullable=False)
    mensaje = Column(Text, nullable=False)
    estado = Column(String(20), default="Pendiente")
    tipo = Column(String(50), default="Recordatorio")
    enviado_at = Column(DateTime, nullable=True)
    creado = Column(DateTime, default=func.now())


class ConfiguracionApp(Base):
    __tablename__ = "configuracion"
    id = Column(Integer, primary_key=True, index=True)
    empresa_id = Column(Integer, ForeignKey("empresas.id"), nullable=False, unique=True, index=True)
    empresa_nombre = Column(String(200), default="CreditosPro")
    empresa_nit = Column(String(50), nullable=True)
    empresa_tel = Column(String(20), nullable=True)
    empresa_dir = Column(String(300), nullable=True)
    pais = Column(String(100), default="Colombia")
    moneda = Column(String(10), default="COP")
    tasa_default = Column(Numeric(5, 2), default=20.0)
    cuotas_default = Column(Integer, default=30)
    dias_aviso_vencimiento = Column(Integer, default=2)
    dias_mora = Column(Integer, default=1)
    wp_api_key = Column(String(500), nullable=True)
    wp_phone_id = Column(String(200), nullable=True)
    wp_token = Column(String(500), nullable=True)
    wp_activo = Column(Boolean, default=False)
    wp_mensaje_recordatorio = Column(Text, default="Hola {nombre}, su cuota #{num_cuota} de ${valor} vence el {fecha}. — {empresa}")
    wp_mensaje_vencida = Column(Text, default="Hola {nombre}, su cuota #{num_cuota} de ${valor} venció el {fecha}. — {empresa}")

    empresa = relationship("Empresa", back_populates="configuracion")


def init_db():
    """Inicializa las tablas en la base de datos. Idempotente."""
    auto_create = os.getenv("AUTO_CREATE_TABLES", "1").strip().lower() in {"1", "true", "yes", "on"}
    if not auto_create:
        logger.info("AUTO_CREATE_TABLES=0; se omite Base.metadata.create_all")
        return
    try:
        Base.metadata.create_all(bind=engine)
        logger.info("Base de datos inicializada correctamente")
    except Exception as e:
        logger.error(f"Error al inicializar la base de datos: {e}")
        raise


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
