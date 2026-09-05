"""Pruebas unitarias de las capas de activacion y 2FA."""
import os

os.environ.setdefault("SECRET_KEY", "test-security-layer-secret")

from app.utils.company_activation import (
    clear_failed_activation,
    generate_company_key,
    get_retry_after,
    is_valid_key_format,
    register_failed_activation,
)
from app.utils.two_factor import (
    backup_hashes_json,
    consume_backup_code,
    generate_backup_codes,
    generate_secret,
    verify_totp,
)


def test_company_key_is_legible_and_has_valid_format():
    key = generate_company_key("ElRusso")
    assert key.startswith("ELRUSSO-")
    assert is_valid_key_format(key)


def test_activation_failure_enforces_retry_window():
    client_key = "test-security-client"
    clear_failed_activation(client_key)
    assert get_retry_after(client_key) == 0
    register_failed_activation(client_key, seconds=30)
    assert 1 <= get_retry_after(client_key) <= 30
    clear_failed_activation(client_key)
    assert get_retry_after(client_key) == 0


def test_totp_and_backup_code_are_one_time():
    import pyotp

    secret = generate_secret()
    assert verify_totp(secret, pyotp.TOTP(secret).now())
    assert not verify_totp(secret, "000000")

    codes = generate_backup_codes(2)
    stored = backup_hashes_json(codes)
    valid, stored = consume_backup_code(codes[0], stored)
    assert valid
    valid_again, stored = consume_backup_code(codes[0], stored)
    assert not valid_again
    assert len(stored) > 0
