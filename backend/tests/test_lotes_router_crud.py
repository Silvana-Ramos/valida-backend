"""Testes de POST/GET/PATCH /lotes (CRUD-base, sem movimentação de
estoque) via TestClient.

`get_db` é sobrescrito com uma Session mockada (unittest.mock) — nenhum
teste aqui conecta a nenhum banco, real ou em memória. A dependency de
autenticação (`obter_id_mercado_atual`) roda de verdade, contra um
mapeamento de chaves de teste, não o real. Os testes de `/entrada`,
`/venda`, `/retirada` e `/ajuste` estão em arquivos próprios
(test_lotes_router_{entrada,venda,retirada,ajuste}.py) — este arquivo
cobre só criação, listagem, consulta, edição, confirmação, cancelamento
e histórico."""

from datetime import date, datetime, timedelta
from decimal import Decimal
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.core.database import get_db
from app.main import app
from app.models.historico_acao import HistoricoAcaoORM
from app.models.lote import LoteORM
from app.models.produto import ProdutoORM
from app.schemas.enums import NivelRisco, OrigemCadastro, StatusLote, TipoAcao
from app.schemas.historico_acao import OrigemAcao

ID_MERCADO = 5
OUTRO_MERCADO = 6
ID_LOTE = 1
CHAVE_VALIDA = "chave-teste-mercado-5"
HEADER_VALIDO = {"X-Mercado-Api-Key": CHAVE_VALIDA}
NAO_VENCIDO = date.today() + timedelta(days=10)


def _lote(
    id_lote: int = ID_LOTE,
    id_mercado: int = ID_MERCADO,
    status: StatusLote = StatusLote.PENDENTE_CONFIRMACAO,
    quantidade: Decimal = Decimal("10"),
) -> LoteORM:
    return LoteORM(
        id=id_lote,
        id_mercado=id_mercado,
        id_produto=1,
        quantidade=quantidade,
        numero_lote=None,
        data_validade=NAO_VENCIDO,
        data_entrada=datetime.now(),
        origem_cadastro=OrigemCadastro.TEXTO,
        status=status,
        nivel_risco=NivelRisco.NORMAL,
        dias_restantes=10,
        data_ultima_atualizacao=datetime.now(),
        criado_por=None,
        preco_custo=None,
        status_operacional="disponivel",
        quantidade_disponivel=quantidade,
        quantidade_inicial=quantidade,
    )


@pytest.fixture
def db_mock():
    db = MagicMock()

    produto_q = MagicMock()
    produto_q.filter.return_value.first.return_value = None
    lote_q = MagicMock()
    lote_q.filter.return_value.all.return_value = []
    lote_q.filter.return_value.filter.return_value.all.return_value = []
    historico_q = MagicMock()
    historico_q.filter.return_value.order_by.return_value.all.return_value = []

    def query_side_effect(model):
        return {
            ProdutoORM: produto_q,
            LoteORM: lote_q,
            HistoricoAcaoORM: historico_q,
        }.get(model, MagicMock())

    db.query.side_effect = query_side_effect
    db.produto_q = produto_q
    db.lote_q = lote_q
    db.historico_q = historico_q

    def refresh_side_effect(obj):
        if getattr(obj, "id", None) is None:
            obj.id = 999

    db.refresh.side_effect = refresh_side_effect
    app.dependency_overrides[get_db] = lambda: db
    yield db
    app.dependency_overrides.pop(get_db, None)


@pytest.fixture
def chaves_de_teste():
    originais = settings.mercado_api_keys
    settings.mercado_api_keys = {CHAVE_VALIDA: ID_MERCADO}
    yield
    settings.mercado_api_keys = originais


@pytest.fixture
def client(db_mock, chaves_de_teste):
    return TestClient(app)


# --- autenticação ---------------------------------------------------------


def test_post_sem_header_retorna_401(client, db_mock):
    resposta = client.post(
        "/lotes",
        json={"produto_nome": "Pao Frances", "quantidade": 10, "data_validade": str(NAO_VENCIDO)},
    )

    assert resposta.status_code == 401
    db_mock.query.assert_not_called()


def test_get_lista_chave_invalida_retorna_401(client, db_mock):
    resposta = client.get("/lotes", headers={"X-Mercado-Api-Key": "chave-errada"})

    assert resposta.status_code == 401


# --- criação ---------------------------------------------------------------


def test_criar_lote_retorna_201(client, db_mock):
    resposta = client.post(
        "/lotes",
        json={"produto_nome": "Pao Frances", "quantidade": 10, "data_validade": str(NAO_VENCIDO)},
        headers=HEADER_VALIDO,
    )

    assert resposta.status_code == 201
    corpo = resposta.json()
    assert corpo["id_mercado"] == ID_MERCADO
    assert corpo["status"] == "pendente_confirmacao"
    assert corpo["quantidade"] == 10


# --- listagem ----------------------------------------------------------


def test_listar_lotes_retorna_200(client, db_mock):
    db_mock.lote_q.filter.return_value.all.return_value = [
        _lote(id_lote=1),
        _lote(id_lote=2),
    ]

    resposta = client.get("/lotes", headers=HEADER_VALIDO)

    assert resposta.status_code == 200
    assert len(resposta.json()) == 2


def test_listar_lotes_com_status_retorna_200(client, db_mock):
    db_mock.lote_q.filter.return_value.filter.return_value.all.return_value = [
        _lote(id_lote=1, status=StatusLote.CONFIRMADO)
    ]

    resposta = client.get("/lotes?status=confirmado", headers=HEADER_VALIDO)

    assert resposta.status_code == 200
    corpo = resposta.json()
    assert len(corpo) == 1
    assert corpo[0]["status"] == "confirmado"


def test_listar_lotes_vazio_retorna_200(client, db_mock):
    resposta = client.get("/lotes", headers=HEADER_VALIDO)

    assert resposta.status_code == 200
    assert resposta.json() == []


# --- consulta ------------------------------------------------------------


def test_obter_lote_retorna_200(client, db_mock):
    db_mock.get.return_value = _lote()

    resposta = client.get(f"/lotes/{ID_LOTE}", headers=HEADER_VALIDO)

    assert resposta.status_code == 200
    assert resposta.json()["id"] == ID_LOTE


def test_obter_lote_nao_encontrado_retorna_404(client, db_mock):
    db_mock.get.return_value = None

    resposta = client.get(f"/lotes/{ID_LOTE}", headers=HEADER_VALIDO)

    assert resposta.status_code == 404


def test_obter_lote_de_outro_mercado_retorna_404(client, db_mock):
    db_mock.get.return_value = _lote(id_mercado=OUTRO_MERCADO)

    resposta = client.get(f"/lotes/{ID_LOTE}", headers=HEADER_VALIDO)

    assert resposta.status_code == 404


# --- edição --------------------------------------------------------------


def test_editar_lote_retorna_200(client, db_mock):
    db_mock.get.return_value = _lote(status=StatusLote.PENDENTE_CONFIRMACAO)

    resposta = client.patch(
        f"/lotes/{ID_LOTE}", json={"quantidade": 25}, headers=HEADER_VALIDO
    )

    assert resposta.status_code == 200
    assert resposta.json()["quantidade"] == 25


def test_editar_lote_nao_encontrado_retorna_404(client, db_mock):
    db_mock.get.return_value = None

    resposta = client.patch(
        f"/lotes/{ID_LOTE}", json={"quantidade": 25}, headers=HEADER_VALIDO
    )

    assert resposta.status_code == 404


def test_editar_lote_de_outro_mercado_retorna_404(client, db_mock):
    db_mock.get.return_value = _lote(id_mercado=OUTRO_MERCADO)

    resposta = client.patch(
        f"/lotes/{ID_LOTE}", json={"quantidade": 25}, headers=HEADER_VALIDO
    )

    assert resposta.status_code == 404


def test_editar_lote_status_invalido_retorna_409(client, db_mock):
    db_mock.get.return_value = _lote(status=StatusLote.CONFIRMADO)

    resposta = client.patch(
        f"/lotes/{ID_LOTE}", json={"quantidade": 25}, headers=HEADER_VALIDO
    )

    assert resposta.status_code == 409


# --- confirmação -----------------------------------------------------------


def test_confirmar_lote_retorna_200(client, db_mock):
    db_mock.get.return_value = _lote(status=StatusLote.PENDENTE_CONFIRMACAO)

    resposta = client.post(f"/lotes/{ID_LOTE}/confirmar", headers=HEADER_VALIDO)

    assert resposta.status_code == 200
    assert resposta.json()["status"] == "confirmado"


def test_confirmar_lote_nao_encontrado_retorna_404(client, db_mock):
    db_mock.get.return_value = None

    resposta = client.post(f"/lotes/{ID_LOTE}/confirmar", headers=HEADER_VALIDO)

    assert resposta.status_code == 404


def test_confirmar_lote_de_outro_mercado_retorna_404(client, db_mock):
    db_mock.get.return_value = _lote(id_mercado=OUTRO_MERCADO)

    resposta = client.post(f"/lotes/{ID_LOTE}/confirmar", headers=HEADER_VALIDO)

    assert resposta.status_code == 404


def test_confirmar_lote_ja_confirmado_retorna_409(client, db_mock):
    db_mock.get.return_value = _lote(status=StatusLote.CONFIRMADO)

    resposta = client.post(f"/lotes/{ID_LOTE}/confirmar", headers=HEADER_VALIDO)

    assert resposta.status_code == 409


# --- cancelamento ----------------------------------------------------------


def test_cancelar_lote_retorna_204(client, db_mock):
    db_mock.get.return_value = _lote(status=StatusLote.PENDENTE_CONFIRMACAO)

    resposta = client.post(f"/lotes/{ID_LOTE}/cancelar", headers=HEADER_VALIDO)

    assert resposta.status_code == 204
    db_mock.delete.assert_called_once()


def test_cancelar_lote_nao_encontrado_retorna_404(client, db_mock):
    db_mock.get.return_value = None

    resposta = client.post(f"/lotes/{ID_LOTE}/cancelar", headers=HEADER_VALIDO)

    assert resposta.status_code == 404
    db_mock.delete.assert_not_called()


def test_cancelar_lote_de_outro_mercado_retorna_404(client, db_mock):
    db_mock.get.return_value = _lote(id_mercado=OUTRO_MERCADO)

    resposta = client.post(f"/lotes/{ID_LOTE}/cancelar", headers=HEADER_VALIDO)

    assert resposta.status_code == 404
    db_mock.delete.assert_not_called()


def test_cancelar_lote_status_invalido_retorna_409(client, db_mock):
    db_mock.get.return_value = _lote(status=StatusLote.CONFIRMADO)

    resposta = client.post(f"/lotes/{ID_LOTE}/cancelar", headers=HEADER_VALIDO)

    assert resposta.status_code == 409
    db_mock.delete.assert_not_called()


# --- histórico -------------------------------------------------------------


def test_historico_do_lote_retorna_lista(client, db_mock):
    db_mock.get.return_value = _lote()
    db_mock.historico_q.filter.return_value.order_by.return_value.all.return_value = [
        HistoricoAcaoORM(
            id=1,
            id_mercado=ID_MERCADO,
            id_lote=ID_LOTE,
            tipo_acao=TipoAcao.CADASTRO,
            descricao="Lote criado.",
            origem=OrigemAcao.USUARIO,
            data_hora=datetime.now(),
        )
    ]

    resposta = client.get(f"/lotes/{ID_LOTE}/historico", headers=HEADER_VALIDO)

    assert resposta.status_code == 200
    corpo = resposta.json()
    assert len(corpo) == 1
    assert corpo[0]["tipo_acao"] == "cadastro"


def test_historico_do_lote_nao_encontrado_retorna_404(client, db_mock):
    db_mock.get.return_value = None

    resposta = client.get(f"/lotes/{ID_LOTE}/historico", headers=HEADER_VALIDO)

    assert resposta.status_code == 404


def test_historico_do_lote_de_outro_mercado_retorna_404(client, db_mock):
    db_mock.get.return_value = _lote(id_mercado=OUTRO_MERCADO)

    resposta = client.get(f"/lotes/{ID_LOTE}/historico", headers=HEADER_VALIDO)

    assert resposta.status_code == 404


# --- regressão: GET reflete quantidade_disponivel após movimentação -------
#
# Bug de produção: POST /lotes/{id}/venda atualizava lotes.quantidade_disponivel
# corretamente (movimentação registrada com quantidade_resultante correto),
# mas GET /lotes e GET /lotes/{id} continuavam devolvendo o campo legado
# `quantidade` (valor de cadastro, nunca tocado por movimentações), em vez do
# estoque disponível atual.


def test_venda_de_1_em_lote_com_10_faz_get_unico_retornar_9(client, db_mock):
    db_mock.get.return_value = _lote(status=StatusLote.CONFIRMADO, quantidade=Decimal("10"))

    resposta_venda = client.post(
        f"/lotes/{ID_LOTE}/venda", json={"quantidade": 1}, headers=HEADER_VALIDO
    )
    assert resposta_venda.status_code == 201
    assert Decimal(str(resposta_venda.json()["quantidade_resultante"])) == Decimal("9")

    resposta_get = client.get(f"/lotes/{ID_LOTE}", headers=HEADER_VALIDO)

    assert resposta_get.status_code == 200
    assert Decimal(str(resposta_get.json()["quantidade"])) == Decimal("9")


def test_venda_de_1_em_lote_com_10_faz_get_lista_retornar_9(client, db_mock):
    lote_orm = _lote(status=StatusLote.CONFIRMADO, quantidade=Decimal("10"))
    db_mock.get.return_value = lote_orm
    db_mock.lote_q.filter.return_value.all.return_value = [lote_orm]

    resposta_venda = client.post(
        f"/lotes/{ID_LOTE}/venda", json={"quantidade": 1}, headers=HEADER_VALIDO
    )
    assert resposta_venda.status_code == 201

    resposta_lista = client.get("/lotes", headers=HEADER_VALIDO)

    assert resposta_lista.status_code == 200
    corpo = resposta_lista.json()
    assert len(corpo) == 1
    assert Decimal(str(corpo[0]["quantidade"])) == Decimal("9")
