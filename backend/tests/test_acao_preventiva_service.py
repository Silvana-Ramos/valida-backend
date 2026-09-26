"""Testes unitários de app/services/acao_preventiva_service.py (Session
mockada, sem banco real).

Em vez de encadear MagicMock (`db.query.return_value.join.return_value...`),
uso FakeQuery: um objeto simples que representa UMA consulta específica do
service, guarda os argumentos de .join()/.filter() para inspeção e devolve
um resultado fixo no método terminal — desacoplado da profundidade exata
do encadeamento real."""

from datetime import date, datetime, timedelta
from decimal import Decimal
from unittest.mock import MagicMock

import pytest

from app.models.acao_preventiva import AcaoPreventivaORM
from app.models.item_relatorio_diario import ItemRelatorioDiarioORM
from app.models.relatorio_acao_diaria import RelatorioAcaoDiarioORM
from app.models.usuario import UsuarioORM
from app.schemas.acao_preventiva import AcaoPreventivaCreateRequest, AcaoPreventivaEditRequest
from app.schemas.usuario import PapelUsuario
from app.services import acao_preventiva_service as service
from app.services.usuario_service import UsuarioNaoEncontrado

ID_MERCADO = 5
ID_RELATORIO = 100


# --- factories de dados reais (não mocks) -----------------------------------


def _item(
    id_item: int = 1, id_relatorio: int = ID_RELATORIO, acao_recomendada: str = "Recomendação padrão do item"
) -> ItemRelatorioDiarioORM:
    return ItemRelatorioDiarioORM(
        id=id_item,
        id_relatorio=id_relatorio,
        id_produto=1,
        id_lote=1,
        data_validade=date.today(),
        quantidade_disponivel=Decimal("10"),
        preco_custo=Decimal("2.00"),
        dias_restantes=2,
        classificacao_validade="urgente",
        prioridade="ALTA",
        valor_em_risco=Decimal("20.00"),
        acao_recomendada=acao_recomendada,
    )


def _acao(id_acao: int = 1, id_item_relatorio: int = 1, status: str = "recomendada", **overrides) -> AcaoPreventivaORM:
    dados = dict(
        id=id_acao,
        id_item_relatorio=id_item_relatorio,
        id_usuario_responsavel=None,
        acao_recomendada="Recomendação padrão do item",
        acao_realizada=None,
        status=status,
        data_inicio=None,
        data_fim=None,
        resultado_operacional=None,
        observacao=None,
        criada_em=datetime.now(),
        atualizada_em=datetime.now(),
    )
    dados.update(overrides)
    return AcaoPreventivaORM(**dados)


def _relatorio(
    id_relatorio: int = ID_RELATORIO, id_mercado: int = ID_MERCADO, total_acoes_realizadas: int = 0
) -> RelatorioAcaoDiarioORM:
    return RelatorioAcaoDiarioORM(
        id=id_relatorio,
        id_mercado=id_mercado,
        data_referencia=date.today(),
        gerado_em=datetime.now(),
        status="gerado",
        qtd_vencidos=0,
        qtd_vence_hoje=0,
        qtd_urgentes=0,
        qtd_risco=0,
        qtd_atencao=0,
        valor_em_risco=Decimal("0"),
        total_acoes_recomendadas=0,
        total_acoes_realizadas=total_acoes_realizadas,
    )


def _usuario(id_usuario: int = 7, id_mercado: int = ID_MERCADO) -> UsuarioORM:
    return UsuarioORM(
        id=id_usuario,
        id_mercado=id_mercado,
        telefone_whatsapp="+5511999999999",
        nome="Fulano de Tal",
        papel=PapelUsuario.FUNCIONARIO,
    )


# --- FakeQuery: substitui cadeias profundas de MagicMock --------------------


class FakeQuery:
    """Representa UMA consulta específica do service (A, B, C ou D).
    Devolve um resultado fixo no método terminal e guarda os argumentos de
    .join(...)/.filter(...) para inspeção estrutural, sem depender da
    profundidade exata do encadeamento real."""

    def __init__(self, resultado=None, db_para_verificar_flush=None):
        self.resultado = resultado
        self.join_args: list[tuple] = []
        self.filter_args: list[tuple] = []
        self.travada_com_for_update = False
        self._db = db_para_verificar_flush
        self.flush_ja_ocorreu_no_count = None

    def join(self, *args, **kwargs):
        self.join_args.append(args)
        return self

    def filter(self, *args, **kwargs):
        self.filter_args.append(args)
        return self

    def with_for_update(self, *args, **kwargs):
        self.travada_com_for_update = True
        return self

    def first(self):
        return self.resultado

    def count(self):
        if self._db is not None:
            self.flush_ja_ocorreu_no_count = self._db.flush.called
        return self.resultado


def _query_dispatcher(mapa: dict):
    """mapa associa cada Model a UMA FakeQuery, ou a uma LISTA quando o
    MESMO Model é consultado mais de uma vez na mesma chamada (ex.:
    atualizar() consulta AcaoPreventivaORM duas vezes: localização (C) e
    recontagem (D)) — cada chamada consome o próximo item, na ordem em que
    o service realmente as faz. Uma lista mais curta que o necessário
    esgota e levanta IndexError — sinal claro de uma consulta a mais."""
    contadores: dict = {}

    def _query(model, *args, **kwargs):
        valor = mapa[model]
        if isinstance(valor, list):
            indice = contadores.get(model, 0)
            contadores[model] = indice + 1
            return valor[indice]
        return valor

    return _query


def _fake_get(mapa: dict):
    def _get(model, ident, **kwargs):
        return mapa.get(model)

    return _get


def _db_mock_registrar(item_orm, acao_existente=None, usuario_orm=None):
    db = MagicMock()
    fake_a = FakeQuery(resultado=item_orm)
    fake_b = FakeQuery(resultado=acao_existente)
    db.query.side_effect = _query_dispatcher({
        ItemRelatorioDiarioORM: fake_a,
        AcaoPreventivaORM: fake_b,
    })
    db.get.side_effect = _fake_get({UsuarioORM: usuario_orm})

    def _fake_refresh(obj):
        # Simula o banco atribuindo id/criada_em/atualizada_em no INSERT
        # real (server_default/autoincrement) — só no caminho de criação
        # de registrar(), onde AcaoPreventivaORM é construído sem esses
        # três campos. Mesma técnica já usada em
        # test_movimentacao_service.py e test_relatorio_acao_diaria_service.py.
        if getattr(obj, "id", None) is None:
            obj.id = 999
        if getattr(obj, "criada_em", None) is None:
            obj.criada_em = datetime.now()
        if getattr(obj, "atualizada_em", None) is None:
            obj.atualizada_em = datetime.now()

    db.refresh.side_effect = _fake_refresh
    return db, fake_a, fake_b


def _db_mock_atualizar(acao_orm, item_orm=None, relatorio_orm=None, total_concluidas=0, com_recontagem=True):
    db = MagicMock()
    fake_c = FakeQuery(resultado=acao_orm)
    lista_acao_preventiva = [fake_c]
    fake_d = None
    if com_recontagem:
        fake_d = FakeQuery(resultado=total_concluidas, db_para_verificar_flush=db)
        lista_acao_preventiva.append(fake_d)
    db.query.side_effect = _query_dispatcher({AcaoPreventivaORM: lista_acao_preventiva})
    db.get.side_effect = _fake_get({ItemRelatorioDiarioORM: item_orm, RelatorioAcaoDiarioORM: relatorio_orm})
    return db, fake_c, fake_d


# =============================================================================
# REGISTRAR
# =============================================================================


def test_registrar_sucesso_copia_acao_recomendada_status_inicial_e_commit_unico():
    item_orm = _item(acao_recomendada="Retirar do estoque imediatamente.")
    db, fake_a, fake_b = _db_mock_registrar(item_orm)
    request = AcaoPreventivaCreateRequest()

    resultado = service.registrar(db, ID_MERCADO, item_orm.id, request)

    assert resultado.acao_recomendada == "Retirar do estoque imediatamente."
    assert resultado.status == service.STATUS_RECOMENDADA
    acao_criada = db.add.call_args.args[0]
    db.commit.assert_called_once()
    db.refresh.assert_called_once_with(acao_criada)


def test_registrar_aceita_id_usuario_responsavel_valido_do_mesmo_mercado():
    item_orm = _item()
    usuario_orm = _usuario(id_usuario=7, id_mercado=ID_MERCADO)
    db, fake_a, fake_b = _db_mock_registrar(item_orm, usuario_orm=usuario_orm)
    request = AcaoPreventivaCreateRequest(id_usuario_responsavel=7)

    resultado = service.registrar(db, ID_MERCADO, item_orm.id, request)

    assert resultado.id_usuario_responsavel == 7
    db.commit.assert_called_once()


def test_registrar_id_usuario_responsavel_none_e_aceito():
    item_orm = _item()
    db, fake_a, fake_b = _db_mock_registrar(item_orm)
    request = AcaoPreventivaCreateRequest(id_usuario_responsavel=None)

    resultado = service.registrar(db, ID_MERCADO, item_orm.id, request)

    assert resultado.id_usuario_responsavel is None
    db.commit.assert_called_once()


def test_registrar_idempotente_retorna_acao_existente_sem_add_nem_commit():
    item_orm = _item()
    acao_existente = _acao(id_acao=42, id_item_relatorio=item_orm.id, status="em_andamento")
    db, fake_a, fake_b = _db_mock_registrar(item_orm, acao_existente=acao_existente)
    request = AcaoPreventivaCreateRequest(observacao="tentativa duplicada")

    resultado = service.registrar(db, ID_MERCADO, item_orm.id, request)

    assert resultado.id == 42
    assert resultado.status == "em_andamento"  # não sobrescrito pela nova requisição
    db.add.assert_not_called()
    db.commit.assert_not_called()
    db.refresh.assert_not_called()


@pytest.mark.parametrize("motivo", ["item_inexistente", "item_de_outro_mercado"])
def test_registrar_item_inexistente_ou_outro_mercado_levanta_item_nao_encontrado(motivo):
    # Em ambos os casos a query A (já filtrada por id_mercado) não
    # encontra nada — indistinguível para o service (RN05).
    db, fake_a, fake_b = _db_mock_registrar(item_orm=None)
    request = AcaoPreventivaCreateRequest()

    with pytest.raises(service.ItemRelatorioNaoEncontrado):
        service.registrar(db, ID_MERCADO, 999, request)

    db.add.assert_not_called()
    db.commit.assert_not_called()


def test_registrar_usuario_responsavel_invalido_levanta_usuario_nao_encontrado():
    item_orm = _item()
    db, fake_a, fake_b = _db_mock_registrar(item_orm, usuario_orm=None)
    request = AcaoPreventivaCreateRequest(id_usuario_responsavel=999)

    with pytest.raises(UsuarioNaoEncontrado):
        service.registrar(db, ID_MERCADO, item_orm.id, request)

    db.add.assert_not_called()
    db.commit.assert_not_called()


def test_registrar_falha_no_commit_causa_rollback_e_propaga_excecao():
    item_orm = _item()
    db, fake_a, fake_b = _db_mock_registrar(item_orm)
    db.commit.side_effect = RuntimeError("falha simulada de banco")
    request = AcaoPreventivaCreateRequest()

    with pytest.raises(RuntimeError, match="falha simulada de banco"):
        service.registrar(db, ID_MERCADO, item_orm.id, request)

    db.rollback.assert_called_once()


def test_registrar_nao_altera_totais_do_relatorio():
    item_orm = _item()
    db, fake_a, fake_b = _db_mock_registrar(item_orm)
    request = AcaoPreventivaCreateRequest()

    service.registrar(db, ID_MERCADO, item_orm.id, request)

    # registrar() nunca consulta RelatorioAcaoDiarioORM — sem
    # id_usuario_responsavel na requisição, db.get nem chega a ser usado.
    db.get.assert_not_called()


def test_registrar_rollback_nao_e_chamado_quando_usuario_invalido():
    item_orm = _item()
    db, fake_a, fake_b = _db_mock_registrar(item_orm, usuario_orm=None)
    request = AcaoPreventivaCreateRequest(id_usuario_responsavel=999)

    with pytest.raises(UsuarioNaoEncontrado):
        service.registrar(db, ID_MERCADO, item_orm.id, request)

    db.rollback.assert_not_called()


def test_registrar_rollback_nao_e_chamado_quando_item_nao_encontrado():
    db, fake_a, fake_b = _db_mock_registrar(item_orm=None)
    request = AcaoPreventivaCreateRequest()

    with pytest.raises(service.ItemRelatorioNaoEncontrado):
        service.registrar(db, ID_MERCADO, 999, request)

    db.rollback.assert_not_called()


def test_query_a_filtra_por_id_mercado_via_join():
    item_orm = _item()
    db, fake_a, fake_b = _db_mock_registrar(item_orm)
    request = AcaoPreventivaCreateRequest()

    service.registrar(db, ID_MERCADO, item_orm.id, request)

    clausulas = fake_a.filter_args[0]
    esperado = RelatorioAcaoDiarioORM.id_mercado == ID_MERCADO
    assert any(c.compare(esperado) for c in clausulas)


# =============================================================================
# ATUALIZAR
# =============================================================================


def test_atualizar_parcial_observacao_mantem_demais_campos():
    acao_orm = _acao(status="recomendada", acao_realizada="realizado original", observacao="obs original")
    db, fake_c, fake_d = _db_mock_atualizar(acao_orm, com_recontagem=False)
    request = AcaoPreventivaEditRequest(observacao="obs nova")

    resultado = service.atualizar(db, ID_MERCADO, acao_orm.id, request)

    assert resultado.observacao == "obs nova"
    assert resultado.status == "recomendada"
    assert resultado.acao_realizada == "realizado original"


@pytest.mark.parametrize("status_valido", ["recomendada", "em_andamento", "concluida", "cancelada"])
def test_atualizar_aceita_cada_status_permitido(status_valido):
    acao_orm = _acao(id_acao=1, id_item_relatorio=1, status="recomendada")
    item_orm = _item(id_item=1, id_relatorio=ID_RELATORIO)
    relatorio_orm = _relatorio()
    db, fake_c, fake_d = _db_mock_atualizar(
        acao_orm,
        item_orm=item_orm,
        relatorio_orm=relatorio_orm,
        total_concluidas=1 if status_valido == "concluida" else 0,
    )
    request = AcaoPreventivaEditRequest(status=status_valido)

    resultado = service.atualizar(db, ID_MERCADO, acao_orm.id, request)

    assert resultado.status == status_valido


def test_atualizar_status_invalido_levanta_excecao_e_nada_persiste():
    acao_orm = _acao(status="recomendada")
    db, fake_c, fake_d = _db_mock_atualizar(acao_orm, com_recontagem=False)
    request = AcaoPreventivaEditRequest(status="inexistente")

    with pytest.raises(service.StatusAcaoPreventivaInvalido):
        service.atualizar(db, ID_MERCADO, acao_orm.id, request)

    assert acao_orm.status == "recomendada"
    db.commit.assert_not_called()
    db.rollback.assert_not_called()


@pytest.mark.parametrize("motivo", ["acao_inexistente", "acao_de_outro_mercado"])
def test_atualizar_acao_inexistente_ou_outro_mercado_levanta_nao_encontrada(motivo):
    db, fake_c, fake_d = _db_mock_atualizar(acao_orm=None, com_recontagem=False)
    request = AcaoPreventivaEditRequest(observacao="x")

    with pytest.raises(service.AcaoPreventivaNaoEncontrada):
        service.atualizar(db, ID_MERCADO, 999, request)

    db.commit.assert_not_called()
    db.rollback.assert_not_called()


def test_atualizar_recomendada_para_concluida_recalcula_total():
    acao_orm = _acao(id_acao=1, id_item_relatorio=1, status="recomendada")
    item_orm = _item(id_item=1, id_relatorio=ID_RELATORIO)
    relatorio_orm = _relatorio(total_acoes_realizadas=0)
    db, fake_c, fake_d = _db_mock_atualizar(
        acao_orm, item_orm=item_orm, relatorio_orm=relatorio_orm, total_concluidas=1
    )
    request = AcaoPreventivaEditRequest(status="concluida")

    service.atualizar(db, ID_MERCADO, acao_orm.id, request)

    assert relatorio_orm.total_acoes_realizadas == 1


def test_atualizar_concluida_para_cancelada_recalcula_total():
    acao_orm = _acao(id_acao=1, id_item_relatorio=1, status="concluida")
    item_orm = _item(id_item=1, id_relatorio=ID_RELATORIO)
    relatorio_orm = _relatorio(total_acoes_realizadas=1)
    db, fake_c, fake_d = _db_mock_atualizar(
        acao_orm, item_orm=item_orm, relatorio_orm=relatorio_orm, total_concluidas=0
    )
    request = AcaoPreventivaEditRequest(status="cancelada")

    service.atualizar(db, ID_MERCADO, acao_orm.id, request)

    assert relatorio_orm.total_acoes_realizadas == 0


def test_atualizar_concluida_para_em_andamento_recalcula_total():
    acao_orm = _acao(id_acao=1, id_item_relatorio=1, status="concluida")
    item_orm = _item(id_item=1, id_relatorio=ID_RELATORIO)
    relatorio_orm = _relatorio(total_acoes_realizadas=1)
    db, fake_c, fake_d = _db_mock_atualizar(
        acao_orm, item_orm=item_orm, relatorio_orm=relatorio_orm, total_concluidas=0
    )
    request = AcaoPreventivaEditRequest(status="em_andamento")

    service.atualizar(db, ID_MERCADO, acao_orm.id, request)

    assert relatorio_orm.total_acoes_realizadas == 0


def test_atualizar_duas_vezes_para_concluida_nao_duplica_total():
    acao_orm = _acao(id_acao=1, id_item_relatorio=1, status="recomendada")
    item_orm = _item(id_item=1, id_relatorio=ID_RELATORIO)
    relatorio_orm = _relatorio(total_acoes_realizadas=0)

    db1, _, _ = _db_mock_atualizar(acao_orm, item_orm=item_orm, relatorio_orm=relatorio_orm, total_concluidas=1)
    service.atualizar(db1, ID_MERCADO, acao_orm.id, AcaoPreventivaEditRequest(status="concluida"))
    assert relatorio_orm.total_acoes_realizadas == 1

    # Segunda chamada, ação já concluída, request pede "concluida" de novo
    # — a recontagem real ainda encontraria só 1 ação concluída, nunca 2
    # (diferente de um `+= 1` cego).
    db2, _, _ = _db_mock_atualizar(acao_orm, item_orm=item_orm, relatorio_orm=relatorio_orm, total_concluidas=1)
    service.atualizar(db2, ID_MERCADO, acao_orm.id, AcaoPreventivaEditRequest(status="concluida"))
    assert relatorio_orm.total_acoes_realizadas == 1


def test_recontagem_considera_apenas_acoes_concluidas():
    acao_orm = _acao(id_acao=1, id_item_relatorio=1, status="em_andamento")
    item_orm = _item(id_item=1, id_relatorio=ID_RELATORIO)
    relatorio_orm = _relatorio(total_acoes_realizadas=0)
    db, fake_c, fake_d = _db_mock_atualizar(
        acao_orm, item_orm=item_orm, relatorio_orm=relatorio_orm, total_concluidas=1
    )
    request = AcaoPreventivaEditRequest(status="concluida")

    service.atualizar(db, ID_MERCADO, acao_orm.id, request)

    assert relatorio_orm.total_acoes_realizadas == 1


def test_query_d_filtra_por_id_relatorio_e_status_concluida():
    acao_orm = _acao(id_acao=1, id_item_relatorio=1, status="recomendada")
    item_orm = _item(id_item=1, id_relatorio=ID_RELATORIO)
    relatorio_orm = _relatorio()
    db, fake_c, fake_d = _db_mock_atualizar(
        acao_orm, item_orm=item_orm, relatorio_orm=relatorio_orm, total_concluidas=0
    )
    request = AcaoPreventivaEditRequest(status="concluida")

    service.atualizar(db, ID_MERCADO, acao_orm.id, request)

    assert fake_d.join_args  # JOIN com ItemRelatorioDiarioORM
    clausulas = fake_d.filter_args[0]
    esperado_relatorio = ItemRelatorioDiarioORM.id_relatorio == item_orm.id_relatorio
    esperado_status = AcaoPreventivaORM.status == service.STATUS_CONCLUIDA
    assert any(c.compare(esperado_relatorio) for c in clausulas)
    assert any(c.compare(esperado_status) for c in clausulas)


def test_atualizar_sem_status_nao_recalcula_nem_faz_flush():
    acao_orm = _acao(status="recomendada", observacao="antiga")
    db, fake_c, fake_d = _db_mock_atualizar(acao_orm, com_recontagem=False)
    request = AcaoPreventivaEditRequest(observacao="nova")

    service.atualizar(db, ID_MERCADO, acao_orm.id, request)

    db.flush.assert_not_called()
    db.get.assert_not_called()
    assert fake_d is None


def test_atualizar_com_status_flush_ocorre_antes_da_contagem():
    acao_orm = _acao(id_acao=1, id_item_relatorio=1, status="recomendada")
    item_orm = _item(id_item=1, id_relatorio=ID_RELATORIO)
    relatorio_orm = _relatorio()
    db, fake_c, fake_d = _db_mock_atualizar(
        acao_orm, item_orm=item_orm, relatorio_orm=relatorio_orm, total_concluidas=1
    )
    request = AcaoPreventivaEditRequest(status="concluida")

    service.atualizar(db, ID_MERCADO, acao_orm.id, request)

    assert db.flush.call_count == 1
    assert fake_d.flush_ja_ocorreu_no_count is True


def test_atualizar_atualizada_em_muda_apos_update():
    antes = datetime.now() - timedelta(days=1)
    acao_orm = _acao(status="recomendada", atualizada_em=antes)
    db, fake_c, fake_d = _db_mock_atualizar(acao_orm, com_recontagem=False)
    request = AcaoPreventivaEditRequest(observacao="qualquer coisa")

    service.atualizar(db, ID_MERCADO, acao_orm.id, request)

    assert acao_orm.atualizada_em > antes


def test_atualizar_commit_unico_no_sucesso():
    acao_orm = _acao(status="recomendada")
    db, fake_c, fake_d = _db_mock_atualizar(acao_orm, com_recontagem=False)
    request = AcaoPreventivaEditRequest(observacao="ok")

    service.atualizar(db, ID_MERCADO, acao_orm.id, request)

    assert db.commit.call_count == 1
    db.rollback.assert_not_called()


def test_atualizar_rollback_se_commit_falhar():
    acao_orm = _acao(status="recomendada")
    db, fake_c, fake_d = _db_mock_atualizar(acao_orm, com_recontagem=False)
    db.commit.side_effect = RuntimeError("falha simulada de banco")
    request = AcaoPreventivaEditRequest(observacao="ok")

    with pytest.raises(RuntimeError, match="falha simulada de banco"):
        service.atualizar(db, ID_MERCADO, acao_orm.id, request)

    db.rollback.assert_called_once()


def test_atualizar_rollback_nao_e_chamado_em_status_invalido():
    acao_orm = _acao(status="recomendada")
    db, fake_c, fake_d = _db_mock_atualizar(acao_orm, com_recontagem=False)
    request = AcaoPreventivaEditRequest(status="status_qualquer_invalido")

    with pytest.raises(service.StatusAcaoPreventivaInvalido):
        service.atualizar(db, ID_MERCADO, acao_orm.id, request)

    db.rollback.assert_not_called()
    db.commit.assert_not_called()


def test_query_c_filtra_por_id_mercado_via_join_duplo():
    acao_orm = _acao(status="recomendada")
    db, fake_c, fake_d = _db_mock_atualizar(acao_orm, com_recontagem=False)
    request = AcaoPreventivaEditRequest(observacao="x")

    service.atualizar(db, ID_MERCADO, acao_orm.id, request)

    clausulas = fake_c.filter_args[0]
    esperado = RelatorioAcaoDiarioORM.id_mercado == ID_MERCADO
    assert any(c.compare(esperado) for c in clausulas)
    assert fake_c.travada_com_for_update is True


# =============================================================================
# preenchimento automático de data_inicio/data_fim
# =============================================================================


def test_atualizar_preenche_data_inicio_automaticamente_ao_mudar_para_em_andamento():
    acao_orm = _acao(id_acao=1, id_item_relatorio=1, status="recomendada", data_inicio=None)
    item_orm = _item(id_item=1, id_relatorio=ID_RELATORIO)
    relatorio_orm = _relatorio()
    db, fake_c, fake_d = _db_mock_atualizar(
        acao_orm, item_orm=item_orm, relatorio_orm=relatorio_orm, total_concluidas=0
    )
    request = AcaoPreventivaEditRequest(status="em_andamento")

    antes = datetime.now()
    resultado = service.atualizar(db, ID_MERCADO, acao_orm.id, request)

    assert resultado.data_inicio is not None
    assert abs((resultado.data_inicio - antes).total_seconds()) < 2


def test_atualizar_nao_sobrescreve_data_inicio_ja_existente():
    data_inicio_original = datetime(2026, 1, 1, 10, 0, 0)
    acao_orm = _acao(
        id_acao=1, id_item_relatorio=1, status="recomendada", data_inicio=data_inicio_original
    )
    item_orm = _item(id_item=1, id_relatorio=ID_RELATORIO)
    relatorio_orm = _relatorio()
    db, fake_c, fake_d = _db_mock_atualizar(
        acao_orm, item_orm=item_orm, relatorio_orm=relatorio_orm, total_concluidas=0
    )
    request = AcaoPreventivaEditRequest(status="em_andamento")

    resultado = service.atualizar(db, ID_MERCADO, acao_orm.id, request)

    assert resultado.data_inicio == data_inicio_original


def test_atualizar_respeita_data_inicio_enviada_explicitamente():
    data_inicio_explicita = datetime(2026, 3, 15, 8, 0, 0)
    acao_orm = _acao(id_acao=1, id_item_relatorio=1, status="recomendada", data_inicio=None)
    item_orm = _item(id_item=1, id_relatorio=ID_RELATORIO)
    relatorio_orm = _relatorio()
    db, fake_c, fake_d = _db_mock_atualizar(
        acao_orm, item_orm=item_orm, relatorio_orm=relatorio_orm, total_concluidas=0
    )
    request = AcaoPreventivaEditRequest(status="em_andamento", data_inicio=data_inicio_explicita)

    resultado = service.atualizar(db, ID_MERCADO, acao_orm.id, request)

    assert resultado.data_inicio == data_inicio_explicita


def test_atualizar_preenche_data_fim_automaticamente_ao_mudar_para_concluida():
    acao_orm = _acao(id_acao=1, id_item_relatorio=1, status="em_andamento", data_fim=None)
    item_orm = _item(id_item=1, id_relatorio=ID_RELATORIO)
    relatorio_orm = _relatorio()
    db, fake_c, fake_d = _db_mock_atualizar(
        acao_orm, item_orm=item_orm, relatorio_orm=relatorio_orm, total_concluidas=1
    )
    request = AcaoPreventivaEditRequest(status="concluida")

    antes = datetime.now()
    resultado = service.atualizar(db, ID_MERCADO, acao_orm.id, request)

    assert resultado.data_fim is not None
    assert abs((resultado.data_fim - antes).total_seconds()) < 2


def test_atualizar_nao_sobrescreve_data_fim_ja_existente():
    data_fim_original = datetime(2026, 1, 2, 18, 0, 0)
    acao_orm = _acao(
        id_acao=1, id_item_relatorio=1, status="em_andamento", data_fim=data_fim_original
    )
    item_orm = _item(id_item=1, id_relatorio=ID_RELATORIO)
    relatorio_orm = _relatorio()
    db, fake_c, fake_d = _db_mock_atualizar(
        acao_orm, item_orm=item_orm, relatorio_orm=relatorio_orm, total_concluidas=1
    )
    request = AcaoPreventivaEditRequest(status="concluida")

    resultado = service.atualizar(db, ID_MERCADO, acao_orm.id, request)

    assert resultado.data_fim == data_fim_original


def test_atualizar_respeita_data_fim_enviada_explicitamente():
    data_fim_explicita = datetime(2026, 3, 20, 17, 30, 0)
    acao_orm = _acao(id_acao=1, id_item_relatorio=1, status="em_andamento", data_fim=None)
    item_orm = _item(id_item=1, id_relatorio=ID_RELATORIO)
    relatorio_orm = _relatorio()
    db, fake_c, fake_d = _db_mock_atualizar(
        acao_orm, item_orm=item_orm, relatorio_orm=relatorio_orm, total_concluidas=1
    )
    request = AcaoPreventivaEditRequest(status="concluida", data_fim=data_fim_explicita)

    resultado = service.atualizar(db, ID_MERCADO, acao_orm.id, request)

    assert resultado.data_fim == data_fim_explicita


def test_atualizar_nao_preenche_datas_quando_status_nao_muda():
    acao_orm = _acao(
        id_acao=1, id_item_relatorio=1, status="em_andamento", data_inicio=None, data_fim=None
    )
    db, fake_c, fake_d = _db_mock_atualizar(acao_orm, com_recontagem=False)
    request = AcaoPreventivaEditRequest(observacao="apenas uma nota")

    resultado = service.atualizar(db, ID_MERCADO, acao_orm.id, request)

    assert resultado.data_inicio is None
    assert resultado.data_fim is None
