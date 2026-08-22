"""Testes unitários de app/core/security.py — cobre só
validar_assinatura_whatsapp(); as outras duas funções do arquivo
(obter_id_mercado_atual, obter_admin_autenticado) já são exercitadas
indiretamente pelos testes de router (test_lotes_router_*.py,
test_mercados_router.py, test_usuarios_router.py)."""

import hashlib
import hmac

import pytest

from app.core.config import settings
from app.core.security import validar_assinatura_whatsapp

SEGREDO = "segredo-de-teste"
CORPO = b'{"entry": [{"changes": []}]}'


def _assinatura_valida(corpo: bytes, segredo: str) -> str:
    return "sha256=" + hmac.new(segredo.encode(), corpo, hashlib.sha256).hexdigest()


@pytest.fixture
def app_secret_configurado():
    original = settings.whatsapp_app_secret
    settings.whatsapp_app_secret = SEGREDO
    yield
    settings.whatsapp_app_secret = original


def test_assinatura_valida_retorna_true(app_secret_configurado):
    assinatura = _assinatura_valida(CORPO, SEGREDO)

    assert validar_assinatura_whatsapp(CORPO, assinatura) is True


def test_segredo_errado_retorna_false(app_secret_configurado):
    assinatura = _assinatura_valida(CORPO, "segredo-errado")

    assert validar_assinatura_whatsapp(CORPO, assinatura) is False


def test_corpo_alterado_retorna_false(app_secret_configurado):
    assinatura = _assinatura_valida(CORPO, SEGREDO)

    assert validar_assinatura_whatsapp(b'{"entry": []}', assinatura) is False


def test_header_ausente_retorna_false(app_secret_configurado):
    assert validar_assinatura_whatsapp(CORPO, None) is False


def test_app_secret_nao_configurado_retorna_false():
    original = settings.whatsapp_app_secret
    settings.whatsapp_app_secret = None
    try:
        assinatura = _assinatura_valida(CORPO, SEGREDO)
        assert validar_assinatura_whatsapp(CORPO, assinatura) is False
    finally:
        settings.whatsapp_app_secret = original
