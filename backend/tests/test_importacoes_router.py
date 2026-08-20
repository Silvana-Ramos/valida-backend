"""Testes de POST/GET /importacoes via TestClient.

`get_db` é sobrescrito com uma Session mockada (unittest.mock) — nenhum
teste aqui conecta a nenhum banco, real ou em memória. A dependency de
autenticação (`obter_id_mercado_atual`) roda de verdade, contra um
mapeamento de chaves de teste, não o real (configurado só via variável de
ambiente MERCADO_API_KEYS)."""

from datetime import date, datetime, timedelta
from decimal import Decimal
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.core.database import get_db
from app.main import app
from app.models.importacao import ImportacaoORM
from app.models.item_importacao import ItemImportacaoORM
from app.models.lote import LoteORM
from app.models.produto import ProdutoORM
from app.schemas.enums import StatusLote
from app.schemas.importacao import StatusImportacao, StatusProcessamentoItem
from app.schemas.produto import CategoriaProduto, UnidadeMedida

ID_MERCADO = 5
CHAVE_VALIDA = "chave-teste-mercado-5"
HEADER_VALIDO = {"X-Mercado-Api-Key": CHAVE_VALIDA}
NAO_VENCIDO = date.today() + timedelta(days=10)

CSV_UMA_LINHA = (
    b"referencia_externa,produto,numero_lote,quantidade\r\n"
    b"ref-1,COD-1,,3\r\n"
)


def _produto() -> ProdutoORM:
    return ProdutoORM(
        id=10,
        id_mercado=ID_MERCADO,
        nome="Pao Frances",
        categoria=CategoriaProduto.PADARIA,
        unidade_medida=UnidadeMedida.KG,
        codigo_sistema_origem="COD-1",
        codigo_barras="7891234567890",
    )


def _lote(saldo: Decimal) -> LoteORM:
    return LoteORM(
        id=20,
        id_mercado=ID_MERCADO,
        id_produto=10,
        status=StatusLote.CONFIRMADO,
        status_operacional="disponivel",
        quantidade_disponivel=saldo,
        quantidade_inicial=saldo,
        data_validade=NAO_VENCIDO,
        numero_lote=None,
    )


@pytest.fixture
def db_mock():
    db = MagicMock()

    produto_q = MagicMock()
    produto_q.filter.return_value.first.return_value = None
    lote_q = MagicMock()
    lote_q.filter.return_value.all.return_value = []
    lote_q.filter.return_value.order_by.return_value.all.return_value = []
    importacao_q = MagicMock()
    importacao_q.filter.return_value.first.return_value = None
    item_q = MagicMock()
    item_q.filter.return_value.first.return_value = None
    item_q.filter.return_value.order_by.return_value.all.return_value = []

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
    db.importacao_por_get = None  # usado por obter_importacao/listar_itens (db.get direto)

    def get_side_effect(model, ident, **kwargs):
        if model is LoteORM:
            candidatos = (
                list(lote_q.filter.return_value.all.return_value)
                + list(lote_q.filter.return_value.order_by.return_value.all.return_value)
            )
            for candidato in candidatos:
                if candidato.id == ident:
                    return candidato
            return None
        if model is ImportacaoORM:
            return db.importacao_por_get
        return None

    db.get.side_effect = get_side_effect

    def refresh_side_effect(obj):
        # Simula o banco atribuindo o PK e o server_default de
        # data_hora_inicio no INSERT real, já que aqui não há nenhuma
        # conexão de fato.
        if getattr(obj, "id", None) is None:
            obj.id = 999
        if hasattr(obj, "data_hora_inicio") and obj.data_hora_inicio is None:
            obj.data_hora_inicio = datetime.now()

    db.refresh.side_effect = refresh_side_effect
    app.dependency_overrides[get_db] = lambda: db
    yield db
    app.dependency_overrides.pop(get_db, None)


def _definir_lotes(db: MagicMock, lotes: list[LoteORM]) -> None:
    db.lote_q.filter.return_value.all.return_value = lotes
    db.lote_q.filter.return_value.order_by.return_value.all.return_value = lotes


@pytest.fixture
def chaves_de_teste():
    originais = settings.mercado_api_keys
    settings.mercado_api_keys = {CHAVE_VALIDA: ID_MERCADO}
    yield
    settings.mercado_api_keys = originais


@pytest.fixture
def client(db_mock, chaves_de_teste):
    return TestClient(app)


def test_upload_bem_sucedido_retorna_201(client, db_mock):
    db_mock.produto_q.filter.return_value.first.return_value = _produto()
    _definir_lotes(db_mock, [_lote(Decimal("10"))])

    resposta = client.post(
        "/importacoes",
        files={"arquivo": ("vendas.csv", CSV_UMA_LINHA, "text/csv")},
        headers=HEADER_VALIDO,
    )

    assert resposta.status_code == 201
    corpo = resposta.json()
    assert corpo["status"] == "concluida"
    assert corpo["total_processadas"] == 1
    assert corpo["total_com_erro"] == 0
    assert corpo["id_mercado"] == ID_MERCADO


def test_upload_com_erro_de_linha_retorna_201_concluida_com_erros(client, db_mock):
    # produto_q.first() -> None sempre: produto não encontrado
    resposta = client.post(
        "/importacoes",
        files={"arquivo": ("vendas.csv", CSV_UMA_LINHA, "text/csv")},
        headers=HEADER_VALIDO,
    )

    assert resposta.status_code == 201
    corpo = resposta.json()
    assert corpo["status"] == "concluida_com_erros"
    assert corpo["total_com_erro"] == 1


def test_arquivo_ja_processado_retorna_409(client, db_mock):
    db_mock.importacao_q.filter.return_value.first.return_value = ImportacaoORM(id=1)

    resposta = client.post(
        "/importacoes",
        files={"arquivo": ("vendas.csv", CSV_UMA_LINHA, "text/csv")},
        headers=HEADER_VALIDO,
    )

    assert resposta.status_code == 409


def test_arquivo_invalido_retorna_422(client, db_mock):
    resposta = client.post(
        "/importacoes",
        files={"arquivo": ("vendas.csv", b"col1,col2\r\nx,y\r\n", "text/csv")},
        headers=HEADER_VALIDO,
    )

    assert resposta.status_code == 422


def test_sem_header_retorna_401(client, db_mock):
    resposta = client.post(
        "/importacoes", files={"arquivo": ("vendas.csv", CSV_UMA_LINHA, "text/csv")}
    )

    assert resposta.status_code == 401
    db_mock.query.assert_not_called()


def test_chave_invalida_retorna_401(client, db_mock):
    resposta = client.post(
        "/importacoes",
        files={"arquivo": ("vendas.csv", CSV_UMA_LINHA, "text/csv")},
        headers={"X-Mercado-Api-Key": "chave-errada"},
    )

    assert resposta.status_code == 401


def test_id_mercado_em_query_string_e_ignorado(client, db_mock):
    db_mock.produto_q.filter.return_value.first.return_value = _produto()
    _definir_lotes(db_mock, [_lote(Decimal("10"))])

    resposta = client.post(
        "/importacoes?id_mercado=999999",
        files={"arquivo": ("vendas.csv", CSV_UMA_LINHA, "text/csv")},
        headers=HEADER_VALIDO,
    )

    assert resposta.status_code == 201
    assert resposta.json()["id_mercado"] == ID_MERCADO  # continua valendo o do header


def test_excecao_inesperada_no_upload_propaga_como_500(db_mock, chaves_de_teste):
    db_mock.produto_q.filter.return_value.first.side_effect = RuntimeError(
        "falha inesperada simulada"
    )

    client_sem_relancar = TestClient(app, raise_server_exceptions=False)
    resposta = client_sem_relancar.post(
        "/importacoes",
        files={"arquivo": ("vendas.csv", CSV_UMA_LINHA, "text/csv")},
        headers=HEADER_VALIDO,
    )

    assert resposta.status_code == 500


def test_get_importacao_retorna_200(client, db_mock):
    db_mock.importacao_por_get = ImportacaoORM(
        id=1,
        id_mercado=ID_MERCADO,
        nome_arquivo="vendas.csv",
        hash_arquivo="abc",
        status=StatusImportacao.CONCLUIDA,
        total_linhas=1,
        total_processadas=1,
        total_duplicadas=0,
        total_com_erro=0,
        data_hora_inicio=datetime.now(),
    )

    resposta = client.get("/importacoes/1", headers=HEADER_VALIDO)

    assert resposta.status_code == 200
    assert resposta.json()["id"] == 1


def test_get_importacao_nao_encontrada_retorna_404(client, db_mock):
    db_mock.importacao_por_get = None

    resposta = client.get("/importacoes/999", headers=HEADER_VALIDO)

    assert resposta.status_code == 404


def test_get_importacao_de_outro_mercado_retorna_404(client, db_mock):
    db_mock.importacao_por_get = ImportacaoORM(
        id=1,
        id_mercado=ID_MERCADO + 1,
        nome_arquivo="vendas.csv",
        hash_arquivo="abc",
        status=StatusImportacao.CONCLUIDA,
        total_processadas=0,
        total_duplicadas=0,
        total_com_erro=0,
    )

    resposta = client.get("/importacoes/1", headers=HEADER_VALIDO)

    assert resposta.status_code == 404


def test_get_itens_retorna_lista(client, db_mock):
    db_mock.importacao_por_get = ImportacaoORM(
        id=1,
        id_mercado=ID_MERCADO,
        nome_arquivo="vendas.csv",
        hash_arquivo="abc",
        status=StatusImportacao.CONCLUIDA,
        total_processadas=1,
        total_duplicadas=0,
        total_com_erro=0,
    )
    db_mock.item_q.filter.return_value.order_by.return_value.all.return_value = [
        ItemImportacaoORM(
            id=1,
            id_importacao=1,
            id_mercado=ID_MERCADO,
            numero_linha=1,
            referencia_externa="ref-1",
            status_processamento=StatusProcessamentoItem.PROCESSADA,
            dados_brutos={"produto": "COD-1"},
        )
    ]

    resposta = client.get("/importacoes/1/itens", headers=HEADER_VALIDO)

    assert resposta.status_code == 200
    corpo = resposta.json()
    assert len(corpo) == 1
    assert corpo[0]["referencia_externa"] == "ref-1"


def test_get_itens_importacao_nao_encontrada_retorna_404(client, db_mock):
    db_mock.importacao_por_get = None

    resposta = client.get("/importacoes/999/itens", headers=HEADER_VALIDO)

    assert resposta.status_code == 404
