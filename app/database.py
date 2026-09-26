"""
CreditosPro v2.1 - Database Multi-tenant
Cada Empresa tiene datos completamente aislados.
Unique constraints son POR empresa, no globales.
"""
import contextvars
import datetime
import logging
import os
import time
from pathlib import Path

from sqlalchemy import (
    create_engine, Column, Integer, String, Float, Numeric, Date,
    DateTime, Boolean, Text, JSON, ForeignKey, UniqueConstraint, Index, Table,
    CheckConstraint, event, text, LargeBinary,
)
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker, relationship
from sqlalchemy.sql import func

from app.utils.url_bd import normalizar as normalizar_url_bd

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

# Normalizar la URL, nombrando el controlador. Dejar `postgresql://` a
# secas delega la eleccion en un valor por defecto de SQLAlchemy, y ese
# valor cambio en la 2.1 (de psycopg2 a psycopg 3): la aplicacion dejo de
# arrancar sin que nadie tocara el codigo. Ver app/utils/url_bd.py.
SQLALCHEMY_DATABASE_URL = normalizar_url_bd(SQLALCHEMY_DATABASE_URL)

# Detectar si es SQLite para desarrollo local
IS_SQLITE = SQLALCHEMY_DATABASE_URL.startswith("sqlite://")


# El tamaño del pool se mide contra el limite de conexiones del servidor de
# base de datos, no contra lo que le gustaria a la aplicacion. La app abre
# DOS motores (el de sistema y el restringido con RLS), asi que el consumo
# maximo real es:
#
#     workers x 2 motores x (DB_POOL_SIZE + DB_MAX_OVERFLOW)
#
# Con los valores historicos (5 + 10) un solo proceso podia llegar a 30
# conexiones; el servidor admite 60 en total y ya hay otras cosas
# conectadas, asi que dos workers lo habrian agotado. Con los valores por
# defecto de abajo, dos workers usan como mucho 20.
POOL_SIZE = int(os.getenv("DB_POOL_SIZE", "3"))
MAX_OVERFLOW = int(os.getenv("DB_MAX_OVERFLOW", "2"))


# El servidor de base de datos admite un numero fijo de conexiones. Se
# configura porque depende del plan contratado.
MAX_CONEXIONES_SERVIDOR = int(os.getenv("DB_MAX_CONEXIONES", "60"))


def revisar_presupuesto_de_conexiones(workers: int | None = None) -> tuple[int, int]:
    """Compara el consumo maximo de conexiones con el limite del servidor.

    El techo de procesos rara vez lo pone la CPU: lo pone el pool contra el
    limite del servidor. La cuenta estaba escrita en un comentario, que solo
    protege si alguien lo lee antes de subir WEB_CONCURRENCY. Aqui se hace
    al arrancar y se deja dicho en el registro, que es donde se mira cuando
    la aplicacion empieza a dar errores de conexion agotada.

    Devuelve (consumo_maximo, limite) y avisa si no cabe.
    """
    if IS_SQLITE:
        return (0, 0)
    if workers is None:
        workers = int(os.getenv("WEB_CONCURRENCY", "2"))
    motores = 2  # el de sistema y el restringido con RLS
    consumo = workers * motores * (POOL_SIZE + MAX_OVERFLOW)
    if consumo > MAX_CONEXIONES_SERVIDOR:
        logger.error(
            "Presupuesto de conexiones excedido: %s workers x %s motores x "
            "(%s+%s) = %s, y el servidor admite %s. Baja WEB_CONCURRENCY o "
            "DB_POOL_SIZE, o la aplicacion agotara las conexiones bajo carga.",
            workers, motores, POOL_SIZE, MAX_OVERFLOW, consumo,
            MAX_CONEXIONES_SERVIDOR,
        )
    else:
        logger.info(
            "Conexiones: hasta %s de %s (%s workers x %s motores x (%s+%s))",
            consumo, MAX_CONEXIONES_SERVIDOR, workers, motores, POOL_SIZE, MAX_OVERFLOW,
        )
    return (consumo, MAX_CONEXIONES_SERVIDOR)


def _engine_kwargs_for(url: str) -> tuple[dict, dict]:
    """connect_args/engine_kwargs correctos segun el dialecto de esa URL
    especifica (DATABASE_URL y DATABASE_URL_APP pueden ser dialectos
    distintos, p.ej. sqlite en tests + postgres real)."""
    if url.startswith("sqlite://"):
        # SQLite necesita check_same_thread=False para usar en hilos
        return {"check_same_thread": False}, {"pool_pre_ping": True}
    return {}, {
        "pool_pre_ping": True,
        # 300 segundos obligaba a tirar y reabrir cada conexion cada 5 minutos.
        # Abrir una conexion nueva contra el pooler cuesta varios viajes de ida
        # y vuelta (TLS + autenticacion), y con trafico continuo eso pasaba todo
        # el rato: de ahi las cientos de miles de autenticaciones registradas en
        # el pooler. Media hora sigue siendo muy inferior a cualquier tiempo de
        # vida de conexion del servidor, y el pre-ping cubre la conexion muerta.
        "pool_recycle": 1800,
        # LIFO reutiliza siempre las conexiones mas recientes en vez de rotar
        # por todas: con trafico bajo mantiene un par calientes y deja que las
        # demas caduquen, en vez de mantenerlas todas a medio morir.
        "pool_use_lifo": True,
        "pool_size": POOL_SIZE,
        "max_overflow": MAX_OVERFLOW,
        # Si el pool esta lleno, esperar en vez de fallar de inmediato: una
        # peticion que tarda un segundo de mas es mejor que un error 500.
        "pool_timeout": 30,
    }


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
APP_DATABASE_URL = normalizar_url_bd(os.getenv("DATABASE_URL_APP", "").strip())

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
    app_engine = engine


# ── Medicion del coste de base de datos por peticion ──────────────────────────
# "Va lento" no se puede atribuir sin separar tres cosas: el viaje por la red
# hasta el servidor, el trabajo de la aplicacion y las idas y venidas a la base
# de datos. Estos dos contadores (numero de consultas y tiempo total dentro de
# ellas) viven en un contextvar, asi que cada peticion tiene los suyos aunque se
# atiendan varias a la vez, y MetricasMiddleware los publica en Server-Timing.
_consultas_peticion: contextvars.ContextVar[list] = contextvars.ContextVar("consultas_peticion")


def reiniciar_contador_consultas() -> None:
    _consultas_peticion.set([0, 0.0])


def contador_consultas() -> tuple[int, float]:
    datos = _consultas_peticion.get(None)
    if not datos:
        return 0, 0.0
    return datos[0], datos[1]


@event.listens_for(engine, "before_cursor_execute")
def _marcar_inicio_consulta(conn, cursor, statement, parameters, context, executemany):
    conn.info["_t_consulta"] = time.perf_counter()


@event.listens_for(engine, "after_cursor_execute")
def _acumular_consulta(conn, cursor, statement, parameters, context, executemany):
    inicio = conn.info.pop("_t_consulta", None)
    if inicio is None:
        return
    datos = _consultas_peticion.get(None)
    if datos is not None:
        datos[0] += 1
        datos[1] += (time.perf_counter() - inicio) * 1000


if app_engine is not engine:
    event.listen(app_engine, "before_cursor_execute", _marcar_inicio_consulta)
    event.listen(app_engine, "after_cursor_execute", _acumular_consulta)


# ── Fecha del negocio, no la del servidor ────────────────────────────────────
# El contenedor corre en UTC y los usuarios estan en Colombia (UTC-5): a las
# 7 de la tarde hora local el servidor ya cree que es el dia siguiente. Para
# "cobros de hoy" eso descuadra un informe; para la ruta del dia cambiaria la
# zona habilitada al cobrador en plena jornada. TZ_NEGOCIO permite ajustarlo
# si algun dia hay un cliente en otro huso.
TZ_NEGOCIO = os.getenv("TZ_NEGOCIO", "America/Bogota")


def hoy_local() -> datetime.date:
    """La fecha de hoy donde trabaja el usuario, no donde corre el servidor."""
    try:
        from zoneinfo import ZoneInfo

        return datetime.datetime.now(ZoneInfo(TZ_NEGOCIO)).date()
    except Exception:  # zona horaria desconocida o sin tzdata: no romper
        logger.warning("TZ_NEGOCIO=%s no disponible; se usa la hora del servidor", TZ_NEGOCIO)
        return datetime.date.today()


def ahora_local() -> datetime.datetime:
    """La hora de pared donde trabaja el usuario, sin zona horaria adjunta.

    Para decidir "son las tres de la madrugada" hay que preguntar por el
    reloj del negocio. Restar medianoches, que fue el primer intento, falla
    justo cuando la fecha local y la del servidor coinciden: la diferencia
    sale cero y queda la hora UTC.
    """
    try:
        from zoneinfo import ZoneInfo

        return datetime.datetime.now(ZoneInfo(TZ_NEGOCIO)).replace(tzinfo=None)
    except Exception:
        return datetime.datetime.now()


def dia_semana_local() -> int:
    """0=lunes .. 6=domingo, en la hora local del negocio."""
    return hoy_local().weekday()


def inicio_dia_negocio() -> datetime.datetime:
    """Medianoche del dia de negocio, en la hora del servidor.

    Las marcas de tiempo (AuditLog.created_at, Cobro.hora) se guardan con
    datetime.now(), es decir en la hora del servidor. Para preguntar "¿paso
    esto hoy?" hay que comparar contra la medianoche local del negocio
    traducida a esa misma escala; usar la medianoche del servidor corre el
    corte del dia cinco horas y parte la jornada en dos.
    """
    try:
        from zoneinfo import ZoneInfo

        medianoche = datetime.datetime.combine(
            hoy_local(), datetime.time.min, tzinfo=ZoneInfo(TZ_NEGOCIO)
        )
        return medianoche.astimezone().replace(tzinfo=None)
    except Exception:
        return datetime.datetime.combine(datetime.date.today(), datetime.time.min)


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
    # Copia cifrada (reversible, Fernet sobre SECRET_KEY) de la clave activa --
    # permite que el superadmin la vuelva a ver desde /plataforma sin tener
    # que rotarla. El hash de arriba sigue siendo lo que valida /license/activate;
    # esta columna es solo para mostrarla, nunca se usa para autenticar.
    activation_key_encrypted = Column(Text, nullable=True)
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


class Archivo(Base):
    """Indice de las imagenes subidas: quien es su dueno y donde estan.

    Antes se escribian en uploads/ dentro del contenedor. El proveedor da un
    disco efimero: cada despliegue lo borra, asi que toda foto tomada por un
    cobrador desaparecia en el siguiente despliegue y el perfil del cliente
    quedaba con la imagen rota.

    Los bytes viven ahora en Supabase Storage, en un bucket privado al que
    solo llega el backend con la clave de servicio. Esta tabla guarda a que
    empresa pertenece cada imagen, que es lo que permite negarsela a otra
    empresa antes de ir a buscarla, y de paso deja el inventario dentro de la
    misma copia de seguridad que el resto de los datos.
    """
    __tablename__ = "archivos"
    id = Column(Integer, primary_key=True, index=True)
    empresa_id = Column(Integer, ForeignKey("empresas.id", ondelete="CASCADE"), nullable=False, index=True)
    # El nombre con el que se sirve; es lo que queda guardado en foto_path.
    nombre = Column(String(300), nullable=False, unique=True, index=True)
    # "cliente" o "cobro": permite localizar y limpiar por tipo.
    tipo = Column(String(30), nullable=False, default="cliente")
    mime = Column(String(80), nullable=False, default="image/jpeg")
    # Donde estan los bytes: "supabase" (Storage) o "bd" (la columna datos).
    # Las dos conviven porque las imagenes subidas antes de mover el almacen
    # siguen en la base, y porque sin credenciales de Storage -- pruebas y
    # desarrollo local -- la aplicacion tiene que seguir funcionando igual.
    almacen = Column(String(20), nullable=False, default="bd")
    # Ruta dentro del bucket cuando almacen == "supabase".
    ruta = Column(String(400), nullable=True)
    datos = Column(LargeBinary, nullable=True)
    tamano = Column(Integer, nullable=False, default=0)
    creado = Column(DateTime, default=func.now())

    __table_args__ = (
        Index("ix_archivos_empresa_tipo", "empresa_id", "tipo"),
    )


class NotaCliente(Base):
    """Aviso que el cobrador deja sobre un cliente, para que el admin actue.

    Es la contrapartida de que el cobrador no pueda tocar la ficha. Quien
    esta en la calle es el unico que se entera de que alguien se mudo o
    cambio de numero; si no tiene donde apuntarlo, ese dato se pierde en un
    WhatsApp o no se dice. La nota no modifica nada: deja constancia y le
    llega al admin, que decide si corrige la ficha.

    `atendida` es lo que la convierte en una bandeja y no en un monton: el
    admin marca lo que ya resolvio y le queda a la vista solo lo pendiente.
    """
    __tablename__ = "notas_cliente"
    id = Column(Integer, primary_key=True, index=True)
    empresa_id = Column(Integer, ForeignKey("empresas.id", ondelete="CASCADE"), nullable=False, index=True)
    cliente_id = Column(Integer, ForeignKey("clientes.id", ondelete="CASCADE"), nullable=False, index=True)
    texto = Column(String(600), nullable=False)
    # Quien la escribio. Se guarda tambien el nombre porque un usuario puede
    # borrarse y la nota tiene que seguir diciendo de quien venia.
    usuario_id = Column(Integer, ForeignKey("usuarios.id", ondelete="SET NULL"), nullable=True, index=True)
    escrita_por = Column(String(200), nullable=True)
    creado = Column(DateTime, default=func.now())

    atendida = Column(Boolean, default=False, nullable=False)
    atendida_por_id = Column(Integer, ForeignKey("usuarios.id", ondelete="SET NULL"), nullable=True)
    atendida_por = Column(String(200), nullable=True)
    atendida_en = Column(DateTime, nullable=True)

    __table_args__ = (
        # La consulta que mas se hace: las pendientes de una empresa,
        # de la mas reciente a la mas antigua.
        Index("ix_notas_empresa_atendida", "empresa_id", "atendida"),
        Index("ix_notas_empresa_cliente", "empresa_id", "cliente_id"),
        CheckConstraint("length(trim(texto)) > 0", name="ck_nota_no_vacia"),
    )


class NoPago(Base):
    """Visita en la que el cliente no pago: queda constancia del intento.

    Sin esto, un dia sin cobro es indistinguible de un dia sin visita: la
    cuota simplemente sigue pendiente y no hay forma de saber si el cobrador
    paso y el cliente no tenia, o si nadie fue. Cada fila es una visita
    fallida concreta, con su fecha y su motivo.
    """
    __tablename__ = "no_pagos"
    id = Column(Integer, primary_key=True, index=True)
    empresa_id = Column(Integer, ForeignKey("empresas.id", ondelete="CASCADE"), nullable=False, index=True)
    cuota_id = Column(Integer, ForeignKey("cuotas.id", ondelete="CASCADE"), nullable=False, index=True)
    prestamo_id = Column(Integer, ForeignKey("prestamos.id", ondelete="CASCADE"), nullable=False, index=True)
    cliente_id = Column(Integer, ForeignKey("clientes.id", ondelete="CASCADE"), nullable=False, index=True)
    zona_id = Column(Integer, ForeignKey("zonas.id", ondelete="SET NULL"), nullable=True, index=True)
    fecha = Column(Date, nullable=False)
    motivo = Column(String(300), nullable=True)
    usuario_id = Column(Integer, ForeignKey("usuarios.id", ondelete="SET NULL"), nullable=True, index=True)
    registrado_por = Column(String(200), nullable=True)
    creado = Column(DateTime, default=func.now())

    __table_args__ = (
        # Una visita fallida por cuota y dia: pulsar dos veces el boton no
        # debe inventar dos visitas.
        UniqueConstraint("cuota_id", "fecha", name="uq_no_pago_cuota_fecha"),
        Index("ix_no_pagos_empresa_fecha", "empresa_id", "fecha"),
    )


class RutaCobro(Base):
    """Que zonas puede cobrar un cobrador en cada dia de la semana.

    Sin filas para un usuario, ese usuario cobra en todas las zonas que tenga
    asignadas (comportamiento de siempre). En cuanto el administrador le
    configura una ruta, pasa a regir la ruta: cada dia solo se le habilitan
    las zonas de ese dia. El limite de 3 zonas por dia se valida en la
    aplicacion, donde se puede devolver un mensaje entendible.
    """
    __tablename__ = "rutas_cobro"
    id = Column(Integer, primary_key=True, index=True)
    empresa_id = Column(Integer, ForeignKey("empresas.id", ondelete="CASCADE"), nullable=False, index=True)
    usuario_id = Column(Integer, ForeignKey("usuarios.id", ondelete="CASCADE"), nullable=False)
    zona_id = Column(Integer, ForeignKey("zonas.id", ondelete="CASCADE"), nullable=False, index=True)
    # 0=lunes .. 6=domingo (coincide con date.weekday() de Python)
    dia_semana = Column(Integer, nullable=False)
    creado = Column(DateTime, default=func.now())

    __table_args__ = (
        UniqueConstraint("usuario_id", "dia_semana", "zona_id", name="uq_ruta_usuario_dia_zona"),
        CheckConstraint("dia_semana >= 0 AND dia_semana <= 6", name="ck_ruta_dia_semana"),
        # La consulta que se hace en CADA peticion de un cobrador es
        # "sus zonas de hoy": indice compuesto con usuario primero.
        Index("ix_rutas_cobro_usuario_dia", "usuario_id", "dia_semana"),
    )


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
    fecha = Column(Date, default=hoy_local)
    hora = Column(DateTime, default=func.now())
    cobrador = Column(String(200))
    metodo_pago = Column(String(50), default="Efectivo")
    observaciones = Column(Text, nullable=True)
    lat_cobro = Column(Float, nullable=True)
    lng_cobro = Column(Float, nullable=True)
    usuario_id = Column(Integer, ForeignKey("usuarios.id", ondelete="SET NULL"), nullable=True)
    # Clave que genera el celular del cobrador al registrar el cobro (incluso
    # sin señal). Si la respuesta del servidor se pierde y la PWA reintenta,
    # el reintento trae la misma clave y el cobro no se aplica dos veces.
    idempotency_key = Column(String(64), nullable=True)
    # La foto del cobro se pedia en pantalla como "evidencia del pago", se
    # validaba y se escribia en disco, pero no habia donde anotar cual era:
    # la referencia se descartaba y la evidencia se perdia siempre.
    foto_path = Column(String(300), nullable=True)
    __table_args__ = (
        Index("ix_cobros_empresa_fecha", "empresa_id", "fecha"),
        UniqueConstraint("empresa_id", "idempotency_key", name="uq_cobro_idempotency"),
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


class SesionJWT(Base):
    """Sesiones emitidas y revocadas, compartidas por todos los procesos.

    Antes esto vivia solo en memoria del proceso. Con un unico worker
    funcionaba, pero significaba dos cosas malas: al reiniciar (cada
    despliegue) se perdia la lista de sesiones revocadas, de modo que un
    token del que se habia hecho logout volvia a ser valido; y con mas de
    un worker cada proceso tenia su propia lista, asi que revocar una
    sesion en uno no la revocaba en los demas. Eso es lo que impedia subir
    el numero de workers.

    No lleva empresa_id ni politica RLS: es infraestructura de sesion, la
    consulta la app antes de saber a que empresa pertenece el token.
    """
    __tablename__ = "sesiones_jwt"
    jti = Column(String(64), primary_key=True)
    usuario_id = Column(String(40), nullable=False, index=True)
    expira_en = Column(Integer, nullable=False, index=True)
    emitida_en = Column(Integer, nullable=False)
    ip = Column(String(45), nullable=True)
    revocada = Column(Boolean, default=False, nullable=False, index=True)


class ContadorRateLimit(Base):
    """Ventanas del rate limit, compartidas por todos los procesos.

    Con el contador en memoria, N workers permiten N veces el limite
    configurado: 10 intentos de login por minuto se vuelven 40 con cuatro
    workers. Aqui la ventana es una fila unica por (regla, cliente), asi
    que el limite es el mismo sin importar cuantos procesos haya.
    """
    __tablename__ = "rate_limit_ventanas"
    clave = Column(String(200), primary_key=True)
    ventana_inicio = Column(Integer, nullable=False)
    conteo = Column(Integer, nullable=False, default=0)
    actualizado_en = Column(Integer, nullable=False, index=True)


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
