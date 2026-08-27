"""Testes de app/services/whatsapp_webhook_service.py — Session mockada
(nenhum banco real) e `enviar_mensagem_texto` sempre mockado (nenhuma
chamada de rede real). Cobre o fluxo guiado por menu ponta a ponta:
resolução de usuário por telefone, cada estado da sessão de conversa, e
os quatro comandos do menu principal."""

from datetime import date, datetime, timedelta
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

from app.models.lote import LoteORM
from app.models.produto import ProdutoORM
from app.models.sessao_conversa import SessaoConversaORM
from app.models.usuario import UsuarioORM
from app.schemas.enums import NivelRisco, OrigemCadastro, StatusLote
from app.schemas.produto import CategoriaProduto, UnidadeMedida
from app.schemas.usuario import PapelUsuario
from app.services import whatsapp_webhook_service as webhook_service

ID_MERCADO = 5
ID_USUARIO = 1
TELEFONE = "5511999998888"
NAO_VENCIDO = date.today() + timedelta(days=20)
VENCENDO_LOGO = date.today() + timedelta(days=2)


def _usuario_orm() -> UsuarioORM:
    return UsuarioORM(
        id=ID_USUARIO,
        id_mercado=ID_MERCADO,
        telefone_whatsapp=TELEFONE,
        nome="Maria",
        papel=PapelUsuario.DONO,
    )


def _produto_orm(id_produto: int = 10, nome: str = "Pão Francês") -> ProdutoORM:
    return ProdutoORM(
        id=id_produto,
        id_mercado=ID_MERCADO,
        nome=nome,
        categoria=CategoriaProduto.PADARIA,
        unidade_medida=UnidadeMedida.KG,
    )


def _lote_orm(
    id_lote: int,
    id_produto: int = 10,
    status: StatusLote = StatusLote.CONFIRMADO,
    nivel_risco: NivelRisco = NivelRisco.URGENTE,
    data_validade: date = VENCENDO_LOGO,
    quantidade: Decimal = Decimal("10"),
    status_operacional: str = "disponivel",
) -> LoteORM:
    return LoteORM(
        id=id_lote,
        id_mercado=ID_MERCADO,
        id_produto=id_produto,
        quantidade=quantidade,
        numero_lote=None,
        data_validade=data_validade,
        data_entrada=datetime.now(),
        origem_cadastro=OrigemCadastro.TEXTO,
        status=status,
        nivel_risco=nivel_risco,
        dias_restantes=(data_validade - date.today()).days,
        data_ultima_atualizacao=datetime.now(),
        criado_por=None,
        preco_custo=None,
        status_operacional=status_operacional,
        quantidade_disponivel=quantidade,
        quantidade_inicial=quantidade,
    )


def _payload(telefone: str, texto: str) -> dict:
    return {
        "entry": [
            {
                "changes": [
                    {
                        "value": {
                            "messages": [
                                {"from": telefone, "type": "text", "text": {"body": texto}}
                            ]
                        }
                    }
                ]
            }
        ]
    }


@pytest.fixture
def db_mock():
    db = MagicMock()

    usuario_q = MagicMock()
    usuario_q.filter.return_value.first.return_value = _usuario_orm()
    lote_q = MagicMock()
    lote_q.filter.return_value.all.return_value = []
    lote_q.filter.return_value.filter.return_value.all.return_value = []
    produto_q = MagicMock()
    produto_q.filter.return_value.all.return_value = []
    produto_q.filter.return_value.first.return_value = None  # produto novo por padrão

    def query_side_effect(model):
        return {UsuarioORM: usuario_q, LoteORM: lote_q, ProdutoORM: produto_q}.get(
            model, MagicMock()
        )

    db.query.side_effect = query_side_effect
    db.usuario_q = usuario_q
    db.lote_q = lote_q
    db.produto_q = produto_q
    db.sessoes = {}

    def get_side_effect(model, ident, **kwargs):
        if model is SessaoConversaORM:
            return db.sessoes.get(ident)
        if model is LoteORM:
            candidatos = list(lote_q.filter.return_value.all.return_value) + list(
                lote_q.filter.return_value.filter.return_value.all.return_value
            )
            for candidato in candidatos:
                if candidato.id == ident:
                    return candidato
            return None
        return None

    db.get.side_effect = get_side_effect

    def add_side_effect(obj):
        if isinstance(obj, SessaoConversaORM):
            db.sessoes[obj.id_usuario] = obj

    db.add.side_effect = add_side_effect

    def delete_side_effect(obj):
        if isinstance(obj, SessaoConversaORM):
            db.sessoes.pop(obj.id_usuario, None)

    db.delete.side_effect = delete_side_effect

    def refresh_side_effect(obj):
        if getattr(obj, "id", None) is None:
            obj.id = 999

    db.refresh.side_effect = refresh_side_effect
    return db


@pytest.fixture
def enviar_mock():
    with patch.object(webhook_service, "enviar_mensagem_texto") as mock:
        yield mock


def _definir_lotes(db, lotes):
    db.lote_q.filter.return_value.all.return_value = lotes
    db.lote_q.filter.return_value.filter.return_value.all.return_value = lotes


# --- resolução por telefone -------------------------------------------------


def test_numero_nao_cadastrado_responde_aviso(db_mock, enviar_mock):
    db_mock.usuario_q.filter.return_value.first.return_value = None

    webhook_service.processar_webhook(db_mock, _payload(TELEFONE, "1"))

    enviar_mock.assert_called_once()
    assert "não está cadastrado" in enviar_mock.call_args[0][1]


# --- menu principal --------------------------------------------------------


def test_escolha_invalida_reimprime_menu(db_mock, enviar_mock):
    webhook_service.processar_webhook(db_mock, _payload(TELEFONE, "xyz"))

    enviar_mock.assert_called_once_with(TELEFONE, webhook_service.MENU)


def test_escolha_1_inicia_sessao_aguardando_produto(db_mock, enviar_mock):
    webhook_service.processar_webhook(db_mock, _payload(TELEFONE, "1"))

    assert db_mock.sessoes[ID_USUARIO].estado == webhook_service.ESTADO_AGUARDANDO_PRODUTO
    enviar_mock.assert_called_once_with(TELEFONE, "Qual o nome do produto?")


def test_escolha_2_sem_lotes_em_risco(db_mock, enviar_mock):
    webhook_service.processar_webhook(db_mock, _payload(TELEFONE, "2"))

    enviar_mock.assert_called_once_with(
        TELEFONE, "Nenhum produto próximo do vencimento no momento."
    )


def test_escolha_2_com_lote_em_risco_mostra_nome_do_produto(db_mock, enviar_mock):
    _definir_lotes(db_mock, [_lote_orm(id_lote=1)])
    db_mock.produto_q.filter.return_value.all.return_value = [_produto_orm()]

    webhook_service.processar_webhook(db_mock, _payload(TELEFONE, "2"))

    mensagem = enviar_mock.call_args[0][1]
    assert "Pão Francês" in mensagem


def test_escolha_2_ignora_lote_esgotado_mesmo_em_risco(db_mock, enviar_mock):
    # Regressão: um lote com saldo zerado por venda (RN07) continua
    # status = confirmado e nivel_risco calculado só pela validade (RN01)
    # — sem o filtro de status_operacional, ele voltaria a aparecer como
    # "produto vencendo" mesmo sem nenhuma unidade em estoque.
    _definir_lotes(db_mock, [_lote_orm(id_lote=1, status_operacional="esgotado")])
    db_mock.produto_q.filter.return_value.all.return_value = [_produto_orm()]

    webhook_service.processar_webhook(db_mock, _payload(TELEFONE, "2"))

    enviar_mock.assert_called_once_with(
        TELEFONE, "Nenhum produto próximo do vencimento no momento."
    )


def test_escolha_2_ignora_lote_descartado_mesmo_em_risco(db_mock, enviar_mock):
    _definir_lotes(db_mock, [_lote_orm(id_lote=1, status_operacional="descartado")])
    db_mock.produto_q.filter.return_value.all.return_value = [_produto_orm()]

    webhook_service.processar_webhook(db_mock, _payload(TELEFONE, "2"))

    enviar_mock.assert_called_once_with(
        TELEFONE, "Nenhum produto próximo do vencimento no momento."
    )


def test_escolha_2_mistura_lote_disponivel_e_esgotado_mostra_so_disponivel(db_mock, enviar_mock):
    _definir_lotes(
        db_mock,
        [
            _lote_orm(id_lote=1, status_operacional="disponivel"),
            _lote_orm(id_lote=2, id_produto=11, status_operacional="esgotado"),
        ],
    )
    db_mock.produto_q.filter.return_value.all.return_value = [
        _produto_orm(),
        _produto_orm(id_produto=11, nome="Leite"),
    ]

    webhook_service.processar_webhook(db_mock, _payload(TELEFONE, "2"))

    mensagem = enviar_mock.call_args[0][1]
    assert "Pão Francês" in mensagem
    assert "Leite" not in mensagem
    assert ID_USUARIO not in db_mock.sessoes  # consulta não inicia sessão


def test_escolha_3_sem_pendentes(db_mock, enviar_mock):
    webhook_service.processar_webhook(db_mock, _payload(TELEFONE, "3"))

    enviar_mock.assert_called_once_with(
        TELEFONE, "Não há nenhum cadastro pendente no momento."
    )


def test_escolha_3_com_pendentes_inicia_escolha(db_mock, enviar_mock):
    lote_pendente = _lote_orm(id_lote=7, status=StatusLote.PENDENTE_CONFIRMACAO)
    _definir_lotes(db_mock, [lote_pendente])
    db_mock.produto_q.filter.return_value.all.return_value = [_produto_orm()]

    webhook_service.processar_webhook(db_mock, _payload(TELEFONE, "3"))

    sessao = db_mock.sessoes[ID_USUARIO]
    assert sessao.estado == webhook_service.ESTADO_AGUARDANDO_ESCOLHA_CONFIRMAR_PENDENTE
    assert sessao.dados_parciais["lotes"] == [7]
    assert "Pão Francês" in enviar_mock.call_args[0][1]


# --- fluxo de cadastro -------------------------------------------------


def test_aguardando_produto_avanca_para_quantidade(db_mock, enviar_mock):
    db_mock.sessoes[ID_USUARIO] = SessaoConversaORM(
        id_usuario=ID_USUARIO,
        id_mercado=ID_MERCADO,
        estado=webhook_service.ESTADO_AGUARDANDO_PRODUTO,
        dados_parciais={},
        criado_em=datetime.now(),
        atualizado_em=datetime.now(),
    )

    webhook_service.processar_webhook(db_mock, _payload(TELEFONE, "Pão Francês"))

    sessao = db_mock.sessoes[ID_USUARIO]
    assert sessao.estado == webhook_service.ESTADO_AGUARDANDO_QUANTIDADE
    assert sessao.dados_parciais["produto_nome"] == "Pão Francês"
    enviar_mock.assert_called_once_with(TELEFONE, "Qual a quantidade?")


def test_aguardando_quantidade_invalida_mantem_estado(db_mock, enviar_mock):
    db_mock.sessoes[ID_USUARIO] = SessaoConversaORM(
        id_usuario=ID_USUARIO,
        id_mercado=ID_MERCADO,
        estado=webhook_service.ESTADO_AGUARDANDO_QUANTIDADE,
        dados_parciais={"produto_nome": "Pão"},
        criado_em=datetime.now(),
        atualizado_em=datetime.now(),
    )

    webhook_service.processar_webhook(db_mock, _payload(TELEFONE, "abc"))

    assert db_mock.sessoes[ID_USUARIO].estado == webhook_service.ESTADO_AGUARDANDO_QUANTIDADE
    assert "inválida" in enviar_mock.call_args[0][1]


def test_aguardando_quantidade_valida_avanca_para_validade(db_mock, enviar_mock):
    db_mock.sessoes[ID_USUARIO] = SessaoConversaORM(
        id_usuario=ID_USUARIO,
        id_mercado=ID_MERCADO,
        estado=webhook_service.ESTADO_AGUARDANDO_QUANTIDADE,
        dados_parciais={"produto_nome": "Pão"},
        criado_em=datetime.now(),
        atualizado_em=datetime.now(),
    )

    webhook_service.processar_webhook(db_mock, _payload(TELEFONE, "10"))

    sessao = db_mock.sessoes[ID_USUARIO]
    assert sessao.estado == webhook_service.ESTADO_AGUARDANDO_VALIDADE
    assert sessao.dados_parciais["quantidade"] == 10.0


def test_aguardando_validade_invalida_mantem_estado(db_mock, enviar_mock):
    db_mock.sessoes[ID_USUARIO] = SessaoConversaORM(
        id_usuario=ID_USUARIO,
        id_mercado=ID_MERCADO,
        estado=webhook_service.ESTADO_AGUARDANDO_VALIDADE,
        dados_parciais={"produto_nome": "Pão", "quantidade": 10.0},
        criado_em=datetime.now(),
        atualizado_em=datetime.now(),
    )

    webhook_service.processar_webhook(db_mock, _payload(TELEFONE, "amanha"))

    assert db_mock.sessoes[ID_USUARIO].estado == webhook_service.ESTADO_AGUARDANDO_VALIDADE
    assert "inválida" in enviar_mock.call_args[0][1]


def test_aguardando_validade_valida_avanca_para_confirmacao(db_mock, enviar_mock):
    db_mock.sessoes[ID_USUARIO] = SessaoConversaORM(
        id_usuario=ID_USUARIO,
        id_mercado=ID_MERCADO,
        estado=webhook_service.ESTADO_AGUARDANDO_VALIDADE,
        dados_parciais={"produto_nome": "Pão", "quantidade": 10.0},
        criado_em=datetime.now(),
        atualizado_em=datetime.now(),
    )

    webhook_service.processar_webhook(db_mock, _payload(TELEFONE, str(NAO_VENCIDO)))

    sessao = db_mock.sessoes[ID_USUARIO]
    assert sessao.estado == webhook_service.ESTADO_AGUARDANDO_CONFIRMACAO_CADASTRO
    mensagem = enviar_mock.call_args[0][1]
    assert "Pão" in mensagem and "10.0" in mensagem


def test_confirmacao_sim_cria_lote_e_encerra_sessao(db_mock, enviar_mock):
    db_mock.sessoes[ID_USUARIO] = SessaoConversaORM(
        id_usuario=ID_USUARIO,
        id_mercado=ID_MERCADO,
        estado=webhook_service.ESTADO_AGUARDANDO_CONFIRMACAO_CADASTRO,
        dados_parciais={
            "produto_nome": "Pão",
            "quantidade": 10.0,
            "data_validade": NAO_VENCIDO.isoformat(),
        },
        criado_em=datetime.now(),
        atualizado_em=datetime.now(),
    )

    webhook_service.processar_webhook(db_mock, _payload(TELEFONE, "sim"))

    assert ID_USUARIO not in db_mock.sessoes
    assert "pendente de confirmação" in enviar_mock.call_args[0][1]


def test_confirmacao_nao_cancela_e_encerra_sessao(db_mock, enviar_mock):
    db_mock.sessoes[ID_USUARIO] = SessaoConversaORM(
        id_usuario=ID_USUARIO,
        id_mercado=ID_MERCADO,
        estado=webhook_service.ESTADO_AGUARDANDO_CONFIRMACAO_CADASTRO,
        dados_parciais={
            "produto_nome": "Pão",
            "quantidade": 10.0,
            "data_validade": NAO_VENCIDO.isoformat(),
        },
        criado_em=datetime.now(),
        atualizado_em=datetime.now(),
    )

    webhook_service.processar_webhook(db_mock, _payload(TELEFONE, "não"))

    assert ID_USUARIO not in db_mock.sessoes
    enviar_mock.assert_called_once_with(TELEFONE, "Cadastro cancelado.")


def test_confirmacao_ambigua_pede_novamente(db_mock, enviar_mock):
    db_mock.sessoes[ID_USUARIO] = SessaoConversaORM(
        id_usuario=ID_USUARIO,
        id_mercado=ID_MERCADO,
        estado=webhook_service.ESTADO_AGUARDANDO_CONFIRMACAO_CADASTRO,
        dados_parciais={
            "produto_nome": "Pão",
            "quantidade": 10.0,
            "data_validade": NAO_VENCIDO.isoformat(),
        },
        criado_em=datetime.now(),
        atualizado_em=datetime.now(),
    )

    webhook_service.processar_webhook(db_mock, _payload(TELEFONE, "talvez"))

    assert db_mock.sessoes[ID_USUARIO].estado == webhook_service.ESTADO_AGUARDANDO_CONFIRMACAO_CADASTRO
    assert "sim ou não" in enviar_mock.call_args[0][1]


# --- escolha de pendente (confirmar/cancelar) -----------------------------


def test_escolha_confirmar_pendente_valida(db_mock, enviar_mock):
    lote_pendente = _lote_orm(id_lote=7, status=StatusLote.PENDENTE_CONFIRMACAO)
    _definir_lotes(db_mock, [lote_pendente])
    db_mock.sessoes[ID_USUARIO] = SessaoConversaORM(
        id_usuario=ID_USUARIO,
        id_mercado=ID_MERCADO,
        estado=webhook_service.ESTADO_AGUARDANDO_ESCOLHA_CONFIRMAR_PENDENTE,
        dados_parciais={"lotes": [7]},
        criado_em=datetime.now(),
        atualizado_em=datetime.now(),
    )

    webhook_service.processar_webhook(db_mock, _payload(TELEFONE, "1"))

    assert ID_USUARIO not in db_mock.sessoes
    assert lote_pendente.status == StatusLote.CONFIRMADO
    enviar_mock.assert_called_once_with(TELEFONE, "Cadastro confirmado.")


def test_escolha_confirmar_pendente_numero_invalido_mantem_sessao(db_mock, enviar_mock):
    lote_pendente = _lote_orm(id_lote=7, status=StatusLote.PENDENTE_CONFIRMACAO)
    _definir_lotes(db_mock, [lote_pendente])
    db_mock.sessoes[ID_USUARIO] = SessaoConversaORM(
        id_usuario=ID_USUARIO,
        id_mercado=ID_MERCADO,
        estado=webhook_service.ESTADO_AGUARDANDO_ESCOLHA_CONFIRMAR_PENDENTE,
        dados_parciais={"lotes": [7]},
        criado_em=datetime.now(),
        atualizado_em=datetime.now(),
    )

    webhook_service.processar_webhook(db_mock, _payload(TELEFONE, "99"))

    assert ID_USUARIO in db_mock.sessoes
    assert "Número inválido" in enviar_mock.call_args[0][1]


def test_escolha_cancelar_pendente_valida(db_mock, enviar_mock):
    lote_pendente = _lote_orm(id_lote=7, status=StatusLote.PENDENTE_CONFIRMACAO)
    _definir_lotes(db_mock, [lote_pendente])
    db_mock.sessoes[ID_USUARIO] = SessaoConversaORM(
        id_usuario=ID_USUARIO,
        id_mercado=ID_MERCADO,
        estado=webhook_service.ESTADO_AGUARDANDO_ESCOLHA_CANCELAR_PENDENTE,
        dados_parciais={"lotes": [7]},
        criado_em=datetime.now(),
        atualizado_em=datetime.now(),
    )

    webhook_service.processar_webhook(db_mock, _payload(TELEFONE, "1"))

    assert ID_USUARIO not in db_mock.sessoes
    db_mock.delete.assert_any_call(lote_pendente)
    enviar_mock.assert_called_once_with(TELEFONE, "Cadastro cancelado.")
