"""Testes unitários de app/services/whatsapp_client.py — o cliente HTTP
(`httpx.Client`) é sempre injetado como um mock; nenhuma chamada de rede
real acontece em nenhum teste aqui."""

from unittest.mock import MagicMock

import pytest

from app.core.config import settings
from app.services.whatsapp_client import (
    EnvioWhatsAppFalhou,
    WhatsAppNaoConfigurado,
    enviar_mensagem_texto,
)

TELEFONE = "5511999998888"


@pytest.fixture
def whatsapp_configurado():
    token_original = settings.whatsapp_access_token
    phone_id_original = settings.whatsapp_phone_number_id
    settings.whatsapp_access_token = "token-de-teste"
    settings.whatsapp_phone_number_id = "123456789"
    yield
    settings.whatsapp_access_token = token_original
    settings.whatsapp_phone_number_id = phone_id_original


@pytest.fixture
def client_mock():
    client = MagicMock()
    client.post.return_value = MagicMock(status_code=200, text="")
    return client


def test_envia_mensagem_com_sucesso(whatsapp_configurado, client_mock):
    enviar_mensagem_texto(TELEFONE, "Olá!", client=client_mock)

    client_mock.post.assert_called_once()
    args, kwargs = client_mock.post.call_args
    assert "123456789/messages" in args[0]
    assert kwargs["json"] == {
        "messaging_product": "whatsapp",
        "to": TELEFONE,
        "type": "text",
        "text": {"body": "Olá!"},
    }
    assert kwargs["headers"] == {"Authorization": "Bearer token-de-teste"}


def test_nao_fecha_client_injetado(whatsapp_configurado, client_mock):
    enviar_mensagem_texto(TELEFONE, "Olá!", client=client_mock)

    client_mock.close.assert_not_called()


def test_envio_com_erro_http_levanta_excecao(whatsapp_configurado, client_mock):
    client_mock.post.return_value = MagicMock(status_code=400, text="Bad Request")

    with pytest.raises(EnvioWhatsAppFalhou):
        enviar_mensagem_texto(TELEFONE, "Olá!", client=client_mock)


def test_sem_access_token_levanta_excecao(client_mock):
    token_original = settings.whatsapp_access_token
    phone_id_original = settings.whatsapp_phone_number_id
    settings.whatsapp_access_token = None
    settings.whatsapp_phone_number_id = "123456789"
    try:
        with pytest.raises(WhatsAppNaoConfigurado):
            enviar_mensagem_texto(TELEFONE, "Olá!", client=client_mock)
        client_mock.post.assert_not_called()
    finally:
        settings.whatsapp_access_token = token_original
        settings.whatsapp_phone_number_id = phone_id_original


def test_sem_phone_number_id_levanta_excecao(client_mock):
    token_original = settings.whatsapp_access_token
    phone_id_original = settings.whatsapp_phone_number_id
    settings.whatsapp_access_token = "token-de-teste"
    settings.whatsapp_phone_number_id = None
    try:
        with pytest.raises(WhatsAppNaoConfigurado):
            enviar_mensagem_texto(TELEFONE, "Olá!", client=client_mock)
        client_mock.post.assert_not_called()
    finally:
        settings.whatsapp_access_token = token_original
        settings.whatsapp_phone_number_id = phone_id_original
