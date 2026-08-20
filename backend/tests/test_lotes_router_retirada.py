"""Testes de POST /lotes/{id_lote}/retirada via TestClient.

`get_db` é sobrescrito com uma Session mockada (unittest.mock) — nenhum
teste aqui conecta a nenhum banco, real ou em memória. A dependency de
autenticação (`obter_id_mercado_atual`) roda de verdade, contra um
mapeamento de chaves de teste, não o real (configurado só via variável de
ambiente MERCADO_API_KEYS)."""

from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.core.database import get_db
from app.main import app
from app.models.lote import LoteORM
from app.schemas.enums import StatusLote

ID_MERCADO = 5
ID_LOTE = 1
CHAVE_VALIDA = "chave-teste-mercado-5"
HEADER_VALIDO = {"X-Mercado-Api-Key": CHAVE_VALIDA}
VENCIDO = date.today() - timedelta(days=1)
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


@pytest.fixture
def db_mock():
    db = MagicMock()

    def _fake_refresh(obj):
        # Simula o banco atribuindo o PK no INSERT real.
        if getattr(obj, "id", None) is None:
            obj.id = 999

    db.refresh.side_effect = _fake_refresh
    app.dependency_overrides[get_db] = lambda: db
    yield db
    app.dependency_overrides.pop(get_db, None)


@pytest.fixture
def chaves_de_teste():
    originais = settings.mercado_api_keys
    settings.mercado_api_keys = {CHAVE_VALIDA: ID_MERCADO}
    yield
    settings.mercado_api_keys = originais


@pytest.fixture
def client(db_mock, chaves_de_teste):
    return TestClient(app)


def test_retirada_parcial_retorna_201(client, db_mock):
    db_mock.get.return_value = _lote_confirmado("disponivel", Decimal("10"), data_validade=VENCIDO)

    resposta = client.post(
        f"/lotes/{ID_LOTE}/retirada", json={"quantidade": 3}, headers=HEADER_VALIDO
    )

    assert resposta.status_code == 201
    corpo = resposta.json()
    assert Decimal(str(corpo["quantidade_anterior"])) == Decimal("10")
    assert Decimal(str(corpo["quantidade_movimentada"])) == Decimal("3")
    assert Decimal(str(corpo["quantidade_resultante"])) == Decimal("7")
    assert corpo["tipo_movimentacao"] == "retirada"
    db_mock.commit.assert_called_once()


def test_retirada_total_retorna_201_e_saldo_zero(client, db_mock):
    db_mock.get.return_value = _lote_confirmado("disponivel", Decimal("5"), data_validade=VENCIDO)

    resposta = client.post(
        f"/lotes/{ID_LOTE}/retirada", json={"quantidade": 5}, headers=HEADER_VALIDO
    )

    assert resposta.status_code == 201
    corpo = resposta.json()
    assert Decimal(str(corpo["quantidade_resultante"])) == Decimal("0")


def test_sem_header_retorna_401(client, db_mock):
    resposta = client.post(f"/lotes/{ID_LOTE}/retirada", json={"quantidade": 3})

    assert resposta.status_code == 401
    db_mock.get.assert_not_called()


def test_chave_invalida_retorna_401(client, db_mock):
    resposta = client.post(
        f"/lotes/{ID_LOTE}/retirada",
        json={"quantidade": 3},
        headers={"X-Mercado-Api-Key": "chave-errada"},
    )

    assert resposta.status_code == 401
    db_mock.get.assert_not_called()


def test_lote_nao_encontrado_retorna_404(client, db_mock):
    db_mock.get.return_value = None

    resposta = client.post(
        f"/lotes/{ID_LOTE}/retirada", json={"quantidade": 3}, headers=HEADER_VALIDO
    )

    assert resposta.status_code == 404


def test_lote_de_outro_mercado_retorna_404(client, db_mock):
    db_mock.get.return_value = _lote_confirmado(
        "disponivel", Decimal("10"), data_validade=VENCIDO, id_mercado=ID_MERCADO + 1
    )

    resposta = client.post(
        f"/lotes/{ID_LOTE}/retirada", json={"quantidade": 3}, headers=HEADER_VALIDO
    )

    assert resposta.status_code == 404


def test_lote_nao_confirmado_retorna_409(client, db_mock):
    db_mock.get.return_value = _lote(
        StatusLote.PENDENTE_CONFIRMACAO, "disponivel", Decimal("10"), data_validade=VENCIDO
    )

    resposta = client.post(
        f"/lotes/{ID_LOTE}/retirada", json={"quantidade": 3}, headers=HEADER_VALIDO
    )

    assert resposta.status_code == 409


def test_lote_nao_vencido_retorna_409(client, db_mock):
    db_mock.get.return_value = _lote_confirmado(
        "disponivel", Decimal("10"), data_validade=NAO_VENCIDO
    )

    resposta = client.post(
        f"/lotes/{ID_LOTE}/retirada", json={"quantidade": 3}, headers=HEADER_VALIDO
    )

    assert resposta.status_code == 409


def test_saldo_insuficiente_retorna_409(client, db_mock):
    db_mock.get.return_value = _lote_confirmado("disponivel", Decimal("2"), data_validade=VENCIDO)

    resposta = client.post(
        f"/lotes/{ID_LOTE}/retirada", json={"quantidade": 9}, headers=HEADER_VALIDO
    )

    assert resposta.status_code == 409


@pytest.mark.parametrize("quantidade_invalida", [0, -1])
def test_quantidade_invalida_retorna_422(client, db_mock, quantidade_invalida):
    resposta = client.post(
        f"/lotes/{ID_LOTE}/retirada",
        json={"quantidade": quantidade_invalida},
        headers=HEADER_VALIDO,
    )

    assert resposta.status_code == 422
    db_mock.get.assert_not_called()


def test_id_mercado_em_query_string_e_ignorado(client, db_mock):
    # O lote pertence ao mercado do header (ID_MERCADO); um id_mercado
    # diferente na query string não pode influenciar a decisão.
    db_mock.get.return_value = _lote_confirmado(
        "disponivel", Decimal("10"), data_validade=VENCIDO, id_mercado=ID_MERCADO
    )

    resposta = client.post(
        f"/lotes/{ID_LOTE}/retirada?id_mercado=999999",
        json={"quantidade": 3},
        headers=HEADER_VALIDO,
    )

    assert resposta.status_code == 201  # continua valendo o id_mercado do header


def test_excecao_inesperada_propaga_como_500(db_mock, chaves_de_teste):
    db_mock.get.return_value = _lote_confirmado("disponivel", Decimal("10"), data_validade=VENCIDO)
    db_mock.commit.side_effect = RuntimeError("falha inesperada simulada")

    # raise_server_exceptions=False: sem isso o TestClient relança a
    # exceção no processo de teste em vez de devolver a resposta 500 —
    # aqui queremos verificar a resposta HTTP, não o traceback.
    client_sem_relancar = TestClient(app, raise_server_exceptions=False)

    resposta = client_sem_relancar.post(
        f"/lotes/{ID_LOTE}/retirada", json={"quantidade": 3}, headers=HEADER_VALIDO
    )

    assert resposta.status_code == 500
    db_mock.rollback.assert_called_once()
