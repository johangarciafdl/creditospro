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
    DateTime, Boolean, Text, JSON, ForeignKey, UniqueConstraint, Index, Table,
    CheckConstraint, event, text,
)
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker, relationship
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


def _engine_kwargs_for(url: str) -> tuple[dict, dict]:
    """connect_args/engine_kwargs correctos segun el dialecto de esa URL
    especifica (DATABASE_URL y DATABASE_URL_APP pueden ser dialectos
    distintos, p.ej. sqlite en tests + postgres real)."""
    if url.startswith("sqlite://"):
        # SQLite necesita check_same_thread=False para usar en hilos
        return {"check_same_thread": False}, {"pool_pre_ping": True}
    return {}, {"pool_pre_ping": True, "pool_recycle": 300, "pool_size": 5, "max_overflow": 10}


connect_args, engine_kwargs = _engine_kwargs_for(SQLALCHEMY_DATABASE_URL)
logger.info("Usando SQLite (modo desarrollo)" if IS_SQLITE else "Usando PostgreSQL (producción)")

engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args=connect_args,
    **engine_kwargs,
)
# SessionLocal es la conexion "sistema": rol de BD privilegiado (hoy el owner),
# usado por el scheduler, auditoria, licencias y los pocos endpoints que
# legitimamente necesitan ver mas de una empresa antes de haber autenticado
# a nadie (selector de empresa, activacion de licencia, registro de empresa
# nueva). NO se expone via Depends(get_db) a las rutas normales.
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# ── Conexión de aplicación (RLS) ──────────────────────────────────────────────
# DATABASE_URL_APP es opcional: un rol de Postgres restringido (sin BYPASSRLS)
# para que las consultas por-empresa tengan un respaldo real de aislamiento a
# nivel de base de datos, ademas del filtro por empresa_id en el codigo. Si no
# esta configurada, get_db() usa la misma conexion privilegiada de siempre
# (comportamiento identico al actual, sin romper despliegues existentes).
APP_DATABASE_URL = os.getenv("DATABASE_URL_APP", "").strip()
if APP_DATABASE_URL.startswith("postgres://"):
    APP_DATABASE_URL = APP_DATABASE_URL.replace("postgres://", "postgresql://", 1)

if APP_DATABASE_URL and APP_DATABASE_URL != SQLALCHEMY_DATABASE_URL:
    app_connect_args, app_engine_kwargs = _engine_kwargs_for(APP_DATABASE_URL)
    app_engine = create_engine(
        APP_DATABASE_URL,
        connect_args=app_connect_args,
        **app_engine_kwargs,
    )
    AppSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=app_engine)
    logger.info("DATABASE_URL_APP configurada: consultas por-empresa usan el rol restringido")
else:
    AppSessionLocal = SessionLocal


def set_tenant_context(db: Session, empresa_id: int) -> None:
    """Fija el tenant para RLS usando solo un ID validado por autenticacion."""
    if not isinstance(empresa_id, int) or empresa_id <= 0:
        raise ValueError("empresa_id invalido para contexto RLS")
    db.info["empresa_id"] = empresa_id


@event.listens_for(Session, "after_begin")
def apply_rls_context(session: Session, transaction, connection) -> None:
    """Aplica el tenant a cada transaccion cuando RLS esta habilitado."""
    from app.utils.settings import settings

    empresa_id = session.info.get("empresa_id")
    if settings.ENABLE_DATABASE_RLS and empresa_id is not None and not IS_SQLITE:
        connection.execute(
            text("SELECT set_config('app.empresa_id', :empresa_id, true)"),
            {"empresa_id": str(empresa_id)},
        )


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
    # Plan comercial: "basico" | "medio" | "alto" (ver app/utils/plan_limits.py).
    # Un valor fuera de esos tres (ej. "trial", el valor historico antes de
    # este sistema) no aplica ninguna restriccion -- evita romper de golpe
    # el acceso de una empresa que ya operaba antes de que el plan existiera.
    plan = Column(String(50), default="basico")
    # Overrides puntuales por empresa (ej. {"whatsapp": true, "max_cobradores": 5}).
    # Tienen prioridad sobre el default del plan; los pone el dueño de la
    # plataforma (superadmin) para activar/desactivar una funcion especifica
    # sin cambiarle el plan completo a la empresa.
    overrides = Column(JSON, nullable=True)
    activation_key_hash = Column(String(64), nullable=True, unique=True, index=True)
    activation_key_hint = Column(String(24), nullable=True)
    activation_enabled = Column(Boolean, default=True, nullable=False)
    creado = Column(DateTime, default=func.now())

    usuarios = relationship("Usuario", back_populates="empresa", cascade="all, delete-orphan")
    zonas = relationship("Zona", back_populates="empresa", cascade="all, delete-orphan")
    clientes = relationship("Cliente", back_populates="empresa", cascade="all, delete-orphan")
    configuracion = relationship("ConfiguracionApp", back_populates="empresa", uselist=False)


class Usuario(Base):
    __tablename__ = "usuarios"
    id = Column(Integer, primary_key=True, index=True)
    # Nullable solo para el superadmin de la plataforma (rol='superadmin'):
    # esa cuenta administra TODAS las empresas, no pertenece a ninguna --
    # ver app/routers/plataforma.py y la nota en get_current_user().
    empresa_id = Column(Integer, ForeignKey("empresas.id"), nullable=True, index=True)
    username = Column(String(100), nullable=False, index=True)
    nombre = Column(String(200), nullable=False)
    email = Column(String(200), nullable=True)
    password_hash = Column(String(500), nullable=False)
    rol = Column(String(50), default="cobrador")
    activo = Column(Boolean, default=True)
    zona_id = Column(Integer, ForeignKey("zonas.id", ondelete="SET NULL"), nullable=True)
    ultimo_login = Column(DateTime, nullable=True)
    two_factor_enabled = Column(Boolean, default=False, nullable=False)
    two_factor_secret = Column(Text, nullable=True)
    two_factor_backup_hashes = Column(Text, nullable=True)
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
    # Green API por zona: bot_phone = instance_id, bot_apikey = token (nombres heredados de CallMeBot)
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
    zona_id = Column(Integer, ForeignKey("zonas.id", ondelete="SET NULL"))
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
    __table_args__ = (
        UniqueConstraint("empresa_id", "cedula", name="uq_cliente_empresa"),
        Index("ix_clientes_empresa_zona", "empresa_id", "zona_id"),
    )


class Prestamo(Base):
    __tablename__ = "prestamos"
    id = Column(Integer, primary_key=True, index=True)
    empresa_id = Column(Integer, ForeignKey("empresas.id"), nullable=False, index=True)
    cliente_id = Column(Integer, ForeignKey("clientes.id", ondelete="RESTRICT"), nullable=False)
    zona_id = Column(Integer, ForeignKey("zonas.id", ondelete="RESTRICT"), nullable=False)
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
        CheckConstraint("capital > 0", name="ck_prestamo_capital_pos"),
        CheckConstraint("num_cuotas > 0 AND num_cuotas <= 365", name="ck_prestamo_cuotas_rango"),
        CheckConstraint("tasa_interes >= 0 AND tasa_interes <= 100", name="ck_prestamo_tasa_rango"),
        CheckConstraint("estado IN ('Activo','Pagado','Mora','Castigado','Cancelado','Atrasado')",
                        name="ck_prestamo_estado"),
    )


class Cuota(Base):
    __tablename__ = "cuotas"
    id = Column(Integer, primary_key=True, index=True)
    empresa_id = Column(Integer, ForeignKey("empresas.id"), nullable=False, index=True)
    prestamo_id = Column(Integer, ForeignKey("prestamos.id", ondelete="CASCADE"), nullable=False)
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
        Index("ix_cuotas_prestamo_id", "prestamo_id"),
        CheckConstraint("valor > 0", name="ck_cuota_valor_pos"),
        CheckConstraint("valor_pagado >= 0", name="ck_cuota_pagado_no_neg"),
        CheckConstraint("valor_pagado <= valor", name="ck_cuota_pagado_no_excede"),
        CheckConstraint(
            "estado IN ('Pendiente','Pagada','Vencida','Parcial')",
            name="ck_cuota_estado",
        ),
    )


class Cobro(Base):
    __tablename__ = "cobros"
    id = Column(Integer, primary_key=True, index=True)
    empresa_id = Column(Integer, ForeignKey("empresas.id"), nullable=False, index=True)
    cuota_id = Column(Integer, ForeignKey("cuotas.id", ondelete="RESTRICT"), nullable=False)
    prestamo_id = Column(Integer, ForeignKey("prestamos.id", ondelete="RESTRICT"), nullable=False)
    cliente_id = Column(Integer, ForeignKey("clientes.id", ondelete="RESTRICT"), nullable=False)
    zona_id = Column(Integer, ForeignKey("zonas.id", ondelete="RESTRICT"), nullable=False)
    valor_cobrado = Column(Numeric(12, 2), nullable=False)
    fecha = Column(Date, default=datetime.date.today)
    hora = Column(DateTime, default=func.now())
    cobrador = Column(String(200))
    metodo_pago = Column(String(50), default="Efectivo")
    observaciones = Column(Text, nullable=True)
    lat_cobro = Column(Float, nullable=True)
    lng_cobro = Column(Float, nullable=True)
    usuario_id = Column(Integer, ForeignKey("usuarios.id", ondelete="SET NULL"), nullable=True)
    __table_args__ = (
        Index("ix_cobros_empresa_fecha", "empresa_id", "fecha"),
        Index("ix_cobros_empresa_cliente", "empresa_id", "cliente_id"),
        Index("ix_cobros_empresa_prestamo", "empresa_id", "prestamo_id"),
        CheckConstraint("valor_cobrado > 0", name="ck_cobro_valor_pos"),
    )


class NotificacionWP(Base):
    __tablename__ = "notificaciones_wp"
    id = Column(Integer, primary_key=True, index=True)
    empresa_id = Column(Integer, ForeignKey("empresas.id"), nullable=False, index=True)
    cliente_id = Column(Integer, ForeignKey("clientes.id", ondelete="CASCADE"), nullable=False)
    cuota_id = Column(Integer, ForeignKey("cuotas.id", ondelete="SET NULL"), nullable=True)
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
    wp_api_key = Column(String(500), nullable=True)  # deprecado: apikey de CallMeBot, ya no se usa para enviar
    wp_phone_id = Column(String(200), nullable=True)  # Green API: idInstance
    wp_token = Column(String(500), nullable=True)  # Green API: apiTokenInstance
    wp_activo = Column(Boolean, default=False)
    wp_mensaje_recordatorio = Column(Text, default="Hola {nombre}, su cuota #{num_cuota} de ${valor} vence el {fecha}. — {empresa}")
    wp_mensaje_vencida = Column(Text, default="Hola {nombre}, su cuota #{num_cuota} de ${valor} venció el {fecha}. — {empresa}")

    empresa = relationship("Empresa", back_populates="configuracion")


class AuditLog(Base):
    """Registro de acciones sensibles para auditoria y trazabilidad."""
    __tablename__ = "audit_log"
    id = Column(Integer, primary_key=True, index=True)
    empresa_id = Column(Integer, ForeignKey("empresas.id", ondelete="SET NULL"), nullable=True, index=True)
    usuario_id = Column(Integer, ForeignKey("usuarios.id", ondelete="SET NULL"), nullable=True, index=True)
    username = Column(String(100), nullable=True)
    action = Column(String(80), nullable=False, index=True)
    category = Column(String(40), nullable=False, index=True)
    details = Column(String(500), nullable=True)
    ip = Column(String(45), nullable=True)
    created_at = Column(DateTime, default=func.now(), index=True)
    __table_args__ = (
        Index("ix_audit_log_empresa_created", "empresa_id", "created_at"),
        Index("ix_audit_log_category_action", "category", "action"),
    )


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
    """Sesion para rutas normales: rol restringido si DATABASE_URL_APP esta
    configurada (RLS real por empresa_id), o la conexion privilegiada si no."""
    db = AppSessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_db_system():
    """Sesion privilegiada explicita, para los pocos endpoints que legitimamente
    necesitan ver mas de una empresa antes de tener un usuario autenticado:
    selector de empresa, activacion de licencia, registro de empresa nueva."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
