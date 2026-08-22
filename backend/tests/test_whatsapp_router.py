"""Testes de GET/POST /whatsapp/webhook via TestClient. O processamento
em si (`processar_webhook`) já é coberto exaustivamente por
test_whatsapp_webhook_service.py — aqui o foco é só o que é específico
do router: handshake de verificação, validação de assinatura, e
tratamento de corpo malformado."""

import hashlib
import hmac
import json
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.core.database import get_db
from app.main import app

APP_SECRET = "segredo-de-teste"
VERIFY_TOKEN = "verify-token-de-teste"


def _assinar(corpo: bytes) -> str:
    return "sha256=" + hmac.new(APP_SECRET.encode(), corpo, hashlib.sha256).hexdigest()


@pytest.fixture
def whatsapp_configurado():
    app_secret_original = settings.whatsapp_app_secret
    verify_token_original = settings.whatsapp_verify_token
    settings.whatsapp_app_secret = APP_SECRET
    settings.whatsapp_verify_token = VERIFY_TOKEN
    yield
    settings.whatsapp_app_secret = app_secret_original
    settings.whatsapp_verify_token = verify_token_original


@pytest.fixture
def db_mock():
    db = MagicMock()
    app.dependency_overrides[get_db] = lambda: db
    yield db
    app.dependency_overrides.pop(get_db, None)


@pytest.fixture
def client(db_mock, whatsapp_configurado):
    return TestClient(app)


# --- GET handshake -----------------------------------------------------


def test_get_handshake_com_token_correto_retorna_challenge(client):
    resposta = client.get(
        "/whatsapp/webhook",
        params={"hub.mode": "subscribe", "hub.verify_token": VERIFY_TOKEN, "hub.challenge": "123456"},
    )

    assert resposta.status_code == 200
    assert resposta.text == "123456"


def test_get_handshake_com_token_errado_retorna_403(client):
    resposta = client.get(
        "/whatsapp/webhook",
        params={"hub.mode": "subscribe", "hub.verify_token": "errado", "hub.challenge": "123456"},
    )

    assert resposta.status_code == 403


def test_get_handshake_sem_verify_token_configurado_retorna_403(client):
    settings.whatsapp_verify_token = None

    resposta = client.get(
        "/whatsapp/webhook",
        params={"hub.mode": "subscribe", "hub.verify_token": VERIFY_TOKEN, "hub.challenge": "123456"},
    )

    assert resposta.status_code == 403


# --- POST: assinatura -------------------------------------------------


def test_post_com_assinatura_valida_processa_e_retorna_200(client, db_mock):
    corpo = json.dumps({"entry": []}).encode()

    with patch("app.routers.whatsapp.processar_webhook") as processar_mock:
        resposta = client.post(
            "/whatsapp/webhook",
            content=corpo,
            headers={"X-Hub-Signature-256": _assinar(corpo), "Content-Type": "application/json"},
        )

    assert resposta.status_code == 200
    assert resposta.json() == {"status": "ok"}
    processar_mock.assert_called_once()
    assert processar_mock.call_args[0][0] is db_mock
    assert processar_mock.call_args[0][1] == {"entry": []}


def test_post_sem_assinatura_retorna_403(client):
    corpo = json.dumps({"entry": []}).encode()

    with patch("app.routers.whatsapp.processar_webhook") as processar_mock:
        resposta = client.post(
            "/whatsapp/webhook", content=corpo, headers={"Content-Type": "application/json"}
        )

    assert resposta.status_code == 403
    processar_mock.assert_not_called()


def test_post_com_assinatura_invalida_retorna_403(client):
    corpo = json.dumps({"entry": []}).encode()

    with patch("app.routers.whatsapp.processar_webhook") as processar_mock:
        resposta = client.post(
            "/whatsapp/webhook",
            content=corpo,
            headers={
                "X-Hub-Signature-256": "sha256=assinatura-invalida",
                "Content-Type": "application/json",
            },
        )

    assert resposta.status_code == 403
    processar_mock.assert_not_called()


def test_post_corpo_malformado_retorna_200_ignorado(client):
    corpo = b"isto nao e json"

    with patch("app.routers.whatsapp.processar_webhook") as processar_mock:
        resposta = client.post(
            "/whatsapp/webhook",
            content=corpo,
            headers={"X-Hub-Signature-256": _assinar(corpo), "Content-Type": "application/json"},
        )

    assert resposta.status_code == 200
    assert resposta.json() == {"status": "ignorado"}
    processar_mock.assert_not_called()
