"""Testes de camada HTTP de app/routers/relatorios_acao_diaria.py, usando
uma aplicação FastAPI isolada (não app.main) — não depende do router
estar registrado em main.py. Os services são mockados via patch no
próprio módulo de origem; a regra de negócio deles já é testada
exaustivamente em test_relatorio_acao_diaria_service.py e
test_acao_preventiva_service.py — aqui só se verifica a camada HTTP
(status, response_model, mapeamento de exceção, repasse de parâmetros)."""

from datetime import date, datetime
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.database import get_db
from app.core.security import obter_id_mercado_atual
from app.routers import relatorios_acao_diaria
from app.schemas.acao_preventiva import (
    AcaoPreventiva,
    AcaoPreventivaCreateRequest,
    AcaoPreventivaEditRequest,
)
from app.schemas.item_relatorio_diario import ItemRelatorioDiario
from app.schemas.relatorio_acao_diaria import RelatorioAcaoDiario
from app.services.acao_preventiva_service import (
    AcaoPreventivaNaoEncontrada,
    ItemRelatorioNaoEncontrado,
    StatusAcaoPreventivaInvalido,
)
from app.services.relatorio_acao_diaria_service import RelatorioNaoEncontrado
from app.services.usuario_service import UsuarioNaoEncontrado

app_teste = FastAPI()
app_teste.include_router(relatorios_acao_diaria.router)

# Valor deliberadamente fora do corpo/URL de qualquer teste, para provar
# que id_mercado vem só do dependency override.
ID_MERCADO = 999


def _relatorio() -> RelatorioAcaoDiario:
    return RelatorioAcaoDiario(
        id=1,
        id_mercado=ID_MERCADO,
        data_referencia=date.today(),
        gerado_em=datetime.now(),
        status="gerado",
        qtd_vencidos=0,
        qtd_vence_hoje=0,
        qtd_urgentes=0,
        qtd_risco=0,
        qtd_atencao=0,
        valor_em_risco=Decimal("0"),
        total_acoes_recomendadas=0,
        total_acoes_realizadas=0,
    )


def _item(id_item: int) -> ItemRelatorioDiario:
    return ItemRelatorioDiario(
        id=id_item,
        id_relatorio=42,
        id_produto=1,
        id_lote=1,
        data_validade=date.today(),
        quantidade_disponivel=Decimal("10"),
        preco_custo=Decimal("2.50"),
        dias_restantes=2,
        classificacao_validade="urgente",
        prioridade="ALTA",
        valor_em_risco=Decimal("25.00"),
        acao_recomendada="Priorizar venda seguindo FEFO.",
    )


def _acao(id_acao: int = 1, status: str = "recomendada") -> AcaoPreventiva:
    return AcaoPreventiva(
        id=id_acao,
        id_item_relatorio=7,
        id_usuario_responsavel=None,
        acao_recomendada="Priorizar venda seguindo FEFO.",
        acao_realizada=None,
        status=status,
        data_inicio=None,
        data_fim=None,
        resultado_operacional=None,
        observacao=None,
        criada_em=datetime.now(),
        atualizada_em=datetime.now(),
    )


@pytest.fixture
def db_mock():
    db = MagicMock(name="db")
    app_teste.dependency_overrides[get_db] = lambda: db
    yield db
    app_teste.dependency_overrides.pop(get_db, None)


@pytest.fixture
def mercado_mock():
    app_teste.dependency_overrides[obter_id_mercado_atual] = lambda: ID_MERCADO
    yield ID_MERCADO
    app_teste.dependency_overrides.pop(obter_id_mercado_atual, None)


@pytest.fixture
def client(db_mock, mercado_mock):
    return TestClient(app_teste)


# =============================================================================
# POST /relatorios-acao-diaria
# =============================================================================


def test_post_relatorio_chama_service_e_retorna_200(client, db_mock):
    relatorio_esperado = _relatorio()

    with patch(
        "app.services.relatorio_acao_diaria_service.gerar_ou_obter",
        return_value=relatorio_esperado,
    ) as mock_gerar:
        resposta = client.post("/relatorios-acao-diaria")

    assert resposta.status_code == 200
    assert resposta.json()["id"] == 1
    mock_gerar.assert_called_once_with(db_mock, ID_MERCADO)


def test_post_relatorio_id_mercado_vem_do_dependency_override(client, db_mock):
    relatorio_esperado = _relatorio()

    with patch(
        "app.services.relatorio_acao_diaria_service.gerar_ou_obter",
        return_value=relatorio_esperado,
    ) as mock_gerar:
        # Nada na requisição (sem corpo, sem query) menciona
        # ID_MERCADO=999 — só o dependency override o fornece.
        resposta = client.post("/relatorios-acao-diaria")

    assert resposta.status_code == 200
    mock_gerar.assert_called_once_with(db_mock, ID_MERCADO)


# =============================================================================
# GET /relatorios-acao-diaria/{id_relatorio}/itens
# =============================================================================


def test_get_itens_sucesso_chama_service_com_id_relatorio_da_url(client, db_mock):
    itens_esperados = [_item(1), _item(2)]

    with patch(
        "app.services.relatorio_acao_diaria_service.listar_itens",
        return_value=itens_esperados,
    ) as mock_listar:
        resposta = client.get("/relatorios-acao-diaria/42/itens")

    assert resposta.status_code == 200
    assert len(resposta.json()) == 2
    mock_listar.assert_called_once_with(db_mock, ID_MERCADO, 42)


def test_get_itens_lista_vazia_retorna_200(client, db_mock):
    with patch(
        "app.services.relatorio_acao_diaria_service.listar_itens", return_value=[]
    ):
        resposta = client.get("/relatorios-acao-diaria/42/itens")

    assert resposta.status_code == 200
    assert resposta.json() == []


def test_get_itens_relatorio_nao_encontrado_retorna_404(client, db_mock):
    with patch(
        "app.services.relatorio_acao_diaria_service.listar_itens",
        side_effect=RelatorioNaoEncontrado(42),
    ):
        resposta = client.get("/relatorios-acao-diaria/42/itens")

    assert resposta.status_code == 404
    assert resposta.json()["detail"] == "Relatório não encontrado."


# =============================================================================
# POST /relatorios-acao-diaria/itens/{id_item_relatorio}/acoes
# =============================================================================


def test_post_acao_sucesso_chama_service_com_request_correto(client, db_mock):
    acao_esperada = _acao(id_acao=10)
    payload = {"observacao": "acompanhar de perto"}

    with patch(
        "app.services.acao_preventiva_service.registrar", return_value=acao_esperada
    ) as mock_registrar:
        resposta = client.post("/relatorios-acao-diaria/itens/7/acoes", json=payload)

    assert resposta.status_code == 201
    assert resposta.json()["id"] == 10
    mock_registrar.assert_called_once_with(
        db_mock, ID_MERCADO, 7, AcaoPreventivaCreateRequest(observacao="acompanhar de perto")
    )


def test_post_acao_item_nao_encontrado_retorna_404(client, db_mock):
    with patch(
        "app.services.acao_preventiva_service.registrar",
        side_effect=ItemRelatorioNaoEncontrado(7),
    ):
        resposta = client.post("/relatorios-acao-diaria/itens/7/acoes", json={})

    assert resposta.status_code == 404
    assert resposta.json()["detail"] == "Item do relatório não encontrado."


def test_post_acao_usuario_responsavel_invalido_retorna_404(client, db_mock):
    with patch(
        "app.services.acao_preventiva_service.registrar",
        side_effect=UsuarioNaoEncontrado(999),
    ):
        resposta = client.post(
            "/relatorios-acao-diaria/itens/7/acoes", json={"id_usuario_responsavel": 999}
        )

    assert resposta.status_code == 404
    assert resposta.json()["detail"] == "Usuário responsável não encontrado."


# =============================================================================
# PATCH /relatorios-acao-diaria/acoes/{id_acao_preventiva}
# =============================================================================


def test_patch_acao_sucesso_chama_service_com_request_correto(client, db_mock):
    acao_atualizada = _acao(id_acao=10, status="em_andamento")
    payload = {"status": "em_andamento"}

    with patch(
        "app.services.acao_preventiva_service.atualizar", return_value=acao_atualizada
    ) as mock_atualizar:
        resposta = client.patch("/relatorios-acao-diaria/acoes/10", json=payload)

    assert resposta.status_code == 200
    assert resposta.json()["status"] == "em_andamento"
    mock_atualizar.assert_called_once_with(
        db_mock, ID_MERCADO, 10, AcaoPreventivaEditRequest(status="em_andamento")
    )


def test_patch_acao_nao_encontrada_retorna_404(client, db_mock):
    with patch(
        "app.services.acao_preventiva_service.atualizar",
        side_effect=AcaoPreventivaNaoEncontrada(10),
    ):
        resposta = client.patch("/relatorios-acao-diaria/acoes/10", json={"observacao": "x"})

    assert resposta.status_code == 404
    assert resposta.json()["detail"] == "Ação preventiva não encontrada."


def test_patch_acao_status_invalido_retorna_422(client, db_mock):
    with patch(
        "app.services.acao_preventiva_service.atualizar",
        side_effect=StatusAcaoPreventivaInvalido("xyz"),
    ):
        resposta = client.patch("/relatorios-acao-diaria/acoes/10", json={"status": "xyz"})

    assert resposta.status_code == 422
    assert "Status inválido" in resposta.json()["detail"]
