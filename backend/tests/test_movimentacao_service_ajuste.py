"""Testes unitários de app.services.movimentacao_service.registrar_ajuste
(RN07 — ajuste de estoque). A Session do SQLAlchemy é sempre mockada
aqui: nenhum teste conecta a nenhum banco, real ou em memória."""

from decimal import Decimal
from unittest.mock import MagicMock

import pytest

from app.models.lote import LoteORM
from app.models.movimentacao_estoque import MovimentacaoEstoqueORM
from app.schemas.enums import StatusLote, TipoAcao
from app.schemas.movimentacao_estoque import AjusteEstoqueRequest, SentidoMovimentacao, TipoMovimentacao
from app.services.lote_service import AcaoInvalidaParaStatus, LoteNaoEncontrado
from app.services.movimentacao_service import (
    LoteDescartadoNaoAceitaEntrada,
    MovimentacaoEstornadaNaoEncontrada,
    MovimentacaoJaEstornada,
    SaldoInsuficienteParaAjuste,
    registrar_ajuste,
)

ID_MERCADO = 5
ID_LOTE = 1
ID_MOVIMENTACAO_ESTORNADA = 42


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


def _lote_confirmado(status_operacional: str, quantidade_disponivel: Decimal, **kwargs) -> LoteORM:
    return _lote(StatusLote.CONFIRMADO, status_operacional, quantidade_disponivel, **kwargs)


def _movimentacao_estornavel(id_mercado: int = ID_MERCADO, id_lote: int = ID_LOTE) -> MovimentacaoEstoqueORM:
    return MovimentacaoEstoqueORM(id=ID_MOVIMENTACAO_ESTORNADA, id_mercado=id_mercado, id_lote=id_lote)


def _mock_db(
    lote_orm: LoteORM | None,
    movimentacao_estornada_orm: MovimentacaoEstoqueORM | None = None,
    ja_estornada: MovimentacaoEstoqueORM | None = None,
) -> MagicMock:
    db = MagicMock()

    def _fake_get(cls, ident, **kwargs):
        if cls is LoteORM:
            return lote_orm
        return movimentacao_estornada_orm

    db.get.side_effect = _fake_get
    db.query.return_value.filter.return_value.first.return_value = ja_estornada

    def _fake_refresh(obj):
        # Simula o banco atribuindo o PK no INSERT real, já que aqui não
        # há nenhuma conexão de fato.
        if getattr(obj, "id", None) is None:
            obj.id = 999

    db.refresh.side_effect = _fake_refresh
    return db


# --- sentido = entrada ---


def test_ajuste_entrada_soma_e_mantem_disponivel():
    lote_orm = _lote_confirmado("disponivel", Decimal("10"))
    db = _mock_db(lote_orm)
    request = AjusteEstoqueRequest(quantidade=Decimal("4"), sentido=SentidoMovimentacao.ENTRADA)

    resultado = registrar_ajuste(db, ID_MERCADO, ID_LOTE, request)

    assert lote_orm.quantidade_disponivel == Decimal("14")
    assert lote_orm.status_operacional == "disponivel"
    assert resultado.quantidade_resultante == Decimal("14")
    db.commit.assert_called_once()


def test_ajuste_entrada_reativa_esgotado_para_disponivel():
    lote_orm = _lote_confirmado("esgotado", Decimal("0"))
    db = _mock_db(lote_orm)
    request = AjusteEstoqueRequest(quantidade=Decimal("4"), sentido=SentidoMovimentacao.ENTRADA)

    registrar_ajuste(db, ID_MERCADO, ID_LOTE, request)

    assert lote_orm.quantidade_disponivel == Decimal("4")
    assert lote_orm.status_operacional == "disponivel"


def test_ajuste_entrada_em_lote_descartado_e_rejeitada():
    lote_orm = _lote_confirmado("descartado", Decimal("0"))
    db = _mock_db(lote_orm)
    request = AjusteEstoqueRequest(quantidade=Decimal("4"), sentido=SentidoMovimentacao.ENTRADA)

    with pytest.raises(LoteDescartadoNaoAceitaEntrada):
        registrar_ajuste(db, ID_MERCADO, ID_LOTE, request)

    assert lote_orm.quantidade_disponivel == Decimal("0")  # inalterado
    db.add.assert_not_called()
    db.commit.assert_not_called()
    db.rollback.assert_called_once()


# --- sentido = saida ---


def test_ajuste_saida_subtrai_mantendo_disponivel():
    lote_orm = _lote_confirmado("disponivel", Decimal("10"))
    db = _mock_db(lote_orm)
    request = AjusteEstoqueRequest(quantidade=Decimal("3"), sentido=SentidoMovimentacao.SAIDA)

    resultado = registrar_ajuste(db, ID_MERCADO, ID_LOTE, request)

    assert lote_orm.quantidade_disponivel == Decimal("7")
    assert lote_orm.status_operacional == "disponivel"
    assert resultado.quantidade_resultante == Decimal("7")


def test_ajuste_saida_zera_saldo_e_muda_para_esgotado_nunca_descartado():
    lote_orm = _lote_confirmado("disponivel", Decimal("5"))
    db = _mock_db(lote_orm)
    request = AjusteEstoqueRequest(quantidade=Decimal("5"), sentido=SentidoMovimentacao.SAIDA)

    registrar_ajuste(db, ID_MERCADO, ID_LOTE, request)

    assert lote_orm.quantidade_disponivel == Decimal("0")
    assert lote_orm.status_operacional == "esgotado"


def test_ajuste_saida_saldo_insuficiente_e_rejeitado_sem_gravar_nada():
    lote_orm = _lote_confirmado("disponivel", Decimal("2"))
    db = _mock_db(lote_orm)
    request = AjusteEstoqueRequest(quantidade=Decimal("9"), sentido=SentidoMovimentacao.SAIDA)

    with pytest.raises(SaldoInsuficienteParaAjuste):
        registrar_ajuste(db, ID_MERCADO, ID_LOTE, request)

    assert lote_orm.quantidade_disponivel == Decimal("2")  # inalterado
    db.add.assert_not_called()
    db.commit.assert_not_called()
    db.rollback.assert_called_once()


def test_ajuste_saida_em_lote_ja_esgotado_e_rejeitado_por_saldo_insuficiente():
    lote_orm = _lote_confirmado("esgotado", Decimal("0"))
    db = _mock_db(lote_orm)
    request = AjusteEstoqueRequest(quantidade=Decimal("1"), sentido=SentidoMovimentacao.SAIDA)

    with pytest.raises(SaldoInsuficienteParaAjuste):
        registrar_ajuste(db, ID_MERCADO, ID_LOTE, request)


def test_ajuste_saida_em_lote_ja_descartado_e_rejeitado_por_saldo_insuficiente():
    lote_orm = _lote_confirmado("descartado", Decimal("0"))
    db = _mock_db(lote_orm)
    request = AjusteEstoqueRequest(quantidade=Decimal("1"), sentido=SentidoMovimentacao.SAIDA)

    with pytest.raises(SaldoInsuficienteParaAjuste):
        registrar_ajuste(db, ID_MERCADO, ID_LOTE, request)


# --- isolamento / status do lote ---


def test_lote_de_outro_mercado_retorna_lote_nao_encontrado():
    lote_orm = _lote_confirmado("disponivel", Decimal("10"))  # id_mercado = ID_MERCADO
    db = _mock_db(lote_orm)
    request = AjusteEstoqueRequest(quantidade=Decimal("3"), sentido=SentidoMovimentacao.ENTRADA)

    with pytest.raises(LoteNaoEncontrado):
        registrar_ajuste(db, ID_MERCADO + 1, ID_LOTE, request)

    assert lote_orm.quantidade_disponivel == Decimal("10")  # inalterado
    db.commit.assert_not_called()
    db.rollback.assert_called_once()


def test_lote_nao_confirmado_retorna_acao_invalida_para_status():
    lote_orm = _lote(StatusLote.PENDENTE_CONFIRMACAO, "disponivel", Decimal("10"))
    db = _mock_db(lote_orm)
    request = AjusteEstoqueRequest(quantidade=Decimal("3"), sentido=SentidoMovimentacao.ENTRADA)

    with pytest.raises(AcaoInvalidaParaStatus):
        registrar_ajuste(db, ID_MERCADO, ID_LOTE, request)

    db.commit.assert_not_called()
    db.rollback.assert_called_once()


def test_quantidade_inicial_nunca_e_alterada():
    lote_orm = _lote_confirmado("disponivel", Decimal("10"))
    db = _mock_db(lote_orm)
    request = AjusteEstoqueRequest(quantidade=Decimal("4"), sentido=SentidoMovimentacao.SAIDA)

    registrar_ajuste(db, ID_MERCADO, ID_LOTE, request)

    assert lote_orm.quantidade_inicial == Decimal("10")


# --- estorno de movimentação (id_movimentacao_estornada) ---


def test_sem_id_movimentacao_estornada_e_modo_correcao_livre():
    lote_orm = _lote_confirmado("disponivel", Decimal("10"))
    db = _mock_db(lote_orm)
    request = AjusteEstoqueRequest(quantidade=Decimal("3"), sentido=SentidoMovimentacao.ENTRADA)

    resultado = registrar_ajuste(db, ID_MERCADO, ID_LOTE, request)

    assert resultado.id_movimentacao_estornada is None


def test_estorno_movimentacao_nao_encontrada_e_rejeitado():
    lote_orm = _lote_confirmado("disponivel", Decimal("10"))
    db = _mock_db(lote_orm, movimentacao_estornada_orm=None)
    request = AjusteEstoqueRequest(
        quantidade=Decimal("3"),
        sentido=SentidoMovimentacao.ENTRADA,
        id_movimentacao_estornada=ID_MOVIMENTACAO_ESTORNADA,
    )

    with pytest.raises(MovimentacaoEstornadaNaoEncontrada):
        registrar_ajuste(db, ID_MERCADO, ID_LOTE, request)

    db.add.assert_not_called()
    db.commit.assert_not_called()
    db.rollback.assert_called_once()


def test_estorno_movimentacao_de_outro_lote_e_rejeitado():
    lote_orm = _lote_confirmado("disponivel", Decimal("10"))
    movimentacao_de_outro_lote = _movimentacao_estornavel(id_lote=ID_LOTE + 1)
    db = _mock_db(lote_orm, movimentacao_estornada_orm=movimentacao_de_outro_lote)
    request = AjusteEstoqueRequest(
        quantidade=Decimal("3"),
        sentido=SentidoMovimentacao.ENTRADA,
        id_movimentacao_estornada=ID_MOVIMENTACAO_ESTORNADA,
    )

    with pytest.raises(MovimentacaoEstornadaNaoEncontrada):
        registrar_ajuste(db, ID_MERCADO, ID_LOTE, request)


def test_estorno_movimentacao_de_outro_mercado_e_rejeitado():
    lote_orm = _lote_confirmado("disponivel", Decimal("10"))
    movimentacao_de_outro_mercado = _movimentacao_estornavel(id_mercado=ID_MERCADO + 1)
    db = _mock_db(lote_orm, movimentacao_estornada_orm=movimentacao_de_outro_mercado)
    request = AjusteEstoqueRequest(
        quantidade=Decimal("3"),
        sentido=SentidoMovimentacao.ENTRADA,
        id_movimentacao_estornada=ID_MOVIMENTACAO_ESTORNADA,
    )

    with pytest.raises(MovimentacaoEstornadaNaoEncontrada):
        registrar_ajuste(db, ID_MERCADO, ID_LOTE, request)


def test_duplo_estorno_e_bloqueado():
    lote_orm = _lote_confirmado("disponivel", Decimal("10"))
    movimentacao_orm = _movimentacao_estornavel()
    ja_estornada = MovimentacaoEstoqueORM(id=100)  # outra linha já referencia a mesma movimentação
    db = _mock_db(lote_orm, movimentacao_estornada_orm=movimentacao_orm, ja_estornada=ja_estornada)
    request = AjusteEstoqueRequest(
        quantidade=Decimal("3"),
        sentido=SentidoMovimentacao.ENTRADA,
        id_movimentacao_estornada=ID_MOVIMENTACAO_ESTORNADA,
    )

    with pytest.raises(MovimentacaoJaEstornada):
        registrar_ajuste(db, ID_MERCADO, ID_LOTE, request)

    assert lote_orm.quantidade_disponivel == Decimal("10")  # inalterado
    db.add.assert_not_called()
    db.commit.assert_not_called()
    db.rollback.assert_called_once()


def test_estorno_valido_grava_id_movimentacao_estornada():
    lote_orm = _lote_confirmado("disponivel", Decimal("10"))
    movimentacao_orm = _movimentacao_estornavel()
    db = _mock_db(lote_orm, movimentacao_estornada_orm=movimentacao_orm, ja_estornada=None)
    request = AjusteEstoqueRequest(
        quantidade=Decimal("2"),
        sentido=SentidoMovimentacao.SAIDA,
        id_movimentacao_estornada=ID_MOVIMENTACAO_ESTORNADA,
    )

    resultado = registrar_ajuste(db, ID_MERCADO, ID_LOTE, request)

    assert resultado.id_movimentacao_estornada == ID_MOVIMENTACAO_ESTORNADA
    assert resultado.sentido == SentidoMovimentacao.SAIDA
    db.commit.assert_called_once()


def test_select_for_update_na_movimentacao_estornada_com_populate_existing():
    lote_orm = _lote_confirmado("disponivel", Decimal("10"))
    movimentacao_orm = _movimentacao_estornavel()
    db = _mock_db(lote_orm, movimentacao_estornada_orm=movimentacao_orm, ja_estornada=None)
    request = AjusteEstoqueRequest(
        quantidade=Decimal("2"),
        sentido=SentidoMovimentacao.SAIDA,
        id_movimentacao_estornada=ID_MOVIMENTACAO_ESTORNADA,
    )

    registrar_ajuste(db, ID_MERCADO, ID_LOTE, request)

    db.get.assert_any_call(
        MovimentacaoEstoqueORM,
        ID_MOVIMENTACAO_ESTORNADA,
        with_for_update=True,
        populate_existing=True,
    )


# --- transação, rollback, conteúdo gravado ---


def test_select_for_update_no_lote_com_populate_existing():
    lote_orm = _lote_confirmado("disponivel", Decimal("10"))
    db = _mock_db(lote_orm)
    request = AjusteEstoqueRequest(quantidade=Decimal("3"), sentido=SentidoMovimentacao.ENTRADA)

    registrar_ajuste(db, ID_MERCADO, ID_LOTE, request)

    db.get.assert_any_call(LoteORM, ID_LOTE, with_for_update=True, populate_existing=True)


def test_rollback_em_falha_no_commit():
    lote_orm = _lote_confirmado("disponivel", Decimal("10"))
    db = _mock_db(lote_orm)
    db.commit.side_effect = RuntimeError("falha simulada de banco")
    request = AjusteEstoqueRequest(quantidade=Decimal("3"), sentido=SentidoMovimentacao.ENTRADA)

    with pytest.raises(RuntimeError, match="falha simulada de banco"):
        registrar_ajuste(db, ID_MERCADO, ID_LOTE, request)

    db.rollback.assert_called_once()


def test_garante_um_unico_commit_apos_registrar_movimentacao_e_historico():
    lote_orm = _lote_confirmado("disponivel", Decimal("10"))
    db = _mock_db(lote_orm)
    request = AjusteEstoqueRequest(quantidade=Decimal("3"), sentido=SentidoMovimentacao.ENTRADA)

    registrar_ajuste(db, ID_MERCADO, ID_LOTE, request)

    assert db.commit.call_count == 1
    assert db.add.call_count == 2  # movimentacoes_estoque + historico_acoes

    nomes_das_chamadas = [chamada[0] for chamada in db.mock_calls]
    indice_commit = nomes_das_chamadas.index("commit")
    indices_add = [i for i, nome in enumerate(nomes_das_chamadas) if nome == "add"]
    assert all(indice_add < indice_commit for indice_add in indices_add)


def test_grava_tipo_acao_ajuste_e_tipo_movimentacao_ajuste():
    lote_orm = _lote_confirmado("disponivel", Decimal("10"))
    db = _mock_db(lote_orm)
    request = AjusteEstoqueRequest(quantidade=Decimal("3"), sentido=SentidoMovimentacao.SAIDA)

    registrar_ajuste(db, ID_MERCADO, ID_LOTE, request)

    objetos_gravados = [chamada.args[0] for chamada in db.add.call_args_list]
    historico_orm = next(o for o in objetos_gravados if type(o).__name__ == "HistoricoAcaoORM")
    movimentacao_orm = next(
        o for o in objetos_gravados if type(o).__name__ == "MovimentacaoEstoqueORM"
    )

    assert historico_orm.tipo_acao == TipoAcao.AJUSTE
    assert movimentacao_orm.tipo_movimentacao == TipoMovimentacao.AJUSTE
    assert movimentacao_orm.sentido == SentidoMovimentacao.SAIDA
    assert historico_orm.quantidade_anterior == Decimal("10")
    assert historico_orm.quantidade_movimentada == Decimal("3")
    assert historico_orm.quantidade_resultante == Decimal("7")
