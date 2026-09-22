"""Testes unitários de app/services/relatorio_acao_diaria_service.py
(Session mockada, sem banco real)."""

from datetime import date, datetime, timedelta
from decimal import Decimal
from unittest.mock import MagicMock, patch
from zoneinfo import ZoneInfo

import pytest

from app.models.item_relatorio_diario import ItemRelatorioDiarioORM
from app.models.lote import LoteORM
from app.models.relatorio_acao_diaria import RelatorioAcaoDiarioORM
from app.schemas.enums import NivelRisco, OrigemCadastro, StatusLote
from app.services import relatorio_acao_diaria_service as service
from app.services.relatorio_acao_diaria_service import (
    ACAO_RECOMENDADA_POR_NIVEL,
    QuantidadeDisponivelInconsistente,
)

ID_MERCADO = 5
# Mesmo fallback que hoje_do_mercado usa quando db.get(MercadoORM, ...)
# devolve None (ver _db_mock) — evita depender de date.today() coincidir
# com o fuso de fallback perto da virada do dia.
HOJE = datetime.now(ZoneInfo("America/Sao_Paulo")).date()


def _lote(
    id_lote: int,
    dias_restantes: int,
    id_mercado: int = ID_MERCADO,
    status: StatusLote = StatusLote.CONFIRMADO,
    status_operacional: str = "disponivel",
    quantidade_disponivel: Decimal | None = Decimal("10"),
    preco_custo: Decimal | None = Decimal("2.50"),
    id_produto: int = 1,
) -> LoteORM:
    return LoteORM(
        id=id_lote,
        id_mercado=id_mercado,
        id_produto=id_produto,
        quantidade=quantidade_disponivel or Decimal("0"),
        numero_lote=None,
        data_validade=HOJE + timedelta(days=dias_restantes),
        data_entrada=datetime.now(),
        origem_cadastro=OrigemCadastro.TEXTO,
        status=status,
        nivel_risco=NivelRisco.NORMAL,  # placeholder — recalculado por calcular_risco no service
        dias_restantes=dias_restantes,
        data_ultima_atualizacao=datetime.now(),
        criado_por=None,
        preco_custo=preco_custo,
        status_operacional=status_operacional,
        quantidade_disponivel=quantidade_disponivel,
        quantidade_inicial=quantidade_disponivel,
    )


def _itens_adicionados(db: MagicMock) -> list[ItemRelatorioDiarioORM]:
    return [c.args[0] for c in db.add.call_args_list if isinstance(c.args[0], ItemRelatorioDiarioORM)]


def _db_mock(
    lotes: list[LoteORM], relatorio_existente: RelatorioAcaoDiarioORM | None = None
) -> MagicMock:
    db = MagicMock()

    # db.get só é usado internamente por hoje_do_mercado (RN01) — sem
    # mercado configurado, cai no fallback America/Sao_Paulo (mesmo padrão
    # de test_lote_service.py).
    db.get.side_effect = lambda model, ident, **kwargs: None

    # gerar_ou_obter faz dois db.query(...) distintos: um .first() (checa
    # relatório existente) e um .all() (lotes do mercado) — mesmo objeto
    # mockado encadeado, métodos finais diferentes.
    db.query.return_value.filter.return_value.first.return_value = relatorio_existente
    db.query.return_value.filter.return_value.all.return_value = lotes

    def _fake_flush():
        # Simula o banco atribuindo o PK no INSERT real do relatório, para
        # permitir vincular id_relatorio aos itens antes do commit.
        for chamada in db.add.call_args_list:
            obj = chamada.args[0]
            if isinstance(obj, RelatorioAcaoDiarioORM) and obj.id is None:
                obj.id = 999

    def _fake_refresh(obj):
        if getattr(obj, "id", None) is None:
            obj.id = 999
        if isinstance(obj, RelatorioAcaoDiarioORM) and obj.gerado_em is None:
            obj.gerado_em = datetime.now()

    db.flush.side_effect = _fake_flush
    db.refresh.side_effect = _fake_refresh
    return db


# --- geração normal ---------------------------------------------------------


def test_geracao_normal_inclui_lotes_acionaveis():
    lote_urgente = _lote(1, dias_restantes=2)
    lote_normal = _lote(2, dias_restantes=30)  # fora da faixa de risco (RN01)
    db = _db_mock([lote_urgente, lote_normal])

    relatorio = service.gerar_ou_obter(db, ID_MERCADO)

    assert relatorio.id_mercado == ID_MERCADO
    assert relatorio.data_referencia == HOJE
    assert relatorio.status == "gerado"

    itens = _itens_adicionados(db)
    assert len(itens) == 1
    assert itens[0].id_lote == 1
    db.commit.assert_called_once()


# --- idempotência -----------------------------------------------------------


def test_idempotente_retorna_relatorio_existente_sem_regenerar():
    relatorio_existente = RelatorioAcaoDiarioORM(
        id=42,
        id_mercado=ID_MERCADO,
        data_referencia=HOJE,
        gerado_em=datetime.now(),
        status="gerado",
        qtd_vencidos=1,
        qtd_vence_hoje=0,
        qtd_urgentes=0,
        qtd_risco=0,
        qtd_atencao=0,
        valor_em_risco=Decimal("10"),
        total_acoes_recomendadas=0,
        total_acoes_realizadas=0,
    )
    lote_urgente = _lote(1, dias_restantes=2)
    db = _db_mock([lote_urgente], relatorio_existente=relatorio_existente)

    relatorio = service.gerar_ou_obter(db, ID_MERCADO)

    assert relatorio.id == 42
    assert relatorio.qtd_vencidos == 1  # veio do relatório existente, não recalculado
    db.add.assert_not_called()
    db.commit.assert_not_called()
    db.flush.assert_not_called()
    db.query.return_value.filter.return_value.all.assert_not_called()  # lotes nunca são consultados


# --- isolamento por mercado (RN05) ------------------------------------------


def test_query_de_lotes_filtra_por_mercado_e_status_confirmado():
    db = _db_mock([])

    service.gerar_ou_obter(db, ID_MERCADO)

    clausulas = db.query.return_value.filter.call_args.args
    filtro_mercado = LoteORM.id_mercado == ID_MERCADO
    filtro_status = LoteORM.status == StatusLote.CONFIRMADO
    assert any(c.compare(filtro_mercado) for c in clausulas)
    assert any(c.compare(filtro_status) for c in clausulas)


def test_isolamento_usa_id_mercado_recebido_nao_um_valor_fixo():
    db = _db_mock([])
    outro_mercado = 99

    service.gerar_ou_obter(db, outro_mercado)

    clausulas = db.query.return_value.filter.call_args.args
    filtro_esperado = LoteORM.id_mercado == outro_mercado
    assert any(c.compare(filtro_esperado) for c in clausulas)


# --- níveis, prioridades e ação recomendada (mapeamento aprovado) ----------


@pytest.mark.parametrize(
    "dias_restantes,nivel_esperado,prioridade_esperada",
    [
        (-1, "vencido", "CRITICA"),
        (2, "urgente", "ALTA"),
        (5, "risco", "MEDIA"),
        (10, "atencao", "BAIXA"),
    ],
)
def test_classificacao_prioridade_e_acao_recomendada_por_nivel(
    dias_restantes, nivel_esperado, prioridade_esperada
):
    lote = _lote(1, dias_restantes=dias_restantes)
    db = _db_mock([lote])

    service.gerar_ou_obter(db, ID_MERCADO)

    item = _itens_adicionados(db)[0]
    assert item.classificacao_validade == nivel_esperado
    assert item.prioridade == prioridade_esperada
    assert item.acao_recomendada == ACAO_RECOMENDADA_POR_NIVEL[NivelRisco(nivel_esperado)]


def test_textos_de_acao_recomendada_sao_exatamente_os_quatro_aprovados():
    assert ACAO_RECOMENDADA_POR_NIVEL[NivelRisco.VENCIDO] == (
        "Retirar do estoque imediatamente e registrar a retirada por "
        "vencimento. Não vender."
    )
    assert ACAO_RECOMENDADA_POR_NIVEL[NivelRisco.URGENTE] == (
        "Priorizar venda seguindo FEFO e avaliar desconto, combo ou destaque."
    )
    assert ACAO_RECOMENDADA_POR_NIVEL[NivelRisco.RISCO] == (
        "Reforçar exposição, acompanhar o giro e considerar ação promocional."
    )
    assert ACAO_RECOMENDADA_POR_NIVEL[NivelRisco.ATENCAO] == (
        "Acompanhar o lote e manter a organização FEFO."
    )


# --- qtd_vence_hoje ----------------------------------------------------------


def test_qtd_vence_hoje_conta_somente_dias_restantes_zero():
    lote_hoje = _lote(1, dias_restantes=0)
    lote_urgente_nao_hoje = _lote(2, dias_restantes=2)
    db = _db_mock([lote_hoje, lote_urgente_nao_hoje])

    relatorio = service.gerar_ou_obter(db, ID_MERCADO)

    assert relatorio.qtd_vence_hoje == 1
    assert relatorio.qtd_urgentes == 2  # os dois estão na faixa urgente (0-3 dias) — subconjunto, não exclusivo


# --- valor_em_risco -----------------------------------------------------------


def test_valor_em_risco_multiplica_preco_custo_por_quantidade_disponivel():
    lote = _lote(
        1, dias_restantes=2, preco_custo=Decimal("3.50"), quantidade_disponivel=Decimal("4")
    )
    db = _db_mock([lote])

    relatorio = service.gerar_ou_obter(db, ID_MERCADO)

    item = _itens_adicionados(db)[0]
    assert item.valor_em_risco == Decimal("14.00")
    assert relatorio.valor_em_risco == Decimal("14.00")


def test_valor_em_risco_e_none_quando_preco_custo_e_none():
    lote = _lote(1, dias_restantes=2, preco_custo=None, quantidade_disponivel=Decimal("4"))
    db = _db_mock([lote])

    relatorio = service.gerar_ou_obter(db, ID_MERCADO)

    item = _itens_adicionados(db)[0]
    assert item.valor_em_risco is None
    assert relatorio.valor_em_risco == Decimal("0")  # item sem preco_custo não entra na soma


# --- quantidade_disponivel None: inconsistência explícita, sem fallback ----


def test_quantidade_disponivel_none_levanta_inconsistencia_e_nao_grava_nada():
    lote = _lote(1, dias_restantes=2, quantidade_disponivel=None)
    db = _db_mock([lote])

    with pytest.raises(QuantidadeDisponivelInconsistente):
        service.gerar_ou_obter(db, ID_MERCADO)

    db.add.assert_not_called()
    db.commit.assert_not_called()
    db.rollback.assert_called_once()


def test_quantidade_disponivel_none_nao_usa_quantidade_legada_como_fallback():
    lote = _lote(1, dias_restantes=2, quantidade_disponivel=None)
    lote.quantidade = Decimal("999")  # se houvesse fallback, apareceria no item — não deve

    db = _db_mock([lote])

    with pytest.raises(QuantidadeDisponivelInconsistente):
        service.gerar_ou_obter(db, ID_MERCADO)

    db.add.assert_not_called()


# --- totais do relatório -----------------------------------------------------


def test_totais_do_relatorio():
    lotes = [
        _lote(1, dias_restantes=-1),  # vencido
        _lote(2, dias_restantes=0),  # urgente + vence hoje
        _lote(3, dias_restantes=2),  # urgente
        _lote(4, dias_restantes=5),  # risco
        _lote(5, dias_restantes=10),  # atencao
        _lote(6, dias_restantes=30),  # normal — fora do relatório
    ]
    db = _db_mock(lotes)

    relatorio = service.gerar_ou_obter(db, ID_MERCADO)

    assert relatorio.qtd_vencidos == 1
    assert relatorio.qtd_vence_hoje == 1
    assert relatorio.qtd_urgentes == 2
    assert relatorio.qtd_risco == 1
    assert relatorio.qtd_atencao == 1
    assert relatorio.valor_em_risco == Decimal("125.00")  # 5 itens acionáveis x (2.50 * 10)
    assert relatorio.total_acoes_recomendadas == 0
    assert relatorio.total_acoes_realizadas == 0


# --- reaproveitamento de calcular_risco (sem duplicar thresholds) ----------


def test_reutiliza_calcular_risco_em_vez_de_duplicar_thresholds():
    lote = _lote(1, dias_restantes=2)
    db = _db_mock([lote])

    with patch(
        "app.services.relatorio_acao_diaria_service.calcular_risco",
        wraps=service.calcular_risco,
    ) as calcular_risco_mock:
        service.gerar_ou_obter(db, ID_MERCADO)

    calcular_risco_mock.assert_called_once()
    args, kwargs = calcular_risco_mock.call_args
    assert args[0] == lote.data_validade
    assert "hoje" in kwargs


# --- transação: commit único no sucesso, rollback no erro ------------------


def test_um_unico_commit_no_caminho_de_sucesso():
    lote = _lote(1, dias_restantes=2)
    db = _db_mock([lote])

    service.gerar_ou_obter(db, ID_MERCADO)

    assert db.commit.call_count == 1
    db.rollback.assert_not_called()


def test_rollback_quando_commit_falha():
    lote = _lote(1, dias_restantes=2)
    db = _db_mock([lote])
    db.commit.side_effect = RuntimeError("falha simulada de banco")

    with pytest.raises(RuntimeError, match="falha simulada de banco"):
        service.gerar_ou_obter(db, ID_MERCADO)

    db.rollback.assert_called_once()


# --- lotes não acionáveis ficam fora do relatório (RN06, decisão da Gestão Preventiva) --


def test_lote_nivel_normal_fica_fora_do_relatorio():
    lote_normal = _lote(1, dias_restantes=30)
    db = _db_mock([lote_normal])

    relatorio = service.gerar_ou_obter(db, ID_MERCADO)

    assert (
        relatorio.qtd_vencidos
        == relatorio.qtd_urgentes
        == relatorio.qtd_risco
        == relatorio.qtd_atencao
        == 0
    )
    assert _itens_adicionados(db) == []


@pytest.mark.parametrize("status_operacional", ["esgotado", "descartado"])
def test_lote_acionavel_mas_sem_estoque_fica_fora_do_relatorio(status_operacional):
    lote = _lote(
        1,
        dias_restantes=2,
        status_operacional=status_operacional,
        quantidade_disponivel=Decimal("0"),
    )
    db = _db_mock([lote])

    relatorio = service.gerar_ou_obter(db, ID_MERCADO)

    assert relatorio.qtd_urgentes == 0
    assert _itens_adicionados(db) == []
