"""Testes unitários de app.services.movimentacao_service.registrar_retirada
(RN07 — retirada de estoque por vencimento). A Session do SQLAlchemy é
sempre mockada aqui: nenhum teste conecta a nenhum banco, real ou em
memória."""

from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import MagicMock

import pytest

from app.models.lote import LoteORM
from app.schemas.enums import StatusLote, TipoAcao
from app.schemas.movimentacao_estoque import RetiradaEstoqueRequest, TipoMovimentacao
from app.services.lote_service import AcaoInvalidaParaStatus, LoteNaoEncontrado
from app.services.movimentacao_service import (
    LoteNaoVencidoNaoAceitaRetirada,
    SaldoInsuficienteParaRetirada,
    registrar_retirada,
)

ID_MERCADO = 5
ID_LOTE = 1
VENCIDO = date.today() - timedelta(days=1)
VENCE_HOJE = date.today()
NAO_VENCIDO = date.today() + timedelta(days=5)


def _lote(
    status: StatusLote,
    status_operacional: str,
    quantidade_disponivel: Decimal,
    data_validade: date = VENCIDO,
    id_mercado: int = ID_MERCADO,
) -> LoteORM:
    return LoteORM(
        id=ID_LOTE,
        id_mercado=id_mercado,
        status=status,
        status_operacional=status_operacional,
        quantidade_disponivel=quantidade_disponivel,
        quantidade_inicial=quantidade_disponivel,
        data_validade=data_validade,
    )


def _lote_confirmado(status_operacional: str, quantidade_disponivel: Decimal, **kwargs) -> LoteORM:
    return _lote(StatusLote.CONFIRMADO, status_operacional, quantidade_disponivel, **kwargs)


def _mock_db(lote_orm: LoteORM | None) -> MagicMock:
    db = MagicMock()

    def _fake_get(model, ident, **kwargs):
        # db.get também é usado por hoje_do_mercado (RN01) para buscar
        # MercadoORM — só LoteORM devolve o lote configurado; qualquer
        # outro modelo cai no fallback de fuso (America/Sao_Paulo).
        return lote_orm if model is LoteORM else None

    db.get.side_effect = _fake_get

    def _fake_refresh(obj):
        # Simula o banco atribuindo o PK no INSERT real, já que aqui não
        # há nenhuma conexão de fato.
        if getattr(obj, "id", None) is None:
            obj.id = 999

    db.refresh.side_effect = _fake_refresh
    return db


def test_retirada_parcial_mantem_disponivel():
    lote_orm = _lote_confirmado("disponivel", Decimal("10"), data_validade=VENCIDO)
    db = _mock_db(lote_orm)
    request = RetiradaEstoqueRequest(quantidade=Decimal("3"))

    resultado = registrar_retirada(db, ID_MERCADO, ID_LOTE, request)

    assert lote_orm.quantidade_disponivel == Decimal("7")
    assert lote_orm.status_operacional == "disponivel"
    assert resultado.quantidade_anterior == Decimal("10")
    assert resultado.quantidade_resultante == Decimal("7")
    db.commit.assert_called_once()
    db.rollback.assert_not_called()


def test_retirada_total_zera_saldo_e_muda_para_descartado():
    lote_orm = _lote_confirmado("disponivel", Decimal("5"), data_validade=VENCIDO)
    db = _mock_db(lote_orm)
    request = RetiradaEstoqueRequest(quantidade=Decimal("5"))

    registrar_retirada(db, ID_MERCADO, ID_LOTE, request)

    assert lote_orm.quantidade_disponivel == Decimal("0")
    assert lote_orm.status_operacional == "descartado"  # não "esgotado" — exclusivo de venda
    db.commit.assert_called_once()


def test_saldo_insuficiente_e_rejeitado_sem_gravar_nada():
    lote_orm = _lote_confirmado("disponivel", Decimal("2"), data_validade=VENCIDO)
    db = _mock_db(lote_orm)
    request = RetiradaEstoqueRequest(quantidade=Decimal("9"))

    with pytest.raises(SaldoInsuficienteParaRetirada):
        registrar_retirada(db, ID_MERCADO, ID_LOTE, request)

    assert lote_orm.quantidade_disponivel == Decimal("2")  # inalterado
    assert lote_orm.status_operacional == "disponivel"  # inalterado
    db.add.assert_not_called()
    db.commit.assert_not_called()
    db.rollback.assert_called_once()


def test_lote_ja_esgotado_e_rejeitado_por_saldo_insuficiente():
    lote_orm = _lote_confirmado("esgotado", Decimal("0"), data_validade=VENCIDO)
    db = _mock_db(lote_orm)
    request = RetiradaEstoqueRequest(quantidade=Decimal("1"))

    with pytest.raises(SaldoInsuficienteParaRetirada):
        registrar_retirada(db, ID_MERCADO, ID_LOTE, request)

    db.add.assert_not_called()
    db.commit.assert_not_called()
    db.rollback.assert_called_once()


def test_lote_ja_descartado_e_rejeitado_por_saldo_insuficiente():
    lote_orm = _lote_confirmado("descartado", Decimal("0"), data_validade=VENCIDO)
    db = _mock_db(lote_orm)
    request = RetiradaEstoqueRequest(quantidade=Decimal("1"))

    with pytest.raises(SaldoInsuficienteParaRetirada):
        registrar_retirada(db, ID_MERCADO, ID_LOTE, request)

    db.add.assert_not_called()
    db.commit.assert_not_called()
    db.rollback.assert_called_once()


def test_lote_nao_vencido_e_rejeitado():
    lote_orm = _lote_confirmado("disponivel", Decimal("10"), data_validade=NAO_VENCIDO)
    db = _mock_db(lote_orm)
    request = RetiradaEstoqueRequest(quantidade=Decimal("3"))

    with pytest.raises(LoteNaoVencidoNaoAceitaRetirada):
        registrar_retirada(db, ID_MERCADO, ID_LOTE, request)

    assert lote_orm.quantidade_disponivel == Decimal("10")  # inalterado
    db.add.assert_not_called()
    db.commit.assert_not_called()
    db.rollback.assert_called_once()


def test_lote_que_vence_hoje_ainda_nao_e_considerado_vencido():
    # dias_restantes == 0 ("vence hoje") não é < 0 (RN01: vencido é
    # dias_restantes < 0) — ainda não deveria aceitar retirada por
    # vencimento.
    lote_orm = _lote_confirmado("disponivel", Decimal("10"), data_validade=VENCE_HOJE)
    db = _mock_db(lote_orm)
    request = RetiradaEstoqueRequest(quantidade=Decimal("3"))

    with pytest.raises(LoteNaoVencidoNaoAceitaRetirada):
        registrar_retirada(db, ID_MERCADO, ID_LOTE, request)


def test_checagem_de_vencimento_acontece_antes_da_checagem_de_saldo():
    # Lote não vencido E com saldo insuficiente ao mesmo tempo: deve
    # levantar LoteNaoVencidoNaoAceitaRetirada, não SaldoInsuficiente.
    lote_orm = _lote_confirmado("disponivel", Decimal("1"), data_validade=NAO_VENCIDO)
    db = _mock_db(lote_orm)
    request = RetiradaEstoqueRequest(quantidade=Decimal("99"))

    with pytest.raises(LoteNaoVencidoNaoAceitaRetirada):
        registrar_retirada(db, ID_MERCADO, ID_LOTE, request)


def test_lote_de_outro_mercado_retorna_lote_nao_encontrado():
    lote_orm = _lote_confirmado("disponivel", Decimal("10"), data_validade=VENCIDO)
    db = _mock_db(lote_orm)
    request = RetiradaEstoqueRequest(quantidade=Decimal("3"))

    with pytest.raises(LoteNaoEncontrado):
        registrar_retirada(db, ID_MERCADO + 1, ID_LOTE, request)

    assert lote_orm.quantidade_disponivel == Decimal("10")  # inalterado
    db.add.assert_not_called()
    db.commit.assert_not_called()
    db.rollback.assert_called_once()


def test_lote_nao_confirmado_retorna_acao_invalida_para_status():
    lote_orm = _lote(
        StatusLote.PENDENTE_CONFIRMACAO, "disponivel", Decimal("10"), data_validade=VENCIDO
    )
    db = _mock_db(lote_orm)
    request = RetiradaEstoqueRequest(quantidade=Decimal("3"))

    with pytest.raises(AcaoInvalidaParaStatus):
        registrar_retirada(db, ID_MERCADO, ID_LOTE, request)

    db.add.assert_not_called()
    db.commit.assert_not_called()
    db.rollback.assert_called_once()


def test_quantidade_inicial_nunca_e_alterada():
    lote_orm = _lote_confirmado("disponivel", Decimal("10"), data_validade=VENCIDO)
    db = _mock_db(lote_orm)
    request = RetiradaEstoqueRequest(quantidade=Decimal("4"))

    registrar_retirada(db, ID_MERCADO, ID_LOTE, request)

    assert lote_orm.quantidade_inicial == Decimal("10")


def test_rollback_em_falha_no_commit():
    lote_orm = _lote_confirmado("disponivel", Decimal("10"), data_validade=VENCIDO)
    db = _mock_db(lote_orm)
    db.commit.side_effect = RuntimeError("falha simulada de banco")
    request = RetiradaEstoqueRequest(quantidade=Decimal("3"))

    with pytest.raises(RuntimeError, match="falha simulada de banco"):
        registrar_retirada(db, ID_MERCADO, ID_LOTE, request)

    db.rollback.assert_called_once()


def test_garante_um_unico_commit_apos_registrar_movimentacao_e_historico():
    lote_orm = _lote_confirmado("disponivel", Decimal("10"), data_validade=VENCIDO)
    db = _mock_db(lote_orm)
    request = RetiradaEstoqueRequest(quantidade=Decimal("3"))

    registrar_retirada(db, ID_MERCADO, ID_LOTE, request)

    assert db.commit.call_count == 1
    assert db.add.call_count == 2  # movimentacoes_estoque + historico_acoes

    nomes_das_chamadas = [chamada[0] for chamada in db.mock_calls]
    indice_commit = nomes_das_chamadas.index("commit")
    indices_add = [i for i, nome in enumerate(nomes_das_chamadas) if nome == "add"]
    assert all(indice_add < indice_commit for indice_add in indices_add)


def test_select_for_update_com_populate_existing():
    lote_orm = _lote_confirmado("disponivel", Decimal("10"), data_validade=VENCIDO)
    db = _mock_db(lote_orm)
    request = RetiradaEstoqueRequest(quantidade=Decimal("3"))

    registrar_retirada(db, ID_MERCADO, ID_LOTE, request)

    # db.get também é chamado para MercadoORM (hoje_do_mercado, RN01) —
    # aqui importa só que o lote é travado com SELECT ... FOR UPDATE.
    db.get.assert_any_call(LoteORM, ID_LOTE, with_for_update=True, populate_existing=True)


def test_grava_tipo_acao_retirada_vencimento_e_tipo_movimentacao_retirada():
    # tipo_acao (historico_acoes) e tipo_movimentacao (movimentacoes_estoque)
    # usam nomes DIFERENTES para a mesma ação (RN04) — confirma que cada
    # objeto gravado recebeu o valor certo, não trocado por engano.
    lote_orm = _lote_confirmado("disponivel", Decimal("10"), data_validade=VENCIDO)
    db = _mock_db(lote_orm)
    request = RetiradaEstoqueRequest(quantidade=Decimal("3"))

    registrar_retirada(db, ID_MERCADO, ID_LOTE, request)

    objetos_gravados = [chamada.args[0] for chamada in db.add.call_args_list]
    historico_orm = next(o for o in objetos_gravados if type(o).__name__ == "HistoricoAcaoORM")
    movimentacao_orm = next(
        o for o in objetos_gravados if type(o).__name__ == "MovimentacaoEstoqueORM"
    )

    assert historico_orm.tipo_acao == TipoAcao.RETIRADA_VENCIMENTO
    assert movimentacao_orm.tipo_movimentacao == TipoMovimentacao.RETIRADA
    assert historico_orm.quantidade_anterior == Decimal("10")
    assert historico_orm.quantidade_movimentada == Decimal("3")
    assert historico_orm.quantidade_resultante == Decimal("7")
