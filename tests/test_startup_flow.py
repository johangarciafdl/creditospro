from pathlib import Path

from app.utils.license_middleware import RUTAS_LIBRES_EXACTAS


def test_inicio_template_shows_owner_and_activation_flow():
    template = Path("templates/inicio.html").read_text(encoding="utf-8")

    assert "software_owner" in template
    assert "start_url" in template
    assert "Supabase/Postgres" in template
    assert "Separacion por empresa_id" in template


def test_license_middleware_allows_only_public_start_and_activation():
    assert "/" in RUTAS_LIBRES_EXACTAS
    assert "/inicio" in RUTAS_LIBRES_EXACTAS
    assert "/license/activar" in RUTAS_LIBRES_EXACTAS
    assert "/seleccionar-empresa" not in RUTAS_LIBRES_EXACTAS
