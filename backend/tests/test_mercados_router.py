"""Testes de POST/GET/PATCH /mercados via TestClient.

`get_db` é sobrescrito com uma Session mockada (unittest.mock) — nenhum
teste aqui conecta a nenhum banco, real ou em memória. A dependency de
autenticação (`obter_admin_autenticado`) roda de verdade, contra uma
`settings.admin_api_key` de teste, não a real (configurada só via
variável de ambiente ADMIN_API_KEY)."""

from datetime import datetime
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import IntegrityError

from app.core.config import settings
from app.core.database import get_db
from app.main import app
from app.models.mercado import MercadoORM
from app.schemas.mercado import SegmentoMercado, StatusMercado

CHAVE_ADMIN_VALIDA = "chave-teste-admin"
HEADER_ADMIN_VALIDO = {"X-Admin-Api-Key": CHAVE_ADMIN_VALIDA}
ID_MERCADO = 1


def _mercado(
    id_mercado: int = ID_MERCADO,
    nome: str = "Mercadinho da Esquina",
    telefone_whatsapp: str = "5511999990000",
    segmento: SegmentoMercado = SegmentoMercado.MERCEARIA,
    status: StatusMercado = StatusMercado.ATIVO,
) -> MercadoORM:
    return MercadoORM(
        id=id_mercado,
        nome=nome,
        telefone_whatsapp=telefone_whatsapp,
        segmento=segmento,
        status=status,
        data_cadastro=datetime.now(),
        relatorio_diario_ativo=False,
    )


@pytest.fixture
def db_mock():
    db = MagicMock()

    def refresh_side_effect(obj):
        # Simula o banco atribuindo o PK e os defaults de coluna (status,
        # relatorio_diario_ativo, data_cadastro) no INSERT real, já que
        # aqui não há nenhuma conexão de fato.
        if getattr(obj, "id", None) is None:
            obj.id = 999
        if getattr(obj, "status", None) is None:
            obj.status = StatusMercado.ATIVO
        if getattr(obj, "relatorio_diario_ativo", None) is None:
            obj.relatorio_diario_ativo = False
        if getattr(obj, "data_cadastro", None) is None:
            obj.data_cadastro = datetime.now()

    db.refresh.side_effect = refresh_side_effect
    app.dependency_overrides[get_db] = lambda: db
    yield db
    app.dependency_overrides.pop(get_db, None)


@pytest.fixture
def chave_admin_de_teste():
    original = settings.admin_api_key
    settings.admin_api_key = CHAVE_ADMIN_VALIDA
    yield
    settings.admin_api_key = original


@pytest.fixture
def client(db_mock, chave_admin_de_teste):
    return TestClient(app)


# --- autenticação ---------------------------------------------------------


def test_post_sem_header_retorna_401(client, db_mock):
    resposta = client.post(
        "/mercados",
        json={
            "nome": "Mercadinho da Esquina",
            "telefone_whatsapp": "5511999990000",
            "segmento": "mercearia",
        },
    )

    assert resposta.status_code == 401
    db_mock.add.assert_not_called()


def test_post_chave_invalida_retorna_401(client, db_mock):
    resposta = client.post(
        "/mercados",
        json={
            "nome": "Mercadinho da Esquina",
            "telefone_whatsapp": "5511999990000",
            "segmento": "mercearia",
        },
        headers={"X-Admin-Api-Key": "chave-errada"},
    )

    assert resposta.status_code == 401
    db_mock.add.assert_not_called()


def test_get_lista_sem_header_retorna_401(client, db_mock):
    # Confirma que a dependência admin protege o router inteiro, não só POST.
    resposta = client.get("/mercados")

    assert resposta.status_code == 401
    db_mock.query.assert_not_called()


def test_admin_api_key_nao_configurada_no_servidor_retorna_401(client, db_mock):
    settings.admin_api_key = None

    resposta = client.get("/mercados", headers=HEADER_ADMIN_VALIDO)

    assert resposta.status_code == 401


# --- criação ---------------------------------------------------------------


def test_criar_mercado_retorna_201(client, db_mock):
    resposta = client.post(
        "/mercados",
        json={
            "nome": "Mercadinho da Esquina",
            "telefone_whatsapp": "5511999990000",
            "segmento": "mercearia",
        },
        headers=HEADER_ADMIN_VALIDO,
    )

    assert resposta.status_code == 201
    corpo = resposta.json()
    assert corpo["nome"] == "Mercadinho da Esquina"
    assert corpo["telefone_whatsapp"] == "5511999990000"
    assert corpo["segmento"] == "mercearia"
    assert corpo["status"] == "ativo"
    db_mock.add.assert_called_once()
    db_mock.commit.assert_called_once()


def test_criar_mercado_telefone_duplicado_retorna_409(client, db_mock):
    db_mock.commit.side_effect = IntegrityError("stmt", {}, Exception("duplicidade"))

    resposta = client.post(
        "/mercados",
        json={
            "nome": "Mercadinho da Esquina",
            "telefone_whatsapp": "5511999990000",
            "segmento": "mercearia",
        },
        headers=HEADER_ADMIN_VALIDO,
    )

    assert resposta.status_code == 409
    db_mock.rollback.assert_called_once()


def test_criar_mercado_telefone_invalido_retorna_422(client, db_mock):
    resposta = client.post(
        "/mercados",
        json={
            "nome": "Mercadinho da Esquina",
            "telefone_whatsapp": "11999990000",  # sem DDI 55
            "segmento": "mercearia",
        },
        headers=HEADER_ADMIN_VALIDO,
    )

    assert resposta.status_code == 422
    db_mock.add.assert_not_called()


def test_criar_mercado_telefone_com_formatacao_e_normalizado(client, db_mock):
    resposta = client.post(
        "/mercados",
        json={
            "nome": "Mercadinho da Esquina",
            "telefone_whatsapp": "+55 11 99999-0000",
            "segmento": "mercearia",
        },
        headers=HEADER_ADMIN_VALIDO,
    )

    assert resposta.status_code == 201
    assert resposta.json()["telefone_whatsapp"] == "5511999990000"


# --- listagem ----------------------------------------------------------


def test_listar_mercados_retorna_200(client, db_mock):
    db_mock.query.return_value.all.return_value = [
        _mercado(id_mercado=1, nome="Mercadinho A"),
        _mercado(id_mercado=2, nome="Mercadinho B", telefone_whatsapp="5511999990001"),
    ]

    resposta = client.get("/mercados", headers=HEADER_ADMIN_VALIDO)

    assert resposta.status_code == 200
    corpo = resposta.json()
    assert len(corpo) == 2
    assert {m["nome"] for m in corpo} == {"Mercadinho A", "Mercadinho B"}


def test_listar_mercados_vazio_retorna_200(client, db_mock):
    db_mock.query.return_value.all.return_value = []

    resposta = client.get("/mercados", headers=HEADER_ADMIN_VALIDO)

    assert resposta.status_code == 200
    assert resposta.json() == []


# --- consulta ------------------------------------------------------------


def test_obter_mercado_retorna_200(client, db_mock):
    db_mock.get.return_value = _mercado()

    resposta = client.get(f"/mercados/{ID_MERCADO}", headers=HEADER_ADMIN_VALIDO)

    assert resposta.status_code == 200
    assert resposta.json()["id"] == ID_MERCADO


def test_obter_mercado_nao_encontrado_retorna_404(client, db_mock):
    db_mock.get.return_value = None

    resposta = client.get(f"/mercados/{ID_MERCADO}", headers=HEADER_ADMIN_VALIDO)

    assert resposta.status_code == 404


# --- atualização -----------------------------------------------------------


def test_atualizar_mercado_retorna_200(client, db_mock):
    db_mock.get.return_value = _mercado()

    resposta = client.patch(
        f"/mercados/{ID_MERCADO}",
        json={"nome": "Novo Nome", "status": "inativo"},
        headers=HEADER_ADMIN_VALIDO,
    )

    assert resposta.status_code == 200
    corpo = resposta.json()
    assert corpo["nome"] == "Novo Nome"
    assert corpo["status"] == "inativo"
    db_mock.commit.assert_called_once()


def test_atualizar_mercado_nao_encontrado_retorna_404(client, db_mock):
    db_mock.get.return_value = None

    resposta = client.patch(
        f"/mercados/{ID_MERCADO}",
        json={"nome": "Novo Nome"},
        headers=HEADER_ADMIN_VALIDO,
    )

    assert resposta.status_code == 404
    db_mock.commit.assert_not_called()


def test_atualizar_mercado_telefone_duplicado_retorna_409(client, db_mock):
    db_mock.get.return_value = _mercado()
    db_mock.commit.side_effect = IntegrityError("stmt", {}, Exception("duplicidade"))

    resposta = client.patch(
        f"/mercados/{ID_MERCADO}",
        json={"telefone_whatsapp": "5511999990009"},
        headers=HEADER_ADMIN_VALIDO,
    )

    assert resposta.status_code == 409
    db_mock.rollback.assert_called_once()


def test_atualizar_mercado_telefone_invalido_retorna_422(client, db_mock):
    db_mock.get.return_value = _mercado()

    resposta = client.patch(
        f"/mercados/{ID_MERCADO}",
        json={"telefone_whatsapp": "11999990009"},  # sem DDI 55
        headers=HEADER_ADMIN_VALIDO,
    )

    assert resposta.status_code == 422
    db_mock.commit.assert_not_called()


# --- bootstrap de usuário ------------------------------------------------


def test_bootstrap_usuario_sem_header_retorna_401(client, db_mock):
    resposta = client.post(
        f"/mercados/{ID_MERCADO}/usuarios",
        json={"telefone_whatsapp": "5511988880000", "nome": "Maria", "papel": "dono"},
    )

    assert resposta.status_code == 401
    db_mock.add.assert_not_called()


def test_bootstrap_usuario_chave_invalida_retorna_401(client, db_mock):
    resposta = client.post(
        f"/mercados/{ID_MERCADO}/usuarios",
        json={"telefone_whatsapp": "5511988880000", "nome": "Maria", "papel": "dono"},
        headers={"X-Admin-Api-Key": "chave-errada"},
    )

    assert resposta.status_code == 401
    db_mock.add.assert_not_called()


def test_bootstrap_usuario_retorna_201(client, db_mock):
    db_mock.get.return_value = _mercado()

    resposta = client.post(
        f"/mercados/{ID_MERCADO}/usuarios",
        json={"telefone_whatsapp": "5511988880000", "nome": "Maria", "papel": "dono"},
        headers=HEADER_ADMIN_VALIDO,
    )

    assert resposta.status_code == 201
    corpo = resposta.json()
    assert corpo["id_mercado"] == ID_MERCADO
    assert corpo["telefone_whatsapp"] == "5511988880000"
    assert corpo["nome"] == "Maria"
    assert corpo["papel"] == "dono"
    db_mock.add.assert_called_once()
    db_mock.commit.assert_called_once()


def test_bootstrap_usuario_mercado_nao_encontrado_retorna_404(client, db_mock):
    db_mock.get.return_value = None

    resposta = client.post(
        f"/mercados/{ID_MERCADO}/usuarios",
        json={"telefone_whatsapp": "5511988880000", "nome": "Maria", "papel": "dono"},
        headers=HEADER_ADMIN_VALIDO,
    )

    assert resposta.status_code == 404
    db_mock.add.assert_not_called()


def test_bootstrap_usuario_telefone_duplicado_retorna_409(client, db_mock):
    db_mock.get.return_value = _mercado()
    db_mock.commit.side_effect = IntegrityError("stmt", {}, Exception("duplicidade"))

    resposta = client.post(
        f"/mercados/{ID_MERCADO}/usuarios",
        json={"telefone_whatsapp": "5511988880000", "nome": "Maria", "papel": "dono"},
        headers=HEADER_ADMIN_VALIDO,
    )

    assert resposta.status_code == 409
    db_mock.rollback.assert_called_once()


def test_bootstrap_usuario_telefone_invalido_retorna_422(client, db_mock):
    db_mock.get.return_value = _mercado()

    resposta = client.post(
        f"/mercados/{ID_MERCADO}/usuarios",
        json={"telefone_whatsapp": "988880000", "nome": "Maria", "papel": "dono"},  # sem DDI
        headers=HEADER_ADMIN_VALIDO,
    )

    assert resposta.status_code == 422
    db_mock.add.assert_not_called()
