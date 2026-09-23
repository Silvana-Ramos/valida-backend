"""Testes unitários de app/services/relatorio_acao_diaria_service.py
(Session mockada, sem banco real)."""

from datetime import date, datetime, time, timedelta
from decimal import Decimal
from unittest.mock import MagicMock, patch
from zoneinfo import ZoneInfo

import pytest

from app.models.item_relatorio_diario import ItemRelatorioDiarioORM
from app.models.lote import LoteORM
from app.models.mercado import MercadoORM
from app.models.relatorio_acao_diaria import RelatorioAcaoDiarioORM
from app.schemas.enums import NivelRisco, OrigemCadastro, StatusLote
from app.schemas.mercado import SegmentoMercado, StatusMercado
from app.services import relatorio_acao_diaria_service as service
from app.services.relatorio_acao_diaria_service import (
    ACAO_RECOMENDADA_POR_NIVEL,
    QuantidadeDisponivelInconsistente,
    RelatorioNaoEncontrado,
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


# =============================================================================
# listar_itens
# =============================================================================


def _relatorio(id_relatorio: int = 100, id_mercado: int = ID_MERCADO) -> RelatorioAcaoDiarioORM:
    return RelatorioAcaoDiarioORM(
        id=id_relatorio,
        id_mercado=id_mercado,
        data_referencia=HOJE,
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


def _item(id_item: int, id_relatorio: int) -> ItemRelatorioDiarioORM:
    return ItemRelatorioDiarioORM(
        id=id_item,
        id_relatorio=id_relatorio,
        id_produto=1,
        id_lote=1,
        data_validade=HOJE + timedelta(days=2),
        quantidade_disponivel=Decimal("10"),
        preco_custo=Decimal("2.50"),
        dias_restantes=2,
        classificacao_validade="urgente",
        prioridade="ALTA",
        valor_em_risco=Decimal("25.00"),
        acao_recomendada=ACAO_RECOMENDADA_POR_NIVEL[NivelRisco.URGENTE],
    )


def _db_mock_listar_itens(relatorio_orm, itens=None) -> MagicMock:
    db = MagicMock()
    # Cadeia própria (.filter().first() para o relatório,
    # .filter().order_by().all() para os itens) — distinta da usada por
    # _db_mock (.filter().all()/.filter().first() para lotes/relatório de
    # gerar_ou_obter). listar_itens nunca é chamada junto de
    # gerar_ou_obter no mesmo teste, então não há colisão entre os dois
    # helpers.
    db.query.return_value.filter.return_value.first.return_value = relatorio_orm
    db.query.return_value.filter.return_value.order_by.return_value.all.return_value = itens or []
    return db


def test_listar_itens_relatorio_existente_retorna_seus_itens():
    relatorio_orm = _relatorio(id_relatorio=100)
    itens = [_item(1, id_relatorio=100), _item(2, id_relatorio=100)]
    db = _db_mock_listar_itens(relatorio_orm, itens=itens)

    resultado = service.listar_itens(db, ID_MERCADO, 100)

    assert len(resultado) == 2
    assert {item.id for item in resultado} == {1, 2}


def test_listar_itens_relatorio_sem_itens_retorna_lista_vazia():
    relatorio_orm = _relatorio(id_relatorio=100)
    db = _db_mock_listar_itens(relatorio_orm, itens=[])

    resultado = service.listar_itens(db, ID_MERCADO, 100)

    assert resultado == []


def test_listar_itens_relatorio_inexistente_levanta_relatorio_nao_encontrado():
    db = _db_mock_listar_itens(relatorio_orm=None)

    with pytest.raises(RelatorioNaoEncontrado):
        service.listar_itens(db, ID_MERCADO, 999)


def test_listar_itens_relatorio_de_outro_mercado_levanta_mesma_excecao():
    # A query real (id == id_relatorio AND id_mercado == id_mercado) não
    # encontraria nenhuma linha para um relatório de outro mercado —
    # simulamos exatamente esse resultado (None), igual ao teste de
    # relatório inexistente. É esperado que os dois testes sejam
    # mecanicamente idênticos: isso comprova que o service não consegue
    # (nem deve) diferenciar os dois casos.
    db = _db_mock_listar_itens(relatorio_orm=None)

    with pytest.raises(RelatorioNaoEncontrado):
        service.listar_itens(db, ID_MERCADO, 100)


def test_query_de_itens_filtra_pelo_id_relatorio_validado():
    relatorio_orm = _relatorio(id_relatorio=100)
    db = _db_mock_listar_itens(relatorio_orm, itens=[])

    service.listar_itens(db, ID_MERCADO, 100)

    clausulas = db.query.return_value.filter.call_args.args
    filtro_esperado = ItemRelatorioDiarioORM.id_relatorio == 100
    assert any(c.compare(filtro_esperado) for c in clausulas)


def test_query_de_relatorio_filtra_por_id_relatorio_e_id_mercado_simultaneamente():
    relatorio_orm = _relatorio(id_relatorio=100)
    db = _db_mock_listar_itens(relatorio_orm, itens=[])

    service.listar_itens(db, ID_MERCADO, 100)

    # A primeira chamada de .filter(...) no nó compartilhado corresponde à
    # query do relatório (a segunda, capturada por .call_args, é a dos
    # itens) — call_args_list preserva a ordem real das chamadas.
    clausulas_relatorio = db.query.return_value.filter.call_args_list[0].args
    filtro_id = RelatorioAcaoDiarioORM.id == 100
    filtro_mercado = RelatorioAcaoDiarioORM.id_mercado == ID_MERCADO
    assert any(c.compare(filtro_id) for c in clausulas_relatorio)
    assert any(c.compare(filtro_mercado) for c in clausulas_relatorio)


def test_listar_itens_nao_chama_gerar_ou_obter():
    relatorio_orm = _relatorio(id_relatorio=100)
    db = _db_mock_listar_itens(relatorio_orm, itens=[])

    with patch("app.services.relatorio_acao_diaria_service.gerar_ou_obter") as gerar_mock:
        service.listar_itens(db, ID_MERCADO, 100)

    gerar_mock.assert_not_called()


def test_listar_itens_nao_grava_nada():
    relatorio_orm = _relatorio(id_relatorio=100)
    itens = [_item(1, id_relatorio=100)]
    db = _db_mock_listar_itens(relatorio_orm, itens=itens)

    service.listar_itens(db, ID_MERCADO, 100)

    db.add.assert_not_called()
    db.commit.assert_not_called()
    db.flush.assert_not_called()


def test_listar_itens_nao_reexecuta_calculo_de_risco():
    relatorio_orm = _relatorio(id_relatorio=100)
    item_persistido = _item(1, id_relatorio=100)
    db = _db_mock_listar_itens(relatorio_orm, itens=[item_persistido])

    with patch("app.services.relatorio_acao_diaria_service.calcular_risco") as calcular_mock:
        resultado = service.listar_itens(db, ID_MERCADO, 100)

    calcular_mock.assert_not_called()
    assert resultado[0].dias_restantes == item_persistido.dias_restantes
    assert resultado[0].classificacao_validade == item_persistido.classificacao_validade


# =============================================================================
# gerar_para_mercados_ativos
# =============================================================================


def _mercado(
    id_mercado: int,
    ativo: bool = True,
    horario_relatorio_diario: time | None = None,
    timezone: str | None = None,
) -> MercadoORM:
    return MercadoORM(
        id=id_mercado,
        nome="Mercado Teste",
        telefone_whatsapp=f"+5511999900{id_mercado:03d}",
        segmento=SegmentoMercado.OUTRO,
        status=StatusMercado.ATIVO,
        data_cadastro=datetime.now(),
        timezone=timezone,
        horario_abertura=None,
        horario_relatorio_diario=horario_relatorio_diario,
        relatorio_diario_ativo=ativo,
        limite_valor_atencao=None,
        limite_quantidade_atencao=None,
    )


def _db_mock_gerar_para_mercados_ativos(mercados: list[MercadoORM]) -> MagicMock:
    db = MagicMock()
    db.query.return_value.filter.return_value.all.return_value = mercados
    por_id = {m.id: m for m in mercados}
    db.get.side_effect = lambda model, ident, **kwargs: (
        por_id.get(ident) if model is MercadoORM else None
    )
    return db


def test_gerar_para_mercados_ativos_sem_mercado_ativo_retorna_resumo_zerado():
    db = _db_mock_gerar_para_mercados_ativos([])

    resumo = service.gerar_para_mercados_ativos(db)

    assert resumo.total_mercados_ativos == 0
    assert resumo.total_processados == 0
    assert resumo.total_aguardando_horario == 0
    assert resumo.mercados_sem_horario_configurado == []
    assert resumo.erros == []


def test_gerar_para_mercados_ativos_ignora_mercado_sem_horario_configurado():
    mercado = _mercado(1, horario_relatorio_diario=None)
    db = _db_mock_gerar_para_mercados_ativos([mercado])

    with patch("app.services.relatorio_acao_diaria_service.gerar_ou_obter") as mock_gerar:
        resumo = service.gerar_para_mercados_ativos(db)

    mock_gerar.assert_not_called()
    assert resumo.mercados_sem_horario_configurado == [1]
    assert resumo.total_processados == 0


def test_gerar_para_mercados_ativos_nao_gera_quando_horario_ainda_nao_chegou():
    # 23:59 no fuso do mercado dificilmente já passou no momento em que o
    # teste roda (mesma tolerância a fragilidade de horário já aceita em
    # outros testes deste arquivo, ex. HOJE).
    mercado = _mercado(1, horario_relatorio_diario=time(23, 59))
    db = _db_mock_gerar_para_mercados_ativos([mercado])

    with patch("app.services.relatorio_acao_diaria_service.gerar_ou_obter") as mock_gerar:
        resumo = service.gerar_para_mercados_ativos(db)

    mock_gerar.assert_not_called()
    assert resumo.total_aguardando_horario == 1
    assert resumo.total_processados == 0


def test_gerar_para_mercados_ativos_gera_quando_horario_ja_passou():
    mercado = _mercado(1, horario_relatorio_diario=time(0, 0))
    db = _db_mock_gerar_para_mercados_ativos([mercado])

    with patch("app.services.relatorio_acao_diaria_service.gerar_ou_obter") as mock_gerar:
        resumo = service.gerar_para_mercados_ativos(db)

    mock_gerar.assert_called_once_with(db, 1)
    assert resumo.total_processados == 1
    assert resumo.total_aguardando_horario == 0


def test_gerar_para_mercados_ativos_erro_em_um_mercado_nao_impede_os_demais():
    mercado_ok = _mercado(1, horario_relatorio_diario=time(0, 0))
    mercado_com_erro = _mercado(2, horario_relatorio_diario=time(0, 0))
    db = _db_mock_gerar_para_mercados_ativos([mercado_ok, mercado_com_erro])

    def _gerar_side_effect(db_arg, id_mercado):
        if id_mercado == 2:
            raise RuntimeError("falha simulada")
        return None

    with patch(
        "app.services.relatorio_acao_diaria_service.gerar_ou_obter",
        side_effect=_gerar_side_effect,
    ):
        resumo = service.gerar_para_mercados_ativos(db)

    assert resumo.total_processados == 1
    assert len(resumo.erros) == 1
    assert "mercado 2" in resumo.erros[0]
    db.rollback.assert_called_once()


def test_gerar_para_mercados_ativos_query_filtra_por_relatorio_diario_ativo():
    db = _db_mock_gerar_para_mercados_ativos([])

    service.gerar_para_mercados_ativos(db)

    clausulas = db.query.return_value.filter.call_args.args
    filtro_esperado = MercadoORM.relatorio_diario_ativo.is_(True)
    assert any(c.compare(filtro_esperado) for c in clausulas)


def test_gerar_para_mercados_ativos_nao_duplica_regra_de_geracao():
    mercado = _mercado(1, horario_relatorio_diario=time(0, 0))
    db = _db_mock_gerar_para_mercados_ativos([mercado])

    with patch(
        "app.services.relatorio_acao_diaria_service.gerar_ou_obter", return_value=None
    ) as mock_gerar:
        service.gerar_para_mercados_ativos(db)

    mock_gerar.assert_called_once_with(db, 1)
    # Toda escrita real fica dentro de gerar_ou_obter (patchada aqui) — esta
    # função nunca deve tocar db.add/db.commit diretamente.
    db.add.assert_not_called()
    db.commit.assert_not_called()
