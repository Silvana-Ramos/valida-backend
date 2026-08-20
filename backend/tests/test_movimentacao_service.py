"""Testes unitários de app.services.movimentacao_service.registrar_entrada
(RN07 — entrada de estoque). A Session do SQLAlchemy é sempre mockada aqui:
nenhum teste conecta a nenhum banco, real ou em memória."""

from decimal import Decimal
from unittest.mock import MagicMock

import pytest
from pydantic import ValidationError

from app.models.lote import LoteORM
from app.schemas.enums import StatusLote
from app.schemas.movimentacao_estoque import EntradaEstoqueRequest
from app.services.lote_service import LoteNaoEncontrado
from app.services.movimentacao_service import (
    LoteDescartadoNaoAceitaEntrada,
    registrar_entrada,
)

ID_MERCADO = 5
ID_LOTE = 1


def _lote_confirmado(status_operacional: str, quantidade_disponivel: Decimal) -> LoteORM:
    return LoteORM(
        id=ID_LOTE,
        id_mercado=ID_MERCADO,
        status=StatusLote.CONFIRMADO,
        status_operacional=status_operacional,
        quantidade_disponivel=quantidade_disponivel,
        quantidade_inicial=quantidade_disponivel,
    )


def _mock_db(lote_orm: LoteORM | None) -> MagicMock:
    db = MagicMock()
    db.get.return_value = lote_orm

    def _fake_refresh(obj):
        # Simula o banco atribuindo o PK no INSERT real, já que aqui não
        # há nenhuma conexão de fato.
        if getattr(obj, "id", None) is None:
            obj.id = 999

    db.refresh.side_effect = _fake_refresh
    return db


def test_entrada_em_lote_disponivel_mantem_disponivel():
    lote_orm = _lote_confirmado("disponivel", Decimal("10"))
    db = _mock_db(lote_orm)
    request = EntradaEstoqueRequest(quantidade=Decimal("3"))

    resultado = registrar_entrada(db, ID_MERCADO, ID_LOTE, request)

    assert lote_orm.quantidade_disponivel == Decimal("13")
    assert lote_orm.status_operacional == "disponivel"
    assert lote_orm.quantidade_inicial == Decimal("10")  # nunca alterado
    assert resultado.quantidade_anterior == Decimal("10")
    assert resultado.quantidade_resultante == Decimal("13")
    db.commit.assert_called_once()
    db.rollback.assert_not_called()


def test_entrada_em_lote_esgotado_volta_para_disponivel():
    lote_orm = _lote_confirmado("esgotado", Decimal("0"))
    db = _mock_db(lote_orm)
    request = EntradaEstoqueRequest(quantidade=Decimal("5"))

    registrar_entrada(db, ID_MERCADO, ID_LOTE, request)

    assert lote_orm.status_operacional == "disponivel"
    assert lote_orm.quantidade_disponivel == Decimal("5")
    db.commit.assert_called_once()


def test_entrada_em_lote_descartado_e_rejeitada():
    lote_orm = _lote_confirmado("descartado", Decimal("0"))
    db = _mock_db(lote_orm)
    request = EntradaEstoqueRequest(quantidade=Decimal("5"))

    with pytest.raises(LoteDescartadoNaoAceitaEntrada):
        registrar_entrada(db, ID_MERCADO, ID_LOTE, request)

    assert lote_orm.status_operacional == "descartado"  # inalterado
    assert lote_orm.quantidade_disponivel == Decimal("0")  # inalterado
    db.add.assert_not_called()
    db.commit.assert_not_called()
    db.rollback.assert_called_once()


def test_entrada_em_lote_de_outro_mercado_e_rejeitada():
    lote_orm = _lote_confirmado("disponivel", Decimal("10"))  # id_mercado = ID_MERCADO
    db = _mock_db(lote_orm)
    request = EntradaEstoqueRequest(quantidade=Decimal("5"))

    with pytest.raises(LoteNaoEncontrado):
        registrar_entrada(db, ID_MERCADO + 1, ID_LOTE, request)

    assert lote_orm.quantidade_disponivel == Decimal("10")  # inalterado
    db.add.assert_not_called()
    db.commit.assert_not_called()
    db.rollback.assert_called_once()


@pytest.mark.parametrize("quantidade_invalida", [Decimal("0"), Decimal("-1")])
def test_quantidade_invalida_e_rejeitada_pelo_schema(quantidade_invalida):
    with pytest.raises(ValidationError):
        EntradaEstoqueRequest(quantidade=quantidade_invalida)


def test_rollback_em_falha_no_commit():
    lote_orm = _lote_confirmado("disponivel", Decimal("10"))
    db = _mock_db(lote_orm)
    db.commit.side_effect = RuntimeError("falha simulada de banco")
    request = EntradaEstoqueRequest(quantidade=Decimal("5"))

    with pytest.raises(RuntimeError, match="falha simulada de banco"):
        registrar_entrada(db, ID_MERCADO, ID_LOTE, request)

    db.rollback.assert_called_once()


def test_garante_um_unico_commit_apos_registrar_movimentacao_e_historico():
    lote_orm = _lote_confirmado("disponivel", Decimal("10"))
    db = _mock_db(lote_orm)
    request = EntradaEstoqueRequest(quantidade=Decimal("5"))

    registrar_entrada(db, ID_MERCADO, ID_LOTE, request)

    assert db.commit.call_count == 1
    assert db.add.call_count == 2  # movimentacoes_estoque + historico_acoes

    nomes_das_chamadas = [chamada[0] for chamada in db.mock_calls]
    indice_commit = nomes_das_chamadas.index("commit")
    indices_add = [i for i, nome in enumerate(nomes_das_chamadas) if nome == "add"]
    assert all(indice_add < indice_commit for indice_add in indices_add)
