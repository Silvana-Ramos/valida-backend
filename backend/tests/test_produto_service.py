"""Testes unitários de app/services/produto_service.py (Session mockada,
sem banco real). `listar` passou a exigir id_mercado (RN05) — cobre o
filtro aplicado."""

from unittest.mock import MagicMock

import pytest

from app.models.produto import ProdutoORM
from app.schemas.produto import CategoriaProduto, UnidadeMedida
from app.services import produto_service

ID_MERCADO = 5


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
    return MagicMock()


def test_listar_filtra_por_mercado(db_mock):
    db_mock.query.return_value.filter.return_value.all.return_value = [
        _produto(1, nome="Pao"),
        _produto(2, nome="Bolo"),
    ]

    resultado = produto_service.listar(db_mock, ID_MERCADO)

    assert len(resultado) == 2
    assert {p.nome for p in resultado} == {"Pao", "Bolo"}
    db_mock.query.return_value.filter.assert_called_once()


def test_listar_vazio(db_mock):
    db_mock.query.return_value.filter.return_value.all.return_value = []

    assert produto_service.listar(db_mock, ID_MERCADO) == []
