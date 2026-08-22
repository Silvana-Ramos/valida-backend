"""Testes de POST/GET/PATCH /usuarios via TestClient.

`get_db` é sobrescrito com uma Session mockada (unittest.mock) — nenhum
teste aqui conecta a nenhum banco, real ou em memória. A dependency de
autenticação (`obter_id_mercado_atual`) roda de verdade, contra um
mapeamento de chaves de teste, não o real (configurado só via variável de
ambiente MERCADO_API_KEYS)."""

from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import IntegrityError

from app.core.config import settings
from app.core.database import get_db
from app.main import app
from app.models.usuario import UsuarioORM
from app.schemas.usuario import PapelUsuario

ID_MERCADO = 5
ID_USUARIO = 1
CHAVE_VALIDA = "chave-teste-mercado-5"
HEADER_VALIDO = {"X-Mercado-Api-Key": CHAVE_VALIDA}


def _usuario(
    id_usuario: int = ID_USUARIO,
    id_mercado: int = ID_MERCADO,
    telefone_whatsapp: str = "5511988880000",
    nome: str = "Maria",
    papel: PapelUsuario = PapelUsuario.DONO,
) -> UsuarioORM:
    return UsuarioORM(
        id=id_usuario,
        id_mercado=id_mercado,
        telefone_whatsapp=telefone_whatsapp,
        nome=nome,
        papel=papel,
    )


@pytest.fixture
def db_mock():
    db = MagicMock()

    def refresh_side_effect(obj):
        # Simula o banco atribuindo o PK no INSERT real.
        if getattr(obj, "id", None) is None:
            obj.id = 999

    db.refresh.side_effect = refresh_side_effect
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


# --- autenticação ---------------------------------------------------------


def test_post_sem_header_retorna_401(client, db_mock):
    resposta = client.post(
        "/usuarios",
        json={"telefone_whatsapp": "5511988880000", "nome": "Maria", "papel": "dono"},
    )

    assert resposta.status_code == 401
    db_mock.add.assert_not_called()


def test_post_chave_invalida_retorna_401(client, db_mock):
    resposta = client.post(
        "/usuarios",
        json={"telefone_whatsapp": "5511988880000", "nome": "Maria", "papel": "dono"},
        headers={"X-Mercado-Api-Key": "chave-errada"},
    )

    assert resposta.status_code == 401
    db_mock.add.assert_not_called()


def test_get_lista_sem_header_retorna_401(client, db_mock):
    resposta = client.get("/usuarios")

    assert resposta.status_code == 401
    db_mock.query.assert_not_called()


# --- criação ---------------------------------------------------------------


def test_criar_usuario_retorna_201(client, db_mock):
    resposta = client.post(
        "/usuarios",
        json={"telefone_whatsapp": "5511988880000", "nome": "Maria", "papel": "dono"},
        headers=HEADER_VALIDO,
    )

    assert resposta.status_code == 201
    corpo = resposta.json()
    assert corpo["telefone_whatsapp"] == "5511988880000"
    assert corpo["nome"] == "Maria"
    assert corpo["papel"] == "dono"
    assert corpo["id_mercado"] == ID_MERCADO
    db_mock.add.assert_called_once()
    db_mock.commit.assert_called_once()


def test_criar_usuario_telefone_duplicado_retorna_409(client, db_mock):
    db_mock.commit.side_effect = IntegrityError("stmt", {}, Exception("duplicidade"))

    resposta = client.post(
        "/usuarios",
        json={"telefone_whatsapp": "5511988880000", "nome": "Maria", "papel": "dono"},
        headers=HEADER_VALIDO,
    )

    assert resposta.status_code == 409
    db_mock.rollback.assert_called_once()


def test_criar_usuario_telefone_invalido_retorna_422(client, db_mock):
    resposta = client.post(
        "/usuarios",
        json={"telefone_whatsapp": "988880000", "nome": "Maria", "papel": "dono"},  # sem DDI
        headers=HEADER_VALIDO,
    )

    assert resposta.status_code == 422
    db_mock.add.assert_not_called()


def test_criar_usuario_telefone_com_formatacao_e_normalizado(client, db_mock):
    resposta = client.post(
        "/usuarios",
        json={"telefone_whatsapp": "+55 11 98888-0000", "nome": "Maria", "papel": "dono"},
        headers=HEADER_VALIDO,
    )

    assert resposta.status_code == 201
    assert resposta.json()["telefone_whatsapp"] == "5511988880000"


# --- listagem ----------------------------------------------------------


def test_listar_usuarios_retorna_200(client, db_mock):
    db_mock.query.return_value.filter.return_value.all.return_value = [
        _usuario(id_usuario=1, nome="Maria"),
        _usuario(id_usuario=2, nome="João", telefone_whatsapp="5511988880001"),
    ]

    resposta = client.get("/usuarios", headers=HEADER_VALIDO)

    assert resposta.status_code == 200
    corpo = resposta.json()
    assert len(corpo) == 2
    assert {u["nome"] for u in corpo} == {"Maria", "João"}


def test_listar_usuarios_vazio_retorna_200(client, db_mock):
    db_mock.query.return_value.filter.return_value.all.return_value = []

    resposta = client.get("/usuarios", headers=HEADER_VALIDO)

    assert resposta.status_code == 200
    assert resposta.json() == []


# --- consulta ------------------------------------------------------------


def test_obter_usuario_retorna_200(client, db_mock):
    db_mock.get.return_value = _usuario()

    resposta = client.get(f"/usuarios/{ID_USUARIO}", headers=HEADER_VALIDO)

    assert resposta.status_code == 200
    assert resposta.json()["id"] == ID_USUARIO


def test_obter_usuario_nao_encontrado_retorna_404(client, db_mock):
    db_mock.get.return_value = None

    resposta = client.get(f"/usuarios/{ID_USUARIO}", headers=HEADER_VALIDO)

    assert resposta.status_code == 404


def test_obter_usuario_de_outro_mercado_retorna_404(client, db_mock):
    db_mock.get.return_value = _usuario(id_mercado=ID_MERCADO + 1)

    resposta = client.get(f"/usuarios/{ID_USUARIO}", headers=HEADER_VALIDO)

    assert resposta.status_code == 404


# --- atualização -----------------------------------------------------------


def test_atualizar_usuario_retorna_200(client, db_mock):
    db_mock.get.return_value = _usuario()

    resposta = client.patch(
        f"/usuarios/{ID_USUARIO}",
        json={"nome": "Novo Nome", "papel": "funcionario"},
        headers=HEADER_VALIDO,
    )

    assert resposta.status_code == 200
    corpo = resposta.json()
    assert corpo["nome"] == "Novo Nome"
    assert corpo["papel"] == "funcionario"
    db_mock.commit.assert_called_once()


def test_atualizar_usuario_nao_encontrado_retorna_404(client, db_mock):
    db_mock.get.return_value = None

    resposta = client.patch(
        f"/usuarios/{ID_USUARIO}", json={"nome": "Novo Nome"}, headers=HEADER_VALIDO
    )

    assert resposta.status_code == 404
    db_mock.commit.assert_not_called()


def test_atualizar_usuario_de_outro_mercado_retorna_404(client, db_mock):
    db_mock.get.return_value = _usuario(id_mercado=ID_MERCADO + 1)

    resposta = client.patch(
        f"/usuarios/{ID_USUARIO}", json={"nome": "Novo Nome"}, headers=HEADER_VALIDO
    )

    assert resposta.status_code == 404
    db_mock.commit.assert_not_called()


def test_atualizar_usuario_telefone_duplicado_retorna_409(client, db_mock):
    db_mock.get.return_value = _usuario()
    db_mock.commit.side_effect = IntegrityError("stmt", {}, Exception("duplicidade"))

    resposta = client.patch(
        f"/usuarios/{ID_USUARIO}",
        json={"telefone_whatsapp": "5511988880009"},
        headers=HEADER_VALIDO,
    )

    assert resposta.status_code == 409
    db_mock.rollback.assert_called_once()


def test_atualizar_usuario_telefone_invalido_retorna_422(client, db_mock):
    db_mock.get.return_value = _usuario()

    resposta = client.patch(
        f"/usuarios/{ID_USUARIO}",
        json={"telefone_whatsapp": "988880009"},  # sem DDI
        headers=HEADER_VALIDO,
    )

    assert resposta.status_code == 422
    db_mock.commit.assert_not_called()
