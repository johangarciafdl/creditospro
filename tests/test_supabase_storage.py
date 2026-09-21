"""Detalles del protocolo de Supabase Storage que no son los evidentes."""
import httpx
import pytest

from app.utils import supabase_storage as st


def _resp(codigo: int, cuerpo=None) -> httpx.Response:
    if cuerpo is None:
        return httpx.Response(codigo, request=httpx.Request("GET", "http://x"))
    return httpx.Response(codigo, json=cuerpo, request=httpx.Request("GET", "http://x"))


def test_un_objeto_que_falta_llega_como_400_no_como_404():
    """Storage responde 400 y pone el 404 real dentro del cuerpo.

    Tratar ese 400 como un error de verdad llenaba el registro de avisos
    por cada imagen ausente, que es justo lo que esconde los avisos que si
    importan.
    """
    assert st._es_no_encontrado(_resp(400, {
        "statusCode": "404", "error": "not_found",
        "message": "Object not found", "code": "NoSuchKey",
    }))
    assert st._es_no_encontrado(_resp(400, {
        "statusCode": "404", "error": "Bucket not found", "code": "NoSuchBucket",
    }))
    assert st._es_no_encontrado(_resp(404))


@pytest.mark.parametrize("codigo,cuerpo", [
    (400, {"statusCode": "400", "error": "invalid_request"}),
    (401, {"statusCode": "401", "error": "Unauthorized"}),
    (413, {"statusCode": "413", "error": "Payload too large"}),
    (500, None),
])
def test_los_errores_de_verdad_si_se_registran(codigo, cuerpo):
    assert not st._es_no_encontrado(_resp(codigo, cuerpo))


def test_un_cuerpo_que_no_es_json_no_revienta():
    r = httpx.Response(400, text="<html>502</html>",
                       request=httpx.Request("GET", "http://x"))
    assert st._es_no_encontrado(r) is False


def test_sin_credenciales_no_se_intenta_hablar_con_storage(monkeypatch):
    """En pruebas y en local no hay claves, y nada debe salir a la red."""
    monkeypatch.setattr(st, "SUPABASE_URL", "")
    monkeypatch.setattr(st, "SUPABASE_SERVICE_KEY", "")
    assert st.disponible() is False
    assert st.descargar("lo/que/sea.jpg") is None
    assert st.borrar("lo/que/sea.jpg") is False
    with pytest.raises(st.ErrorStorage):
        st.subir("lo/que/sea.jpg", b"x", "image/jpeg")


def test_la_clave_no_viaja_en_la_url():
    """Una clave en la URL acaba en los registros del proxy y del navegador."""
    monkeypatch_url = st._url("empresa_1/cliente/x.jpg")
    assert "key" not in monkeypatch_url.lower()
    assert st.BUCKET in monkeypatch_url
