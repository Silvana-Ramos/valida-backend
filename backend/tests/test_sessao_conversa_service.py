"""Testes unitários de app/services/sessao_conversa_service.py (Session
mockada, sem banco real)."""

from datetime import datetime
from unittest.mock import MagicMock

import pytest

from app.models.sessao_conversa import SessaoConversaORM
from app.services import sessao_conversa_service
from app.services.sessao_conversa_service import SessaoConversaNaoEncontrada

ID_MERCADO = 5
OUTRO_MERCADO = 6
ID_USUARIO = 1


def _sessao(
    id_usuario: int = ID_USUARIO,
    id_mercado: int = ID_MERCADO,
    estado: str = "aguardando_produto",
    dados_parciais: dict | None = None,
) -> SessaoConversaORM:
    return SessaoConversaORM(
        id_usuario=id_usuario,
        id_mercado=id_mercado,
        estado=estado,
        dados_parciais=dados_parciais or {},
        criado_em=datetime.now(),
        atualizado_em=datetime.now(),
    )


@pytest.fixture
def db_mock():
    return MagicMock()


# --- obter ---------------------------------------------------------------


def test_obter_retorna_sessao_existente(db_mock):
    db_mock.get.return_value = _sessao(estado="aguardando_quantidade")

    sessao = sessao_conversa_service.obter(db_mock, ID_MERCADO, ID_USUARIO)

    assert sessao is not None
    assert sessao.estado == "aguardando_quantidade"


def test_obter_sem_sessao_retorna_none(db_mock):
    db_mock.get.return_value = None

    assert sessao_conversa_service.obter(db_mock, ID_MERCADO, ID_USUARIO) is None


def test_obter_sessao_de_outro_mercado_retorna_none(db_mock):
    db_mock.get.return_value = _sessao(id_mercado=OUTRO_MERCADO)

    assert sessao_conversa_service.obter(db_mock, ID_MERCADO, ID_USUARIO) is None


# --- iniciar ---------------------------------------------------------------


def test_iniciar_cria_sessao_nova(db_mock):
    db_mock.get.return_value = None

    sessao = sessao_conversa_service.iniciar(
        db_mock, ID_MERCADO, ID_USUARIO, "aguardando_produto"
    )

    assert sessao.id_usuario == ID_USUARIO
    assert sessao.id_mercado == ID_MERCADO
    assert sessao.estado == "aguardando_produto"
    assert sessao.dados_parciais == {}
    db_mock.add.assert_called_once()
    db_mock.commit.assert_called_once()


def test_iniciar_substitui_sessao_existente(db_mock):
    db_mock.get.return_value = _sessao(
        estado="aguardando_confirmacao_cadastro", dados_parciais={"produto_nome": "Pao"}
    )

    sessao = sessao_conversa_service.iniciar(
        db_mock, ID_MERCADO, ID_USUARIO, "aguardando_produto", dados_parciais={"x": 1}
    )

    assert sessao.estado == "aguardando_produto"
    assert sessao.dados_parciais == {"x": 1}  # substitui, não mescla
    db_mock.add.assert_not_called()
    db_mock.commit.assert_called_once()


# --- avancar ---------------------------------------------------------------


def test_avancar_atualiza_estado_e_mescla_dados(db_mock):
    db_mock.get.return_value = _sessao(
        estado="aguardando_produto", dados_parciais={"produto_nome": "Pao"}
    )

    sessao = sessao_conversa_service.avancar(
        db_mock, ID_MERCADO, ID_USUARIO, "aguardando_quantidade", {"quantidade": 10}
    )

    assert sessao.estado == "aguardando_quantidade"
    assert sessao.dados_parciais == {"produto_nome": "Pao", "quantidade": 10}


def test_avancar_sem_sessao_levanta_nao_encontrada(db_mock):
    db_mock.get.return_value = None

    with pytest.raises(SessaoConversaNaoEncontrada):
        sessao_conversa_service.avancar(db_mock, ID_MERCADO, ID_USUARIO, "aguardando_quantidade")


def test_avancar_sessao_de_outro_mercado_levanta_nao_encontrada(db_mock):
    db_mock.get.return_value = _sessao(id_mercado=OUTRO_MERCADO)

    with pytest.raises(SessaoConversaNaoEncontrada):
        sessao_conversa_service.avancar(db_mock, ID_MERCADO, ID_USUARIO, "aguardando_quantidade")


# --- encerrar ------------------------------------------------------------


def test_encerrar_remove_sessao_existente(db_mock):
    sessao_orm = _sessao()
    db_mock.get.return_value = sessao_orm

    sessao_conversa_service.encerrar(db_mock, ID_MERCADO, ID_USUARIO)

    db_mock.delete.assert_called_once_with(sessao_orm)
    db_mock.commit.assert_called_once()


def test_encerrar_sem_sessao_e_idempotente(db_mock):
    db_mock.get.return_value = None

    sessao_conversa_service.encerrar(db_mock, ID_MERCADO, ID_USUARIO)

    db_mock.delete.assert_not_called()
    db_mock.commit.assert_not_called()


def test_encerrar_sessao_de_outro_mercado_e_idempotente(db_mock):
    db_mock.get.return_value = _sessao(id_mercado=OUTRO_MERCADO)

    sessao_conversa_service.encerrar(db_mock, ID_MERCADO, ID_USUARIO)

    db_mock.delete.assert_not_called()
    db_mock.commit.assert_not_called()
