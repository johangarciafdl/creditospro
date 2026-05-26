import asyncio
from pathlib import Path

import pytest
from fastapi import HTTPException

from app.routers import auth
from app.utils.validators import sanitizar_imagen_subida


class _Request:
    cookies = {}


def test_public_stats_do_not_return_global_counts_without_session():
    result = asyncio.run(auth.stats_publicos(_Request(), db=None))
    assert result == {"clientes": 0, "prestamos": 0, "zonas": 0}


def test_invalid_image_content_is_rejected():
    with pytest.raises(HTTPException) as exc:
        sanitizar_imagen_subida("foto.jpg", b"not-an-image")
    assert exc.value.status_code == 400


def test_gitignore_does_not_include_broken_glob():
    root = Path(__file__).resolve().parents[1]
    content = (root / ".gitignore").read_text(encoding="utf-8")
    assert "{app/" not in content
    assert ".env" in content
    assert "uploads/" in content
