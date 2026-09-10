"""Validacion de telefono y WhatsApp (reporte de errores, punto 2).

Un WhatsApp incompleto no falla al guardarlo sino despues, en silencio,
cuando el recordatorio no se puede enviar. Por eso se valida al escribirlo.
"""
import pytest
from fastapi import HTTPException

from app.utils.validators import validar_telefono, validar_whatsapp


@pytest.mark.parametrize("entrada,esperado", [
    ("3102666226", "3102666226"),   # celular
    ("310 266 6226", "3102666226"),  # con espacios: se normaliza
    ("(604) 4441122", "6044441122"),  # fijo con indicativo, 10 digitos
    ("4441122", "4441122"),          # fijo viejo de 7 digitos
])
def test_telefono_acepta_formatos_validos(entrada, esperado):
    assert validar_telefono(entrada) == esperado


@pytest.mark.parametrize("entrada", [
    "310266622",     # 9 digitos: incompleto
    "31026662266",   # 11 digitos: sobra uno
    "000",           # relleno
    "abcdefg",       # sin digitos
])
def test_telefono_rechaza_longitudes_invalidas(entrada):
    with pytest.raises(HTTPException) as exc:
        validar_telefono(entrada)
    assert exc.value.status_code == 400


def test_telefono_opcional_vacio_devuelve_none():
    assert validar_telefono("", requerido=False) is None


def test_telefono_requerido_vacio_falla():
    with pytest.raises(HTTPException):
        validar_telefono("", requerido=True)


@pytest.mark.parametrize("entrada,esperado", [
    ("3102666226", "3102666226"),
    ("310-266-6226", "3102666226"),
    ("+57 310 266 6226", "573102666226"),  # con indicativo pais: 12 digitos
])
def test_whatsapp_normaliza_separadores(entrada, esperado):
    if len(esperado) == 10:
        assert validar_whatsapp(entrada) == esperado
    else:
        # 12 digitos no es un celular de 10: se rechaza en vez de truncarlo
        with pytest.raises(HTTPException):
            validar_whatsapp(entrada)


@pytest.mark.parametrize("entrada", [
    "310266622",    # 9 digitos
    "6044441122",   # 10 digitos pero fijo: WhatsApp solo funciona en celular
    "0102666226",   # no empieza por 3
])
def test_whatsapp_rechaza_numeros_que_no_sirven_para_enviar(entrada):
    with pytest.raises(HTTPException) as exc:
        validar_whatsapp(entrada)
    assert "10 dígitos" in exc.value.detail or "empezar por 3" in exc.value.detail


def test_whatsapp_es_opcional():
    assert validar_whatsapp("", requerido=False) is None
