"""Testes unitários de app/services/recalculo_risco_service.py (Session
mockada, sem banco real)."""

from datetime import date, datetime, timedelta
from decimal import Decimal
from unittest.mock import MagicMock

from app.models.historico_acao import HistoricoAcaoORM
from app.models.lote import LoteORM
from app.schemas.enums import NivelRisco, OrigemCadastro, StatusLote, TipoAcao
from app.schemas.historico_acao import OrigemAcao
from app.services import recalculo_risco_service

ID_MERCADO = 5


def _lote_confirmado(
    id_lote: int,
    data_validade: date,
    nivel_risco: NivelRisco,
    dias_restantes: int = 999,
) -> LoteORM:
    return LoteORM(
        id=id_lote,
        id_mercado=ID_MERCADO,
        id_produto=1,
        quantidade=Decimal("10"),
        numero_lote=None,
        data_validade=data_validade,
        data_entrada=datetime.now(),
        origem_cadastro=OrigemCadastro.TEXTO,
        status=StatusLote.CONFIRMADO,
        nivel_risco=nivel_risco,
        dias_restantes=dias_restantes,
        data_ultima_atualizacao=datetime.now() - timedelta(days=1),
        criado_por=None,
        preco_custo=None,
        status_operacional="disponivel",
        quantidade_disponivel=Decimal("10"),
        quantidade_inicial=Decimal("10"),
    )


def _db_mock(lotes: list[LoteORM]) -> MagicMock:
    db = MagicMock()
    db.query.return_value.filter.return_value.all.return_value = [(l.id,) for l in lotes]

    por_id = {l.id: l for l in lotes}

    def get_side_effect(model, ident, **kwargs):
        return por_id.get(ident)

    db.get.side_effect = get_side_effect
    return db


# --- sem mudança de faixa ---------------------------------------------------


def test_sem_mudanca_de_faixa_nao_gera_historico():
    # Validade a 20 dias -> NORMAL; lote já está marcado NORMAL.
    lote = _lote_confirmado(1, date.today() + timedelta(days=20), NivelRisco.NORMAL)
    db = _db_mock([lote])

    resumo = recalculo_risco_service.recalcular_todos(db)

    assert resumo.total_processados == 1
    assert resumo.total_mudaram_faixa == 0
    assert lote.nivel_risco == NivelRisco.NORMAL
    assert lote.dias_restantes == 20
    assert not any(
        isinstance(chamada.args[0], HistoricoAcaoORM) for chamada in db.add.call_args_list
    )


# --- com mudança de faixa --------------------------------------------------


def test_com_mudanca_de_faixa_atualiza_e_gera_historico():
    # Validade a 5 dias -> RISCO; lote ainda marcado ATENCAO (defasado).
    lote = _lote_confirmado(1, date.today() + timedelta(days=5), NivelRisco.ATENCAO)
    db = _db_mock([lote])

    resumo = recalculo_risco_service.recalcular_todos(db)

    assert resumo.total_processados == 1
    assert resumo.total_mudaram_faixa == 1
    assert lote.nivel_risco == NivelRisco.RISCO
    assert lote.dias_restantes == 5

    historicos = [
        chamada.args[0]
        for chamada in db.add.call_args_list
        if isinstance(chamada.args[0], HistoricoAcaoORM)
    ]
    assert len(historicos) == 1
    assert historicos[0].tipo_acao == TipoAcao.STATUS_ALTERADO
    assert historicos[0].origem == OrigemAcao.SISTEMA
    assert historicos[0].id_lote == 1
    assert historicos[0].id_mercado == ID_MERCADO


# --- múltiplos lotes / isolamento de erro -----------------------------


def test_multiplos_lotes_processados_independentemente():
    lote_sem_mudanca = _lote_confirmado(1, date.today() + timedelta(days=20), NivelRisco.NORMAL)
    lote_com_mudanca = _lote_confirmado(2, date.today() + timedelta(days=1), NivelRisco.RISCO)
    db = _db_mock([lote_sem_mudanca, lote_com_mudanca])

    resumo = recalculo_risco_service.recalcular_todos(db)

    assert resumo.total_processados == 2
    assert resumo.total_mudaram_faixa == 1
    assert lote_com_mudanca.nivel_risco == NivelRisco.URGENTE


def test_erro_em_um_lote_nao_impede_os_demais():
    lote_ok = _lote_confirmado(1, date.today() + timedelta(days=20), NivelRisco.NORMAL)
    lote_com_erro = _lote_confirmado(2, date.today() + timedelta(days=5), NivelRisco.ATENCAO)
    db = _db_mock([lote_ok, lote_com_erro])

    chamadas = {"n": 0}

    def commit_side_effect():
        chamadas["n"] += 1
        # A primeira chamada de commit corresponde ao primeiro lote
        # processado (id=1, sem erro); a segunda (id=2) falha.
        if chamadas["n"] == 2:
            raise RuntimeError("falha simulada de banco")

    db.commit.side_effect = commit_side_effect

    resumo = recalculo_risco_service.recalcular_todos(db)

    assert resumo.total_processados == 1
    assert len(resumo.erros) == 1
    assert "lote 2" in resumo.erros[0]
    db.rollback.assert_called_once()


def test_nenhum_lote_confirmado_retorna_resumo_zerado():
    db = _db_mock([])

    resumo = recalculo_risco_service.recalcular_todos(db)

    assert resumo.total_processados == 0
    assert resumo.total_mudaram_faixa == 0
    assert resumo.erros == []


# --- idempotência -----------------------------------------------------


def test_rodar_duas_vezes_no_mesmo_dia_nao_duplica_historico():
    lote = _lote_confirmado(1, date.today() + timedelta(days=5), NivelRisco.ATENCAO)
    db = _db_mock([lote])

    resumo1 = recalculo_risco_service.recalcular_todos(db)
    db.add.reset_mock()
    resumo2 = recalculo_risco_service.recalcular_todos(db)

    assert resumo1.total_mudaram_faixa == 1
    assert resumo2.total_mudaram_faixa == 0
    assert not any(
        isinstance(chamada.args[0], HistoricoAcaoORM) for chamada in db.add.call_args_list
    )
