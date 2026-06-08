"""Tests de regresion para el sistema de licencias."""
import base64
import hashlib
import importlib
import json
import os
import time

import pytest


# Configurar master key antes de importar el modulo
TEST_MASTER_KEY = "test-master-key-for-license-tests-only-do-not-use-in-prod"


@pytest.fixture(autouse=True)
def _restore_license_env():
    """Asegura que LICENSE_MASTER_KEY tenga el valor del test, no el de otros tests.

    El fixture del test_integration puede haber sobreescrito esta variable
    con su propia master key. La restauramos aqui antes de cada test.
    """
    import license_manager
    saved = os.environ.get("LICENSE_MASTER_KEY")
    os.environ["LICENSE_MASTER_KEY"] = TEST_MASTER_KEY
    importlib.reload(license_manager)
    yield
    if saved is not None:
        os.environ["LICENSE_MASTER_KEY"] = saved
    importlib.reload(license_manager)


def _make_license(machine_id: str, expires_at: str) -> str:
    """Genera una licencia valida para los tests, replicando owner_tool.py.

    owner_tool codifica el token Fernet (que ya es URL-safe base64) en
    base64 una vez mas, y le anade el prefijo 'CPRO-'. El validador
    hace el camino inverso: strip prefijo, base64-decode, Fernet decrypt.
    """
    from cryptography.fernet import Fernet
    key = base64.urlsafe_b64encode(hashlib.sha256(TEST_MASTER_KEY.encode()).digest())
    f = Fernet(key)
    payload = json.dumps({
        "empresa_id": 1,
        "empresa": "Test",
        "machine_id": machine_id,
        "expires_at": expires_at,
    }).encode()
    token = f.encrypt(payload)
    return "CPRO-" + base64.urlsafe_b64encode(token).decode()


def test_licencia_valida_para_equipo_correcto():
    from license_manager import get_fingerprint, validate_license
    fp = get_fingerprint()
    expires = "2099-12-31T23:59:59"
    key = _make_license(fp, expires)
    result = validate_license(key)
    assert result["valid"] is True
    assert result["machine_id"] == fp


def test_licencia_rechazada_para_equipo_distinto():
    from license_manager import validate_license
    fake_fp = "ABCDEF1234567890ABCDEF1234567890"
    key = _make_license(fake_fp, "2099-12-31T23:59:59")
    result = validate_license(key)
    assert result["valid"] is False
    assert "equipo" in result["error"].lower()


def test_licencia_expirada():
    from license_manager import get_fingerprint, validate_license
    fp = get_fingerprint()
    key = _make_license(fp, "2020-01-01T00:00:00")
    result = validate_license(key)
    assert result["valid"] is False
    assert "expirada" in result["error"].lower()


def test_licencia_tampered_rechazada():
    from license_manager import validate_license
    # Clave manipulada (cambiar un caracter al final)
    valid = _make_license("X" * 32, "2099-12-31T23:59:59")
    tampered = valid[:-1] + ("A" if valid[-1] != "A" else "B")
    result = validate_license(tampered)
    assert result["valid"] is False


def test_licencia_sin_master_key_falla():
    """Sin LICENSE_MASTER_KEY, validate_license debe fallar limpiamente."""
    import importlib
    import license_manager
    saved = os.environ.pop("LICENSE_MASTER_KEY", None)
    try:
        # Reimportar con env limpia
        importlib.reload(license_manager)
        result = license_manager.validate_license("CPRO-whatever")
        assert result["valid"] is False
        assert "LICENSE_MASTER_KEY" in result["error"]
    finally:
        os.environ["LICENSE_MASTER_KEY"] = TEST_MASTER_KEY
        importlib.reload(license_manager)
