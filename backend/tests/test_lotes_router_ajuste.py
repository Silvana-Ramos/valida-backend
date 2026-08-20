"""Testes de POST /lotes/{id_lote}/ajuste via TestClient.

`get_db` é sobrescrito com uma Session mockada (unittest.mock) — nenhum
teste aqui conecta a nenhum banco, real ou em memória. A dependency de
autenticação (`obter_id_mercado_atual`) roda de verdade, contra um
mapeamento de chaves de teste, não o real (configurado só via variável de
ambiente MERCADO_API_KEYS)."""

from decimal import Decimal
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.core.database import get_db
from app.main import app
from app.models.lote import LoteORM
from app.models.movimentacao_estoque import MovimentacaoEstoqueORM
from app.schemas.enums import StatusLote

ID_MERCADO = 5
ID_LOTE = 1
ID_MOVIMENTACAO_ESTORNADA = 42
CHAVE_VALIDA = "chave-teste-mercado-5"
HEADER_VALIDO = {"X-Mercado-Api-Key": CHAVE_VALIDA}


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


@pytest.fixture
def db_mock():
    db = MagicMock()
    # Por padrão (sem estorno), qualquer db.get de MovimentacaoEstoqueORM
    # não é usado; testes que precisam dele configuram db.get.side_effect
    # explicitamente.
    db.query.return_value.filter.return_value.first.return_value = None

    def _fake_refresh(obj):
        # Simula o banco atribuindo o PK no INSERT real.
        if getattr(obj, "id", None) is None:
            obj.id = 999

    db.refresh.side_effect = _fake_refresh
    app.dependency_overrides[get_db] = lambda: db
    yield db
    app.dependency_overrides.pop(get_db, None)


def _configurar_lote(db_mock, lote_orm):
    db_mock.get.side_effect = lambda cls, ident, **kw: (
        lote_orm if cls is LoteORM else None
    )


def _configurar_lote_e_movimentacao_estornavel(db_mock, lote_orm, movimentacao_orm):
    db_mock.get.side_effect = lambda cls, ident, **kw: (
        lote_orm if cls is LoteORM else movimentacao_orm
    )


@pytest.fixture
def chaves_de_teste():
    originais = settings.mercado_api_keys
    settings.mercado_api_keys = {CHAVE_VALIDA: ID_MERCADO}
    yield
    settings.mercado_api_keys = originais


@pytest.fixture
def client(db_mock, chaves_de_teste):
    return TestClient(app)


def test_ajuste_entrada_retorna_201(client, db_mock):
    _configurar_lote(db_mock, _lote_confirmado("disponivel", Decimal("10")))

    resposta = client.post(
        f"/lotes/{ID_LOTE}/ajuste",
        json={"quantidade": 4, "sentido": "entrada"},
        headers=HEADER_VALIDO,
    )

    assert resposta.status_code == 201
    corpo = resposta.json()
    assert Decimal(str(corpo["quantidade_resultante"])) == Decimal("14")
    assert corpo["tipo_movimentacao"] == "ajuste"
    assert corpo["sentido"] == "entrada"
    db_mock.commit.assert_called_once()


def test_ajuste_saida_retorna_201(client, db_mock):
    _configurar_lote(db_mock, _lote_confirmado("disponivel", Decimal("10")))

    resposta = client.post(
        f"/lotes/{ID_LOTE}/ajuste",
        json={"quantidade": 3, "sentido": "saida"},
        headers=HEADER_VALIDO,
    )

    assert resposta.status_code == 201
    corpo = resposta.json()
    assert Decimal(str(corpo["quantidade_resultante"])) == Decimal("7")
    assert corpo["sentido"] == "saida"


def test_ajuste_entrada_reativa_lote_esgotado(client, db_mock):
    _configurar_lote(db_mock, _lote_confirmado("esgotado", Decimal("0")))

    resposta = client.post(
        f"/lotes/{ID_LOTE}/ajuste",
        json={"quantidade": 5, "sentido": "entrada"},
        headers=HEADER_VALIDO,
    )

    assert resposta.status_code == 201
    assert Decimal(str(resposta.json()["quantidade_resultante"])) == Decimal("5")


def test_ajuste_entrada_em_lote_descartado_retorna_409(client, db_mock):
    _configurar_lote(db_mock, _lote_confirmado("descartado", Decimal("0")))

    resposta = client.post(
        f"/lotes/{ID_LOTE}/ajuste",
        json={"quantidade": 5, "sentido": "entrada"},
        headers=HEADER_VALIDO,
    )

    assert resposta.status_code == 409


def test_ajuste_saida_saldo_insuficiente_retorna_409(client, db_mock):
    _configurar_lote(db_mock, _lote_confirmado("disponivel", Decimal("2")))

    resposta = client.post(
        f"/lotes/{ID_LOTE}/ajuste",
        json={"quantidade": 9, "sentido": "saida"},
        headers=HEADER_VALIDO,
    )

    assert resposta.status_code == 409


def test_sem_header_retorna_401(client, db_mock):
    resposta = client.post(
        f"/lotes/{ID_LOTE}/ajuste", json={"quantidade": 3, "sentido": "entrada"}
    )

    assert resposta.status_code == 401
    db_mock.get.assert_not_called()


def test_chave_invalida_retorna_401(client, db_mock):
    resposta = client.post(
        f"/lotes/{ID_LOTE}/ajuste",
        json={"quantidade": 3, "sentido": "entrada"},
        headers={"X-Mercado-Api-Key": "chave-errada"},
    )

    assert resposta.status_code == 401
    db_mock.get.assert_not_called()


def test_lote_nao_encontrado_retorna_404(client, db_mock):
    _configurar_lote(db_mock, None)

    resposta = client.post(
        f"/lotes/{ID_LOTE}/ajuste",
        json={"quantidade": 3, "sentido": "entrada"},
        headers=HEADER_VALIDO,
    )

    assert resposta.status_code == 404


def test_lote_de_outro_mercado_retorna_404(client, db_mock):
    _configurar_lote(
        db_mock, _lote_confirmado("disponivel", Decimal("10"), id_mercado=ID_MERCADO + 1)
    )

    resposta = client.post(
        f"/lotes/{ID_LOTE}/ajuste",
        json={"quantidade": 3, "sentido": "entrada"},
        headers=HEADER_VALIDO,
    )

    assert resposta.status_code == 404


def test_lote_nao_confirmado_retorna_409(client, db_mock):
    _configurar_lote(
        db_mock, _lote(StatusLote.PENDENTE_CONFIRMACAO, "disponivel", Decimal("10"))
    )

    resposta = client.post(
        f"/lotes/{ID_LOTE}/ajuste",
        json={"quantidade": 3, "sentido": "entrada"},
        headers=HEADER_VALIDO,
    )

    assert resposta.status_code == 409


@pytest.mark.parametrize("quantidade_invalida", [0, -1])
def test_quantidade_invalida_retorna_422(client, db_mock, quantidade_invalida):
    resposta = client.post(
        f"/lotes/{ID_LOTE}/ajuste",
        json={"quantidade": quantidade_invalida, "sentido": "entrada"},
        headers=HEADER_VALIDO,
    )

    assert resposta.status_code == 422
    db_mock.get.assert_not_called()


def test_sentido_invalido_retorna_422(client, db_mock):
    resposta = client.post(
        f"/lotes/{ID_LOTE}/ajuste",
        json={"quantidade": 3, "sentido": "lateral"},
        headers=HEADER_VALIDO,
    )

    assert resposta.status_code == 422
    db_mock.get.assert_not_called()


def test_estorno_movimentacao_nao_encontrada_retorna_404(client, db_mock):
    _configurar_lote_e_movimentacao_estornavel(
        db_mock, _lote_confirmado("disponivel", Decimal("10")), None
    )

    resposta = client.post(
        f"/lotes/{ID_LOTE}/ajuste",
        json={
            "quantidade": 3,
            "sentido": "entrada",
            "id_movimentacao_estornada": ID_MOVIMENTACAO_ESTORNADA,
        },
        headers=HEADER_VALIDO,
    )

    assert resposta.status_code == 404


def test_duplo_estorno_retorna_409(client, db_mock):
    _configurar_lote_e_movimentacao_estornavel(
        db_mock, _lote_confirmado("disponivel", Decimal("10")), _movimentacao_estornavel()
    )
    db_mock.query.return_value.filter.return_value.first.return_value = MovimentacaoEstoqueORM(
        id=100
    )

    resposta = client.post(
        f"/lotes/{ID_LOTE}/ajuste",
        json={
            "quantidade": 3,
            "sentido": "entrada",
            "id_movimentacao_estornada": ID_MOVIMENTACAO_ESTORNADA,
        },
        headers=HEADER_VALIDO,
    )

    assert resposta.status_code == 409


def test_estorno_valido_retorna_201_com_id_movimentacao_estornada(client, db_mock):
    _configurar_lote_e_movimentacao_estornavel(
        db_mock, _lote_confirmado("disponivel", Decimal("10")), _movimentacao_estornavel()
    )

    resposta = client.post(
        f"/lotes/{ID_LOTE}/ajuste",
        json={
            "quantidade": 2,
            "sentido": "saida",
            "id_movimentacao_estornada": ID_MOVIMENTACAO_ESTORNADA,
        },
        headers=HEADER_VALIDO,
    )

    assert resposta.status_code == 201
    assert resposta.json()["id_movimentacao_estornada"] == ID_MOVIMENTACAO_ESTORNADA


def test_id_mercado_em_query_string_e_ignorado(client, db_mock):
    _configurar_lote(db_mock, _lote_confirmado("disponivel", Decimal("10"), id_mercado=ID_MERCADO))

    resposta = client.post(
        f"/lotes/{ID_LOTE}/ajuste?id_mercado=999999",
        json={"quantidade": 3, "sentido": "entrada"},
        headers=HEADER_VALIDO,
    )

    assert resposta.status_code == 201  # continua valendo o id_mercado do header


def test_excecao_inesperada_propaga_como_500(db_mock, chaves_de_teste):
    _configurar_lote(db_mock, _lote_confirmado("disponivel", Decimal("10")))
    db_mock.commit.side_effect = RuntimeError("falha inesperada simulada")

    # raise_server_exceptions=False: sem isso o TestClient relança a
    # exceção no processo de teste em vez de devolver a resposta 500 —
    # aqui queremos verificar a resposta HTTP, não o traceback.
    client_sem_relancar = TestClient(app, raise_server_exceptions=False)

    resposta = client_sem_relancar.post(
        f"/lotes/{ID_LOTE}/ajuste",
        json={"quantidade": 3, "sentido": "entrada"},
        headers=HEADER_VALIDO,
    )

    assert resposta.status_code == 500
    db_mock.rollback.assert_called_once()
