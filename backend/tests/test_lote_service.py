"""Testes unitários de app/services/lote_service.py (Session mockada via
unittest.mock — nenhum teste aqui conecta a nenhum banco, real ou em
memória). Cobre principalmente o isolamento por id_mercado (RN05) que
cada função do serviço passou a impor nesta etapa: um lote de outro
mercado é tratado como inexistente (`LoteNaoEncontrado`), nunca como
"proibido"."""

from datetime import date, datetime, timedelta
from decimal import Decimal
from unittest.mock import MagicMock

import pytest

from app.models.historico_acao import HistoricoAcaoORM
from app.models.lote import LoteORM
from app.schemas.enums import NivelRisco, OrigemCadastro, StatusLote, TipoAcao
from app.schemas.historico_acao import OrigemAcao
from app.schemas.lote import LoteCreateRequest, LoteEditRequest
from app.services import lote_service
from app.services.lote_service import AcaoInvalidaParaStatus, LoteNaoEncontrado

ID_MERCADO = 5
OUTRO_MERCADO = 6
ID_LOTE = 1
NAO_VENCIDO = date.today() + timedelta(days=10)


def _lote(
    id_lote: int = ID_LOTE,
    id_mercado: int = ID_MERCADO,
    status: StatusLote = StatusLote.PENDENTE_CONFIRMACAO,
    data_validade: date = NAO_VENCIDO,
    quantidade: Decimal = Decimal("10"),
) -> LoteORM:
    return LoteORM(
        id=id_lote,
        id_mercado=id_mercado,
        id_produto=1,
        quantidade=quantidade,
        numero_lote=None,
        data_validade=data_validade,
        data_entrada=datetime.now(),
        origem_cadastro=OrigemCadastro.TEXTO,
        status=status,
        nivel_risco=NivelRisco.NORMAL,
        dias_restantes=10,
        data_ultima_atualizacao=datetime.now(),
        criado_por=None,
        preco_custo=None,
        status_operacional="disponivel",
        quantidade_disponivel=quantidade,
        quantidade_inicial=quantidade,
    )


@pytest.fixture
def db_mock():
    db = MagicMock()

    def refresh_side_effect(obj):
        # Simula o banco atribuindo o PK no INSERT real.
        if getattr(obj, "id", None) is None:
            obj.id = 999

    db.refresh.side_effect = refresh_side_effect
    return db


# --- criar_pendente ---------------------------------------------------------


def test_criar_pendente_cria_lote_pendente_confirmacao(db_mock):
    db_mock.query.return_value.filter.return_value.first.return_value = None  # produto novo

    request = LoteCreateRequest(
        produto_nome="Pao Frances", quantidade=10, data_validade=NAO_VENCIDO
    )
    lote = lote_service.criar_pendente(db_mock, ID_MERCADO, request)

    assert lote.id_mercado == ID_MERCADO
    assert lote.status == StatusLote.PENDENTE_CONFIRMACAO
    assert lote.quantidade == 10
    db_mock.commit.assert_called()


# --- obter -------------------------------------------------------------


def test_obter_retorna_lote(db_mock):
    db_mock.get.return_value = _lote()

    lote = lote_service.obter(db_mock, ID_MERCADO, ID_LOTE)

    assert lote.id == ID_LOTE


def test_obter_lote_inexistente_levanta_nao_encontrado(db_mock):
    db_mock.get.return_value = None

    with pytest.raises(LoteNaoEncontrado):
        lote_service.obter(db_mock, ID_MERCADO, ID_LOTE)


def test_obter_lote_de_outro_mercado_levanta_nao_encontrado(db_mock):
    db_mock.get.return_value = _lote(id_mercado=OUTRO_MERCADO)

    with pytest.raises(LoteNaoEncontrado):
        lote_service.obter(db_mock, ID_MERCADO, ID_LOTE)


def test_obter_retorna_quantidade_disponivel_apos_venda(db_mock):
    # Regressão: uma venda (RN07) só altera quantidade_disponivel — o
    # campo legado `quantidade` permanece no valor de cadastro. O GET
    # precisa refletir o estoque disponível atual, não o de cadastro.
    lote_orm = _lote(status=StatusLote.CONFIRMADO, quantidade=Decimal("10"))
    lote_orm.quantidade_disponivel = Decimal("9")  # simula venda de 1 unidade
    db_mock.get.return_value = lote_orm

    lote = lote_service.obter(db_mock, ID_MERCADO, ID_LOTE)

    assert lote.quantidade == 9


# --- listar ------------------------------------------------------------


def _definir_lotes(db: MagicMock, lotes: list[LoteORM]) -> None:
    db.query.return_value.filter.return_value.all.return_value = lotes
    db.query.return_value.filter.return_value.filter.return_value.all.return_value = lotes


def test_listar_retorna_lotes_do_mercado(db_mock):
    _definir_lotes(db_mock, [_lote(id_lote=1), _lote(id_lote=2)])

    lotes = lote_service.listar(db_mock, ID_MERCADO)

    assert len(lotes) == 2


def test_listar_com_status_aplica_segundo_filtro(db_mock):
    _definir_lotes(db_mock, [_lote(id_lote=1, status=StatusLote.CONFIRMADO)])

    lotes = lote_service.listar(db_mock, ID_MERCADO, status=StatusLote.CONFIRMADO)

    assert len(lotes) == 1


def test_listar_vazio(db_mock):
    _definir_lotes(db_mock, [])

    assert lote_service.listar(db_mock, ID_MERCADO) == []


def test_listar_retorna_quantidade_disponivel_apos_venda(db_mock):
    lote_orm = _lote(status=StatusLote.CONFIRMADO, quantidade=Decimal("10"))
    lote_orm.quantidade_disponivel = Decimal("9")  # simula venda de 1 unidade
    _definir_lotes(db_mock, [lote_orm])

    lotes = lote_service.listar(db_mock, ID_MERCADO)

    assert lotes[0].quantidade == 9


# --- editar_pendente ---------------------------------------------------


def test_editar_pendente_atualiza_campos(db_mock):
    db_mock.get.return_value = _lote(status=StatusLote.PENDENTE_CONFIRMACAO)

    lote = lote_service.editar_pendente(
        db_mock, ID_MERCADO, ID_LOTE, LoteEditRequest(quantidade=25)
    )

    assert lote.quantidade == 25


def test_editar_pendente_lote_de_outro_mercado_levanta_nao_encontrado(db_mock):
    db_mock.get.return_value = _lote(id_mercado=OUTRO_MERCADO)

    with pytest.raises(LoteNaoEncontrado):
        lote_service.editar_pendente(db_mock, ID_MERCADO, ID_LOTE, LoteEditRequest(quantidade=25))


def test_editar_pendente_lote_confirmado_levanta_acao_invalida(db_mock):
    db_mock.get.return_value = _lote(status=StatusLote.CONFIRMADO)

    with pytest.raises(AcaoInvalidaParaStatus):
        lote_service.editar_pendente(db_mock, ID_MERCADO, ID_LOTE, LoteEditRequest(quantidade=25))


# --- confirmar -----------------------------------------------------------


def test_confirmar_muda_status_para_confirmado(db_mock):
    db_mock.get.return_value = _lote(status=StatusLote.PENDENTE_CONFIRMACAO)

    lote = lote_service.confirmar(db_mock, ID_MERCADO, ID_LOTE)

    assert lote.status == StatusLote.CONFIRMADO


def test_confirmar_lote_de_outro_mercado_levanta_nao_encontrado(db_mock):
    db_mock.get.return_value = _lote(id_mercado=OUTRO_MERCADO)

    with pytest.raises(LoteNaoEncontrado):
        lote_service.confirmar(db_mock, ID_MERCADO, ID_LOTE)


def test_confirmar_lote_ja_confirmado_levanta_acao_invalida(db_mock):
    db_mock.get.return_value = _lote(status=StatusLote.CONFIRMADO)

    with pytest.raises(AcaoInvalidaParaStatus):
        lote_service.confirmar(db_mock, ID_MERCADO, ID_LOTE)


# --- cancelar ------------------------------------------------------------


def test_cancelar_remove_lote_pendente(db_mock):
    lote_orm = _lote(status=StatusLote.PENDENTE_CONFIRMACAO)
    db_mock.get.return_value = lote_orm

    lote_service.cancelar(db_mock, ID_MERCADO, ID_LOTE)

    db_mock.delete.assert_called_once_with(lote_orm)
    db_mock.commit.assert_called_once()


def test_cancelar_lote_de_outro_mercado_levanta_nao_encontrado(db_mock):
    db_mock.get.return_value = _lote(id_mercado=OUTRO_MERCADO)

    with pytest.raises(LoteNaoEncontrado):
        lote_service.cancelar(db_mock, ID_MERCADO, ID_LOTE)
    db_mock.delete.assert_not_called()


def test_cancelar_lote_confirmado_levanta_acao_invalida(db_mock):
    db_mock.get.return_value = _lote(status=StatusLote.CONFIRMADO)

    with pytest.raises(AcaoInvalidaParaStatus):
        lote_service.cancelar(db_mock, ID_MERCADO, ID_LOTE)
    db_mock.delete.assert_not_called()


# --- historico_do_lote ---------------------------------------------------


def test_historico_do_lote_retorna_lista(db_mock):
    db_mock.get.return_value = _lote()
    db_mock.query.return_value.filter.return_value.order_by.return_value.all.return_value = [
        HistoricoAcaoORM(
            id=1,
            id_mercado=ID_MERCADO,
            id_lote=ID_LOTE,
            tipo_acao=TipoAcao.CADASTRO,
            descricao="Lote criado.",
            origem=OrigemAcao.USUARIO,
            data_hora=datetime.now(),
        )
    ]

    historico = lote_service.historico_do_lote(db_mock, ID_MERCADO, ID_LOTE)

    assert len(historico) == 1
    assert historico[0].tipo_acao == TipoAcao.CADASTRO


def test_historico_do_lote_inexistente_levanta_nao_encontrado(db_mock):
    db_mock.get.return_value = None

    with pytest.raises(LoteNaoEncontrado):
        lote_service.historico_do_lote(db_mock, ID_MERCADO, ID_LOTE)


def test_historico_do_lote_de_outro_mercado_levanta_nao_encontrado(db_mock):
    db_mock.get.return_value = _lote(id_mercado=OUTRO_MERCADO)

    with pytest.raises(LoteNaoEncontrado):
        lote_service.historico_do_lote(db_mock, ID_MERCADO, ID_LOTE)
    db_mock.query.assert_not_called()
