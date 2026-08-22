"""Testes de GET /produtos via TestClient.

`get_db` é sobrescrito com uma Session mockada (unittest.mock) — nenhum
teste aqui conecta a nenhum banco, real ou em memória. A dependency de
autenticação (`obter_id_mercado_atual`) roda de verdade, contra um
mapeamento de chaves de teste, não o real."""

from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.core.database import get_db
from app.main import app
from app.models.produto import ProdutoORM
from app.schemas.produto import CategoriaProduto, UnidadeMedida

ID_MERCADO = 5
CHAVE_VALIDA = "chave-teste-mercado-5"
HEADER_VALIDO = {"X-Mercado-Api-Key": CHAVE_VALIDA}


def _produto(id_produto: int, id_mercado: int = ID_MERCADO, nome: str = "Pao Frances") -> ProdutoORM:
    return ProdutoORM(
        id=id_produto,
        id_mercado=id_mercado,
        nome=nome,
        categoria=CategoriaProduto.PADARIA,
        unidade_medida=UnidadeMedida.KG,
        preco_venda=None,
    )


@pytest.fixture
def db_mock():
    db = MagicMock()
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


def test_sem_header_retorna_401(client, db_mock):
    resposta = client.get("/produtos")

    assert resposta.status_code == 401
    db_mock.query.assert_not_called()


def test_chave_invalida_retorna_401(client, db_mock):
    resposta = client.get("/produtos", headers={"X-Mercado-Api-Key": "chave-errada"})

    assert resposta.status_code == 401


def test_listar_produtos_retorna_200(client, db_mock):
    db_mock.query.return_value.filter.return_value.all.return_value = [
        _produto(1, nome="Pao"),
        _produto(2, nome="Bolo"),
    ]

    resposta = client.get("/produtos", headers=HEADER_VALIDO)

    assert resposta.status_code == 200
    corpo = resposta.json()
    assert len(corpo) == 2
    assert {p["nome"] for p in corpo} == {"Pao", "Bolo"}


def test_listar_produtos_vazio_retorna_200(client, db_mock):
    db_mock.query.return_value.filter.return_value.all.return_value = []

    resposta = client.get("/produtos", headers=HEADER_VALIDO)

    assert resposta.status_code == 200
    assert resposta.json() == []


def test_id_mercado_em_query_string_e_ignorado(client, db_mock):
    # id_mercado deixou de ser um parâmetro de query aceito pelo endpoint
    # (RN05) — a listagem sempre usa o id_mercado resolvido do header.
    db_mock.query.return_value.filter.return_value.all.return_value = [
        _produto(1, id_mercado=ID_MERCADO, nome="Pao"),
    ]

    resposta = client.get("/produtos?id_mercado=999999", headers=HEADER_VALIDO)

    assert resposta.status_code == 200
    assert len(resposta.json()) == 1
