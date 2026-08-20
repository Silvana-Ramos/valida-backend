"""Testes unitários de app.services.movimentacao_service.registrar_venda
(RN07 — venda de estoque). A Session do SQLAlchemy é sempre mockada aqui:
nenhum teste conecta a nenhum banco, real ou em memória."""

from decimal import Decimal
from unittest.mock import MagicMock

import pytest

from app.models.lote import LoteORM
from app.schemas.enums import StatusLote
from app.schemas.movimentacao_estoque import VendaEstoqueRequest
from app.services.lote_service import AcaoInvalidaParaStatus, LoteNaoEncontrado
from app.services.movimentacao_service import SaldoInsuficienteParaVenda, registrar_venda

ID_MERCADO = 5
ID_LOTE = 1


def _lote(
    status: StatusLote,
    status_operacional: str,
    quantidade_disponivel: Decimal,
    id_mercado: int = ID_MERCADO,
) -> LoteORM:
    return LoteORM(
        id=ID_LOTE,
        id_mercado=id_mercado,
        status=status,
        status_operacional=status_operacional,
        quantidade_disponivel=quantidade_disponivel,
        quantidade_inicial=quantidade_disponivel,
    )


def _lote_confirmado(status_operacional: str, quantidade_disponivel: Decimal) -> LoteORM:
    return _lote(StatusLote.CONFIRMADO, status_operacional, quantidade_disponivel)


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


def test_venda_parcial_mantem_disponivel():
    lote_orm = _lote_confirmado("disponivel", Decimal("10"))
    db = _mock_db(lote_orm)
    request = VendaEstoqueRequest(quantidade=Decimal("3"))

    resultado = registrar_venda(db, ID_MERCADO, ID_LOTE, request)

    assert lote_orm.quantidade_disponivel == Decimal("7")
    assert lote_orm.status_operacional == "disponivel"
    assert resultado.quantidade_anterior == Decimal("10")
    assert resultado.quantidade_resultante == Decimal("7")
    db.commit.assert_called_once()
    db.rollback.assert_not_called()


def test_venda_total_zera_saldo_e_muda_para_esgotado():
    lote_orm = _lote_confirmado("disponivel", Decimal("5"))
    db = _mock_db(lote_orm)
    request = VendaEstoqueRequest(quantidade=Decimal("5"))

    registrar_venda(db, ID_MERCADO, ID_LOTE, request)

    assert lote_orm.quantidade_disponivel == Decimal("0")
    assert lote_orm.status_operacional == "esgotado"
    db.commit.assert_called_once()


def test_saldo_insuficiente_e_rejeitado_sem_gravar_nada():
    lote_orm = _lote_confirmado("disponivel", Decimal("2"))
    db = _mock_db(lote_orm)
    request = VendaEstoqueRequest(quantidade=Decimal("9"))

    with pytest.raises(SaldoInsuficienteParaVenda):
        registrar_venda(db, ID_MERCADO, ID_LOTE, request)

    assert lote_orm.quantidade_disponivel == Decimal("2")  # inalterado
    assert lote_orm.status_operacional == "disponivel"  # inalterado
    db.add.assert_not_called()
    db.commit.assert_not_called()
    db.rollback.assert_called_once()


def test_lote_ja_esgotado_e_rejeitado_por_saldo_insuficiente():
    lote_orm = _lote_confirmado("esgotado", Decimal("0"))
    db = _mock_db(lote_orm)
    request = VendaEstoqueRequest(quantidade=Decimal("1"))

    with pytest.raises(SaldoInsuficienteParaVenda):
        registrar_venda(db, ID_MERCADO, ID_LOTE, request)

    db.add.assert_not_called()
    db.commit.assert_not_called()
    db.rollback.assert_called_once()


def test_lote_descartado_e_rejeitado_por_saldo_insuficiente():
    lote_orm = _lote_confirmado("descartado", Decimal("0"))
    db = _mock_db(lote_orm)
    request = VendaEstoqueRequest(quantidade=Decimal("1"))

    with pytest.raises(SaldoInsuficienteParaVenda):
        registrar_venda(db, ID_MERCADO, ID_LOTE, request)

    db.add.assert_not_called()
    db.commit.assert_not_called()
    db.rollback.assert_called_once()


def test_lote_de_outro_mercado_retorna_lote_nao_encontrado():
    lote_orm = _lote_confirmado("disponivel", Decimal("10"))  # id_mercado = ID_MERCADO
    db = _mock_db(lote_orm)
    request = VendaEstoqueRequest(quantidade=Decimal("3"))

    with pytest.raises(LoteNaoEncontrado):
        registrar_venda(db, ID_MERCADO + 1, ID_LOTE, request)

    assert lote_orm.quantidade_disponivel == Decimal("10")  # inalterado
    db.add.assert_not_called()
    db.commit.assert_not_called()
    db.rollback.assert_called_once()


def test_lote_nao_confirmado_retorna_acao_invalida_para_status():
    lote_orm = _lote(StatusLote.PENDENTE_CONFIRMACAO, "disponivel", Decimal("10"))
    db = _mock_db(lote_orm)
    request = VendaEstoqueRequest(quantidade=Decimal("3"))

    with pytest.raises(AcaoInvalidaParaStatus):
        registrar_venda(db, ID_MERCADO, ID_LOTE, request)

    db.add.assert_not_called()
    db.commit.assert_not_called()
    db.rollback.assert_called_once()


def test_quantidade_inicial_nunca_e_alterada():
    lote_orm = _lote_confirmado("disponivel", Decimal("10"))
    db = _mock_db(lote_orm)
    request = VendaEstoqueRequest(quantidade=Decimal("4"))

    registrar_venda(db, ID_MERCADO, ID_LOTE, request)

    assert lote_orm.quantidade_inicial == Decimal("10")


def test_rollback_em_falha_no_commit():
    lote_orm = _lote_confirmado("disponivel", Decimal("10"))
    db = _mock_db(lote_orm)
    db.commit.side_effect = RuntimeError("falha simulada de banco")
    request = VendaEstoqueRequest(quantidade=Decimal("3"))

    with pytest.raises(RuntimeError, match="falha simulada de banco"):
        registrar_venda(db, ID_MERCADO, ID_LOTE, request)

    db.rollback.assert_called_once()


def test_garante_um_unico_commit_apos_registrar_movimentacao_e_historico():
    lote_orm = _lote_confirmado("disponivel", Decimal("10"))
    db = _mock_db(lote_orm)
    request = VendaEstoqueRequest(quantidade=Decimal("3"))

    registrar_venda(db, ID_MERCADO, ID_LOTE, request)

    assert db.commit.call_count == 1
    assert db.add.call_count == 2  # movimentacoes_estoque + historico_acoes

    nomes_das_chamadas = [chamada[0] for chamada in db.mock_calls]
    indice_commit = nomes_das_chamadas.index("commit")
    indices_add = [i for i, nome in enumerate(nomes_das_chamadas) if nome == "add"]
    assert all(indice_add < indice_commit for indice_add in indices_add)


def test_select_for_update_com_populate_existing():
    lote_orm = _lote_confirmado("disponivel", Decimal("10"))
    db = _mock_db(lote_orm)
    request = VendaEstoqueRequest(quantidade=Decimal("3"))

    registrar_venda(db, ID_MERCADO, ID_LOTE, request)

    db.get.assert_called_once_with(
        LoteORM, ID_LOTE, with_for_update=True, populate_existing=True
    )
