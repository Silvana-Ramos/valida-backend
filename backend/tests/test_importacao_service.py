"""Testes unitários de app.services.importacao_service (RN07, pipeline de
importação de vendas). A Session do SQLAlchemy é sempre mockada aqui:
nenhum teste conecta a nenhum banco, real ou em memória."""

from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import MagicMock

import pytest

from app.models.importacao import ImportacaoORM
from app.models.item_importacao import ItemImportacaoORM
from app.models.lote import LoteORM
from app.models.produto import ProdutoORM
from app.schemas.enums import StatusLote
from app.schemas.importacao import StatusImportacao, StatusProcessamentoItem
from app.schemas.movimentacao_estoque import OrigemMovimentacao
from app.schemas.produto import CategoriaProduto, UnidadeMedida
from app.services.importacao_parser import ArquivoInvalido
from app.services.importacao_service import (
    MAX_LINHAS_IMPORTACAO,
    ArquivoJaProcessado,
    processar_arquivo_venda,
)

ID_MERCADO = 5
VENCIDO = date.today() - timedelta(days=1)
NAO_VENCIDO = date.today() + timedelta(days=10)
NAO_VENCIDO_MAIS_LONGE = date.today() + timedelta(days=30)

CSV_UMA_LINHA = (
    b"referencia_externa,produto,numero_lote,quantidade\r\n"
    b"ref-1,COD-1,,3\r\n"
)


def _produto(**overrides) -> ProdutoORM:
    dados = dict(
        id=10,
        id_mercado=ID_MERCADO,
        nome="Pao Frances",
        categoria=CategoriaProduto.PADARIA,
        unidade_medida=UnidadeMedida.KG,
        codigo_sistema_origem="COD-1",
        codigo_barras="7891234567890",
    )
    dados.update(overrides)
    return ProdutoORM(**dados)


def _lote(saldo: Decimal, data_validade: date = NAO_VENCIDO, **overrides) -> LoteORM:
    dados = dict(
        id=20,
        id_mercado=ID_MERCADO,
        id_produto=10,
        status=StatusLote.CONFIRMADO,
        status_operacional="disponivel",
        quantidade_disponivel=saldo,
        quantidade_inicial=saldo,
        data_validade=data_validade,
        numero_lote=None,
    )
    dados.update(overrides)
    return LoteORM(**dados)


def _mock_db() -> MagicMock:
    db = MagicMock()

    produto_q = MagicMock()
    produto_q.filter.return_value.first.return_value = None
    lote_q = MagicMock()
    # Dois caminhos reais em _resolver_lote: explicito (.filter().all()) e
    # FEFO (.filter().order_by().all()) — os dois precisam ser
    # configurados, já que são chamadas de mock distintas mesmo vindo do
    # mesmo db.query(LoteORM).
    lote_q.filter.return_value.all.return_value = []
    lote_q.filter.return_value.order_by.return_value.all.return_value = []
    importacao_q = MagicMock()
    importacao_q.filter.return_value.first.return_value = None
    item_q = MagicMock()
    item_q.filter.return_value.first.return_value = None

    def query_side_effect(model):
        return {
            ProdutoORM: produto_q,
            LoteORM: lote_q,
            ImportacaoORM: importacao_q,
            ItemImportacaoORM: item_q,
        }.get(model, MagicMock())

    db.query.side_effect = query_side_effect
    db.produto_q = produto_q
    db.lote_q = lote_q
    db.importacao_q = importacao_q
    db.item_q = item_q

    def get_side_effect(model, ident, **kwargs):
        # registrar_venda trava o lote via db.get — devolve o mesmo objeto
        # já resolvido por _resolver_lote, para que as mutações se
        # reflitam no mesmo lote que o teste inspeciona.
        if model is LoteORM:
            candidatos = (
                list(lote_q.filter.return_value.all.return_value)
                + list(lote_q.filter.return_value.order_by.return_value.all.return_value)
            )
            for candidato in candidatos:
                if candidato.id == ident:
                    return candidato
        return None

    db.get.side_effect = get_side_effect

    def refresh_side_effect(obj):
        if getattr(obj, "id", None) is None:
            obj.id = 999

    db.refresh.side_effect = refresh_side_effect
    return db


def _definir_lotes(db: MagicMock, lotes: list[LoteORM]) -> None:
    """Configura os lotes visíveis pelos dois caminhos de query reais de
    _resolver_lote (explícito por número e FEFO com order_by)."""
    db.lote_q.filter.return_value.all.return_value = lotes
    db.lote_q.filter.return_value.order_by.return_value.all.return_value = lotes


def test_linha_bem_sucedida_via_codigo_sistema_origem():
    db = _mock_db()
    db.produto_q.filter.return_value.first.return_value = _produto()
    lote = _lote(Decimal("10"))
    _definir_lotes(db, [lote])

    importacao = processar_arquivo_venda(db, ID_MERCADO, "vendas.csv", CSV_UMA_LINHA)

    assert importacao.status == StatusImportacao.CONCLUIDA
    assert importacao.total_processadas == 1
    assert importacao.total_com_erro == 0
    assert importacao.total_duplicadas == 0
    assert lote.quantidade_disponivel == Decimal("7")


def test_produto_resolvido_por_codigo_barras_quando_codigo_origem_nao_bate():
    db = _mock_db()
    produto = _produto()
    db.produto_q.filter.return_value.first.side_effect = [None, produto]
    lote = _lote(Decimal("10"))
    _definir_lotes(db, [lote])

    importacao = processar_arquivo_venda(db, ID_MERCADO, "vendas.csv", CSV_UMA_LINHA)

    assert importacao.total_processadas == 1


def test_produto_resolvido_por_nome_quando_codigos_nao_batem():
    db = _mock_db()
    produto = _produto()
    db.produto_q.filter.return_value.first.side_effect = [None, None, produto]
    lote = _lote(Decimal("10"))
    _definir_lotes(db, [lote])

    importacao = processar_arquivo_venda(db, ID_MERCADO, "vendas.csv", CSV_UMA_LINHA)

    assert importacao.total_processadas == 1


def test_produto_nao_encontrado_e_erro_de_linha():
    db = _mock_db()  # produto_q.first() -> None sempre

    importacao = processar_arquivo_venda(db, ID_MERCADO, "vendas.csv", CSV_UMA_LINHA)

    assert importacao.total_processadas == 0
    assert importacao.total_com_erro == 1
    assert importacao.status == StatusImportacao.CONCLUIDA_COM_ERROS


def test_lote_explicito_por_numero_lote():
    csv_com_lote = (
        b"referencia_externa,produto,numero_lote,quantidade\r\n"
        b"ref-1,COD-1,L10,3\r\n"
    )
    db = _mock_db()
    db.produto_q.filter.return_value.first.return_value = _produto()
    lote = _lote(Decimal("10"), numero_lote="L10")
    _definir_lotes(db, [lote])

    importacao = processar_arquivo_venda(db, ID_MERCADO, "vendas.csv", csv_com_lote)

    assert importacao.total_processadas == 1
    assert lote.quantidade_disponivel == Decimal("7")


def test_lote_ambiguo_por_numero_lote_e_erro_de_linha():
    csv_com_lote = (
        b"referencia_externa,produto,numero_lote,quantidade\r\n"
        b"ref-1,COD-1,L10,3\r\n"
    )
    db = _mock_db()
    db.produto_q.filter.return_value.first.return_value = _produto()
    lote1 = _lote(Decimal("10"), numero_lote="L10")
    lote2 = _lote(Decimal("5"), numero_lote="L10", id=21)
    _definir_lotes(db, [lote1, lote2])

    importacao = processar_arquivo_venda(db, ID_MERCADO, "vendas.csv", csv_com_lote)

    assert importacao.total_com_erro == 1
    assert importacao.total_processadas == 0


def test_fefo_escolhe_lote_de_validade_mais_proxima_com_saldo_suficiente():
    db = _mock_db()
    db.produto_q.filter.return_value.first.return_value = _produto()
    lote_mais_proximo = _lote(Decimal("10"), data_validade=NAO_VENCIDO, id=20)
    lote_mais_distante = _lote(Decimal("10"), data_validade=NAO_VENCIDO_MAIS_LONGE, id=21)
    # A ordenação real é feita pela query (order_by na consulta real); o
    # mock já devolve na ordem que o ORDER BY produziria.
    _definir_lotes(db, [lote_mais_proximo, lote_mais_distante])

    importacao = processar_arquivo_venda(db, ID_MERCADO, "vendas.csv", CSV_UMA_LINHA)

    assert importacao.total_processadas == 1
    assert lote_mais_proximo.quantidade_disponivel == Decimal("7")
    assert lote_mais_distante.quantidade_disponivel == Decimal("10")  # intocado


def test_fefo_sem_lote_suficiente_e_erro_de_linha():
    db = _mock_db()
    db.produto_q.filter.return_value.first.return_value = _produto()
    # Nenhum lote sozinho cobre a quantidade de 3 pedida.
    _definir_lotes(db, [_lote(Decimal("1"))])

    importacao = processar_arquivo_venda(db, ID_MERCADO, "vendas.csv", CSV_UMA_LINHA)

    assert importacao.total_com_erro == 1
    assert importacao.total_processadas == 0


def test_quantidade_invalida_e_erro_de_linha():
    csv_invalido = (
        b"referencia_externa,produto,numero_lote,quantidade\r\n"
        b"ref-1,COD-1,,abc\r\n"
    )
    db = _mock_db()
    db.produto_q.filter.return_value.first.return_value = _produto()

    importacao = processar_arquivo_venda(db, ID_MERCADO, "vendas.csv", csv_invalido)

    assert importacao.total_com_erro == 1
    assert importacao.total_processadas == 0


def test_referencia_externa_vazia_e_erro_de_linha():
    csv_sem_ref = (
        b"referencia_externa,produto,numero_lote,quantidade\r\n"
        b" ,COD-1,,3\r\n"
    )
    db = _mock_db()

    importacao = processar_arquivo_venda(db, ID_MERCADO, "vendas.csv", csv_sem_ref)

    assert importacao.total_com_erro == 1


def test_referencia_externa_duplicada_marca_duplicada():
    db = _mock_db()
    db.item_q.filter.return_value.first.return_value = ItemImportacaoORM(id=1)

    importacao = processar_arquivo_venda(db, ID_MERCADO, "vendas.csv", CSV_UMA_LINHA)

    assert importacao.total_duplicadas == 1
    assert importacao.total_processadas == 0
    assert importacao.status == StatusImportacao.CONCLUIDA_COM_ERROS


def test_saldo_insuficiente_no_registrar_venda_e_erro_de_linha():
    db = _mock_db()
    db.produto_q.filter.return_value.first.return_value = _produto()
    # FEFO escolhe este lote por parecer suficiente (10 >= 3), mas
    # registrar_venda decide com base no mesmo objeto — para simular uma
    # corrida real seria preciso mutar entre a escolha e o lock; aqui
    # simulamos diretamente um saldo insuficiente já no momento da escolha.
    _definir_lotes(db, [_lote(Decimal("2"))])

    importacao = processar_arquivo_venda(db, ID_MERCADO, "vendas.csv", CSV_UMA_LINHA)

    assert importacao.total_com_erro == 1


def test_lote_nao_confirmado_e_erro_de_linha():
    db = _mock_db()
    db.produto_q.filter.return_value.first.return_value = _produto()
    lote_pendente = _lote(Decimal("10"), status=StatusLote.PENDENTE_CONFIRMACAO)
    # _resolver_lote já filtra status=confirmado na query real; aqui o
    # mock simula o caso em que a query real não devolveria nada.
    _definir_lotes(db, [])

    importacao = processar_arquivo_venda(db, ID_MERCADO, "vendas.csv", CSV_UMA_LINHA)

    assert importacao.total_com_erro == 1


def test_arquivo_ja_processado_e_rejeitado():
    db = _mock_db()
    db.importacao_q.filter.return_value.first.return_value = ImportacaoORM(id=1)

    with pytest.raises(ArquivoJaProcessado):
        processar_arquivo_venda(db, ID_MERCADO, "vendas.csv", CSV_UMA_LINHA)

    db.add.assert_not_called()
    db.commit.assert_not_called()


def test_arquivo_invalido_propaga_sem_criar_importacao():
    db = _mock_db()

    with pytest.raises(ArquivoInvalido):
        processar_arquivo_venda(db, ID_MERCADO, "vendas.csv", b"col1,col2\r\nx,y\r\n")

    db.add.assert_not_called()
    db.commit.assert_not_called()


def test_limite_de_linhas_excedido_e_rejeitado():
    cabecalho = "referencia_externa,produto,numero_lote,quantidade\r\n"
    linhas = "".join(f"ref-{i},COD-1,,1\r\n" for i in range(MAX_LINHAS_IMPORTACAO + 1))
    csv_grande = (cabecalho + linhas).encode()
    db = _mock_db()

    with pytest.raises(ArquivoInvalido):
        processar_arquivo_venda(db, ID_MERCADO, "vendas.csv", csv_grande)

    db.add.assert_not_called()


def test_movimentacao_gravada_com_origem_importacao_externa_e_referencia():
    db = _mock_db()
    db.produto_q.filter.return_value.first.return_value = _produto()
    lote = _lote(Decimal("10"))
    _definir_lotes(db, [lote])

    processar_arquivo_venda(db, ID_MERCADO, "vendas.csv", CSV_UMA_LINHA)

    objetos_gravados = [chamada.args[0] for chamada in db.add.call_args_list]
    movimentacoes = [o for o in objetos_gravados if type(o).__name__ == "MovimentacaoEstoqueORM"]
    assert len(movimentacoes) == 1
    assert movimentacoes[0].origem == OrigemMovimentacao.IMPORTACAO_EXTERNA
    assert movimentacoes[0].referencia_externa == "ref-1"


def test_multiplas_linhas_mistura_sucesso_erro_e_duplicada():
    csv_multi = (
        b"referencia_externa,produto,numero_lote,quantidade\r\n"
        b"ref-ok,COD-1,,3\r\n"
        b"ref-produto-ausente,COD-INEXISTENTE,,1\r\n"
        b"ref-dup,COD-1,,1\r\n"
    )
    db = _mock_db()
    produto = _produto()
    # ref-ok resolve produto normalmente; ref-produto-ausente não encontra
    # (retorna None nas 3 tentativas de busca); ref-dup nem chega a
    # resolver produto, pois é barrada antes pela checagem de duplicidade.
    db.produto_q.filter.return_value.first.side_effect = [produto, None, None, None]
    lote = _lote(Decimal("10"))
    _definir_lotes(db, [lote])
    db.item_q.filter.return_value.first.side_effect = [None, None, ItemImportacaoORM(id=1)]

    importacao = processar_arquivo_venda(db, ID_MERCADO, "vendas.csv", csv_multi)

    assert importacao.total_processadas == 1
    assert importacao.total_com_erro == 1
    assert importacao.total_duplicadas == 1
    assert importacao.status == StatusImportacao.CONCLUIDA_COM_ERROS


def test_status_concluida_quando_tudo_processado_sem_erro():
    db = _mock_db()
    db.produto_q.filter.return_value.first.return_value = _produto()
    _definir_lotes(db, [_lote(Decimal("10"))])

    importacao = processar_arquivo_venda(db, ID_MERCADO, "vendas.csv", CSV_UMA_LINHA)

    assert importacao.status == StatusImportacao.CONCLUIDA
    assert importacao.data_hora_fim is not None
