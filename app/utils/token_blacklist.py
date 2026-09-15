"""Sesiones JWT emitidas y revocadas, compartidas entre procesos.

Cuando un usuario cierra sesion, cambia su contrasena o un admin revoca
una sesion, el `jti` de ese token queda marcado como revocado y
get_current_user() lo rechaza.

Esto vivia solo en memoria del proceso, con dos consecuencias:

- Cada reinicio (es decir, cada despliegue) borraba la lista, asi que un
  token del que ya se habia hecho logout volvia a ser valido hasta su
  expiracion natural.
- Con mas de un worker, cada proceso tenia su propia lista: revocar una
  sesion en uno no la revocaba en los demas. Eso es lo que impedia
  levantar la aplicacion con varios workers.

Ahora el estado vive en la tabla `sesiones_jwt`. Para no pagar una
consulta por peticion, cada proceso mantiene en memoria el conjunto de
jtis revocados y lo refresca como mucho cada `_TTL_CACHE` segundos; una
revocacion tarda entonces a lo sumo ese tiempo en verse en los demas
workers, y es inmediata en el que la ejecuta.

Si la base de datos no esta disponible se sigue operando solo en memoria:
es preferible perder el alcance entre procesos a dejar a todo el mundo sin
poder entrar.
"""
import logging
import threading
import time

logger = logging.getLogger(__name__)

_MAX_ENTRIES = 10_000
_TTL_CACHE = 10  # segundos que un proceso puede tardar en ver una revocacion ajena

_revoked: dict[str, int] = {}  # respaldo en memoria: jti -> exp_epoch
_active_by_user: dict[str, list[dict]] = {}
_lock = threading.Lock()

_cache_revocados: set[str] = set()
_cache_hasta: float = 0.0
_bd_disponible = True


def _sesion():
    """Sesion de BD con el rol privilegiado, o None si no se puede usar.

    Se importa aqui dentro a proposito: este modulo lo cargan rutas que
    tambien se ejecutan en tests sin base de datos real.
    """
    if not _bd_disponible:
        return None
    try:
        from app.database import SessionLocal

        return SessionLocal()
    except Exception:
        return None


def _sin_bd(exc: Exception) -> None:
    """Marca la BD como no usable para sesiones y deja rastro una sola vez."""
    global _bd_disponible
    if _bd_disponible:
        logger.warning(
            "No se pueden guardar las sesiones en la base de datos (%s); "
            "se opera solo en memoria de este proceso",
            exc,
        )
    _bd_disponible = False


def _purge_expired():
    """Quita entradas expiradas del respaldo en memoria. Llamar con _lock tomado."""
    now = int(time.time())
    for jti in [j for j, exp in _revoked.items() if exp <= now]:
        _revoked.pop(jti, None)
    for uid in list(_active_by_user.keys()):
        _active_by_user[uid] = [s for s in _active_by_user[uid] if s["exp"] > now]
        if not _active_by_user[uid]:
            _active_by_user.pop(uid, None)


def _refrescar_cache(forzar: bool = False) -> None:
    global _cache_hasta, _cache_revocados
    ahora = time.monotonic()
    if not forzar and ahora < _cache_hasta:
        return
    db = _sesion()
    if db is None:
        return
    try:
        from app.database import SesionJWT

        filas = (
            db.query(SesionJWT.jti)
            .filter(
                SesionJWT.revocada.is_(True),
                SesionJWT.expira_en > int(time.time()),
            )
            .all()
        )
        _cache_revocados = {f[0] for f in filas}
        _cache_hasta = ahora + _TTL_CACHE
    except Exception as exc:
        _sin_bd(exc)
    finally:
        db.close()


def revoke_jti(jti: str, exp_epoch: int) -> None:
    """Marca un jti como revocado hasta su expiracion."""
    if not jti:
        return
    exp = int(exp_epoch) if exp_epoch else int(time.time()) + 3600

    with _lock:
        _purge_expired()
        if len(_revoked) >= _MAX_ENTRIES:
            _revoked.pop(min(_revoked.items(), key=lambda x: x[1])[0], None)
        _revoked[jti] = exp
        _cache_revocados.add(jti)  # efecto inmediato en este proceso

    db = _sesion()
    if db is None:
        return
    try:
        from app.database import SesionJWT

        fila = db.query(SesionJWT).filter(SesionJWT.jti == jti).first()
        if fila:
            fila.revocada = True
        else:
            db.add(
                SesionJWT(
                    jti=jti,
                    usuario_id="?",
                    expira_en=exp,
                    emitida_en=int(time.time()),
                    revocada=True,
                )
            )
        db.commit()
    except Exception as exc:
        db.rollback()
        _sin_bd(exc)
    finally:
        db.close()


def is_jti_revoked(jti: str) -> bool:
    if not jti:
        return False
    _refrescar_cache()
    with _lock:
        return jti in _cache_revocados or jti in _revoked


def revoke_jti_by_prefix_and_user(prefix: str, user_id: str) -> bool:
    """Revoca una sesion buscandola por prefijo de jti + usuario.

    Devuelve True si encontro y revoco alguna.
    """
    if not prefix or not user_id:
        return False

    db = _sesion()
    if db is not None:
        try:
            from app.database import SesionJWT

            fila = (
                db.query(SesionJWT)
                .filter(
                    SesionJWT.usuario_id == str(user_id),
                    SesionJWT.revocada.is_(False),
                    SesionJWT.jti.like(f"{prefix}%"),
                    SesionJWT.expira_en > int(time.time()),
                )
                .first()
            )
            if fila:
                fila.revocada = True
                db.commit()
                with _lock:
                    _revoked[fila.jti] = fila.expira_en
                    _cache_revocados.add(fila.jti)
                return True
        except Exception as exc:
            db.rollback()
            _sin_bd(exc)
        finally:
            db.close()

    with _lock:
        for s in _active_by_user.get(user_id, []):
            if s["jti"].startswith(prefix):
                _revoked[s["jti"]] = s["exp"]
                _cache_revocados.add(s["jti"])
                _active_by_user[user_id].remove(s)
                return True
    return False


def register_active_jti(user_id: str, jti: str, exp_epoch: int, ip: str = "?") -> None:
    """Registra una sesion recien emitida, para poder listarla y revocarla."""
    if not user_id or not jti:
        return
    ahora = int(time.time())

    with _lock:
        _purge_expired()
        _active_by_user.setdefault(user_id, []).append(
            {"jti": jti, "exp": int(exp_epoch), "issued": ahora, "ip": ip}
        )

    db = _sesion()
    if db is None:
        return
    try:
        from app.database import SesionJWT

        db.merge(
            SesionJWT(
                jti=jti,
                usuario_id=str(user_id),
                expira_en=int(exp_epoch),
                emitida_en=ahora,
                ip=(ip or "?")[:45],
                revocada=False,
            )
        )
        # Limpieza oportunista: las sesiones expiradas hace mas de un dia no
        # sirven ni para revocar ni para listar.
        db.query(SesionJWT).filter(SesionJWT.expira_en < ahora - 86400).delete(
            synchronize_session=False
        )
        db.commit()
    except Exception as exc:
        db.rollback()
        _sin_bd(exc)
    finally:
        db.close()


def list_active_jti_for_user(user_id: str) -> list[dict]:
    db = _sesion()
    if db is not None:
        try:
            from app.database import SesionJWT

            filas = (
                db.query(SesionJWT)
                .filter(
                    SesionJWT.usuario_id == str(user_id),
                    SesionJWT.revocada.is_(False),
                    SesionJWT.expira_en > int(time.time()),
                )
                .order_by(SesionJWT.emitida_en.desc())
                .all()
            )
            return [
                {"jti": f.jti, "exp": f.expira_en, "issued": f.emitida_en, "ip": f.ip or "?"}
                for f in filas
            ]
        except Exception as exc:
            _sin_bd(exc)
        finally:
            db.close()

    with _lock:
        return list(_active_by_user.get(user_id, []))


def estado() -> dict:
    """Resumen para el panel de monitoreo."""
    _refrescar_cache()
    return {
        "compartido": _bd_disponible,
        "revocados_en_cache": len(_cache_revocados),
        "segundos_de_propagacion": _TTL_CACHE,
    }
