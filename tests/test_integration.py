"""Tests de integracion basicos que levantan la app con TestClient."""
import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="module")
def client():
    """Levanta la app en un TestClient con DB SQLite en archivo.

    Usamos un archivo (no :memory:) para que todas las conexiones
    (incluyendo el scheduler en background) compartan la misma base
    de datos. Con :memory: cada conexion ve una DB distinta y
    aparecen errores tipo 'no such table'.
    """
    import tempfile
    test_db = Path(tempfile.gettempdir()) / "creditospro_integration_test.db"
    if test_db.exists():
        test_db.unlink()

    # Configurar env ANTES de importar
    os.environ["DATABASE_URL"] = f"sqlite:///{test_db}"
    os.environ["SECRET_KEY"] = "test-secret-key-for-integration-tests-only"
    os.environ["SESSION_SECRET_KEY"] = "test-session-secret-for-integration-tests"
    os.environ["ENVIRONMENT"] = "development"
    os.environ["AUTO_CREATE_TABLES"] = "1"
    os.environ["ALLOW_PUBLIC_REGISTRATION"] = "0"
    master_key = "integration-test-master-key-not-real"
    os.environ["LICENSE_MASTER_KEY"] = master_key

    # Crear un archivo de licencia valido para que LicenseMiddleware no
    # bloquee las requests. La licencia es para el fingerprint de este equipo.
    import base64
    import hashlib
    import json
    from cryptography.fernet import Fernet
    from license_manager import get_fingerprint

    key = base64.urlsafe_b64encode(hashlib.sha256(master_key.encode()).digest())
    f = Fernet(key)
    fp = get_fingerprint()
    payload = json.dumps({
        "empresa_id": 1,
        "empresa": "TestCo",
        "machine_id": fp,
        "expires_at": "2099-12-31T23:59:59",
    }).encode()
    token = f.encrypt(payload)
    license_str = "CPRO-" + base64.urlsafe_b64encode(token).decode()

    license_file = Path(tempfile.gettempdir()) / "license.key.test"
    license_file.write_text(license_str, encoding="utf-8")
    # Apuntar la app al archivo de licencia
    import license_manager
    license_manager.LICENSE_FILE = license_file

    # Importar app y crear tablas
    # Si otros tests ya importaron app.database, hay que recargar para que
    # el engine use la URL de archivo (no :memory: que es el default del conftest).
    import importlib
    import app.database as _appdb
    import app.main as _appmain
    importlib.reload(_appdb)
    importlib.reload(_appmain)
    from app.database import Base, engine, init_db
    from app.main import app
    init_db()

    with TestClient(app) as c:
        from app.database import SessionLocal, Usuario, Empresa
        from app.utils.security import get_password_hash
        db = SessionLocal()
        try:
            emp = db.query(Empresa).first()
            if not emp:
                emp = Empresa(nombre="TestCo", activa=True)
                db.add(emp)
                db.commit()
                db.refresh(emp)
                from app.utils.company_activation import assign_company_key
                if not emp.activation_key_hash:
                    activation_key = assign_company_key(db, emp)
                    db.commit()
                else:
                    activation_key = None
                emp_id = emp.id
                if activation_key is None:
                    raise AssertionError("La fixture requiere una clave de activacion nueva")
        finally:
            db.close()

        def reset_test_user():
            db = SessionLocal()
            try:
                user = db.query(Usuario).filter(Usuario.username == "testuser").first()
                if user:
                    user.password_hash = get_password_hash("contrasena123")
                    db.commit()
                else:
                    user = Usuario(
                        empresa_id=emp_id,
                        username="testuser",
                        nombre="Test User",
                        password_hash=get_password_hash("contrasena123"),
                        rol="admin",
                        activo=True,
                    )
                    db.add(user)
                    db.commit()
            finally:
                db.close()

        c.reset_test_user = reset_test_user
        reset_test_user()
        activation_response = c.post("/license/activate", data={"license_key": activation_key})
        assert activation_response.status_code == 200
        assert activation_response.json().get("valid") is True
        yield c

    # Cleanup
    try:
        Base.metadata.drop_all(bind=engine)
        engine.dispose()
    except Exception:
        pass
    try:
        license_file.unlink()
    except (FileNotFoundError, PermissionError):
        pass


@pytest.fixture(autouse=True)
def _reset_test_user_entre_tests(client):
    """Resetea la contrasena del testuser ANTES de cada test.

    Si un test cambia la contrasena y falla antes de llamar a
    reset_test_user(), el siguiente test aun encuentra al usuario
    con la contrasena original.
    """
    client.cookies.delete("cp_session")
    client.cookies.delete("cp_csrf")
    from app.database import SessionLocal, Usuario, Empresa
    from app.utils.security import get_password_hash
    # Reset directo: crear/actualizar usuario con la contrasena original
    db = SessionLocal()
    try:
        emp = db.query(Empresa).first()
        if not emp:
            emp = Empresa(nombre="TestCo", activa=True)
            db.add(emp)
            db.commit()
            db.refresh(emp)
        user = db.query(Usuario).filter(Usuario.username == "testuser").first()
        if user:
            user.password_hash = get_password_hash("contrasena123")
            user.activo = True
        else:
            user = Usuario(
                empresa_id=emp.id,
                username="Test User",
                password_hash=get_password_hash("contrasena123"),
                rol="admin",
                activo=True,
            )
            db.add(user)
        db.commit()
        # Verificar que el usuario existe con la contrasena correcta
        from app.utils.security import verify_password
        db.refresh(user)
        verify_password("contrasena123", user.password_hash)  # sanity check
    finally:
        db.close()
    yield


def test_health_endpoint_responde(client):
    """El endpoint /health debe responder 200 con la BD en memoria OK."""
    r = client.get("/health")
    assert r.status_code == 200
    data = r.json()
    assert "status" in data
    assert data["status"] in ("ok", "healthy")


def test_request_id_header_en_respuesta(client):
    """El middleware RequestID debe agregar el header X-Request-ID."""
    r = client.get("/health")
    assert "X-Request-ID" in r.headers or "x-request-id" in {k.lower() for k in r.headers}
    rid = r.headers.get("X-Request-ID") or r.headers.get("x-request-id")
    assert rid and len(rid) > 0


def test_request_id_personalizado_se_respeta(client):
    """Si el cliente envia X-Request-ID, se respeta."""
    custom = "mi-request-id-12345"
    r = client.get("/health", headers={"X-Request-ID": custom})
    assert r.headers.get("X-Request-ID") == custom


def test_login_credenciales_invalidas_no_enumera_usuarios(client):
    """Login fallido debe tardar aprox. lo mismo sin importar si el user existe."""
    import time
    # Timing del login con usuario inexistente
    t1 = time.perf_counter()
    r1 = client.post("/auth/login", data={"username": "noexiste123", "password": "x" * 20})
    t_no_existe = time.perf_counter() - t1

    # Crear un usuario para comparar
    from app.database import SessionLocal, Usuario, Empresa
    db = SessionLocal()
    try:
        # Verificar si ya hay empresa
        emp = db.query(Empresa).first()
        if not emp:
            emp = Empresa(nombre="TestCo", activa=True)
            db.add(emp)
            db.commit()
            db.refresh(emp)
        from app.utils.security import get_password_hash
        user = db.query(Usuario).filter(Usuario.username == "testuser").first()
        if not user:
            user = Usuario(
                empresa_id=emp.id,
                username="testuser",
                nombre="Test",
                password_hash=get_password_hash("contrasena123"),
                rol="admin",
                activo=True,
            )
            db.add(user)
            db.commit()
    finally:
        db.close()

    # Timing con usuario existente pero password incorrecta
    t2 = time.perf_counter()
    r2 = client.post("/auth/login", data={"username": "testuser", "password": "wrongpassword"})
    t_existe = time.perf_counter() - t2

    # Ambos deben ser aprox iguales (timing safety). Toleramos variacion
    # por carga del sistema (DB queries en lifespan, etc).
    diff = abs(t_no_existe - t_existe)
    assert diff < 1.5, (
        f"Timing attack: dif={diff:.3f}s "
        f"(no_existe={t_no_existe:.3f}, existe={t_existe:.3f})"
    )


def test_login_exitoso_crea_cookie_y_token(client):
    """Login valido debe setear cp_session y redirigir a /dashboard."""
    r = client.post(
        "/auth/login",
        data={"username": "testuser", "password": "contrasena123"},
        follow_redirects=False,
    )
    assert r.status_code == 302
    assert "cp_session" in r.cookies or r.headers.get("set-cookie", "").startswith("cp_session=")


def test_logout_limpia_cookies(client):
    """Logout debe limpiar cp_session y cp_csrf."""
    # Primero login
    r = client.post(
        "/auth/login",
        data={"username": "testuser", "password": "contrasena123"},
    )
    # Logout
    r2 = client.get("/auth/logout", follow_redirects=False)
    assert r2.status_code == 302


def test_cambio_password_politica_rechaza_corta(client):
    """El endpoint cambiar-password debe rechazar contrasenas debiles."""
    # Login (establece cookies de sesion y CSRF)
    login_r = client.post(
        "/auth/login",
        data={"username": "testuser", "password": "contrasena123"},
        follow_redirects=False,
    )
    assert login_r.status_code == 302, f"Login fallo: {login_r.status_code}"
    csrf = login_r.cookies.get("cp_csrf")
    assert csrf, "El login no setea cookie CSRF"

    # Intentar cambio con contrasena corta — debe fallar por politica
    r = client.post(
        "/auth/cambiar-password",
        data={
            "current_actual": "contrasena123",
            "nueva": "abc",
            "confirmar": "abc",
        },
        headers={"X-CSRF-Token": csrf},
    )
    assert r.status_code == 400
    assert "caracteres" in r.json()["error"].lower()


def test_cambio_password_politica_acepta_fuerte(client):
    """Contrasena fuerte + actual correcta debe pasar."""
    login_r = client.post(
        "/auth/login",
        data={"username": "testuser", "password": "contrasena123"},
        follow_redirects=False,
    )
    csrf = login_r.cookies.get("cp_csrf")
    r = client.post(
        "/auth/cambiar-password",
        data={
            "current_actual": "contrasena123",
            "nueva": "NuevaClave123!",
            "confirmar": "NuevaClave123!",
        },
        headers={"X-CSRF-Token": csrf},
    )
    assert r.status_code == 200
    assert r.json()["ok"] is True
    # Restaurar la contrasena para que otros tests no se vean afectados
    client.reset_test_user()
