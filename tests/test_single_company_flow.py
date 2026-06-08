from app.utils.settings import get_settings


def test_brand_defaults_and_registration_closed():
    settings = get_settings()

    assert settings.SOFTWARE_NAME == "CreditosPro"
    assert settings.SOFTWARE_OWNER == "Johan Garcia"
    assert settings.ALLOW_PUBLIC_REGISTRATION is False


def test_login_template_carries_empresa_id():
    from pathlib import Path

    template = Path("templates/auth/login.html").read_text(encoding="utf-8")

    assert 'name="empresa_id"' in template
    assert "empresa_nombre" in template


def test_base_menu_visible_without_animation_dependency():
    from pathlib import Path

    template = Path("templates/base.html").read_text(encoding="utf-8")

    # El menu debe ser visible por defecto (display:flex en .nav-item)
    assert ".nav-item{display:flex" in template
    # Debe haber fallback de anime.js por si el CDN falla
    assert "if(!window.anime)" in template
    # El fallback debe forzar opacity:1 para no dejar el menu invisible
    assert "opacity='1'" in template or 'opacity="1"' in template
