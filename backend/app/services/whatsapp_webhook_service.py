"""Processamento das mensagens recebidas via webhook do WhatsApp
(fatia 7 — última do plano de integração). Fluxo guiado por menu, sem
NLU/LLM (decisão aprovada explicitamente pelo usuário): toda mensagem
fora de um fluxo em andamento é interpretada como uma escolha de menu
(1-4) ou ignorada em favor de reimprimir o menu.

**Gap conhecido e aceito, explicitamente adiado (plano de integração,
seção "decisões em aberto"):** não há deduplicação de `message id` da
Meta. Se a Meta reentregar um webhook (timeout, etc.) depois que já
processamos a mensagem com sucesso, o texto é processado de novo — no
pior caso (ex.: usuário estava no passo "confirma? sim/não"), isso
poderia criar um lote duplicado. Aceito como risco residual do piloto;
a idempotência fica para uma fatia futura e separada.

Falha ao *enviar* uma resposta (`whatsapp_client`) nunca desfaz uma
mudança de estado já persistida (lote criado/confirmado/cancelado,
sessão avançada) — é só engolida (ver `_responder`), porque não há
infraestrutura de log/observabilidade neste piloto ainda.
"""

from datetime import date

from sqlalchemy.orm import Session

from app.schemas.enums import NivelRisco, StatusLote
from app.schemas.lote import LoteCreateRequest
from app.schemas.sessao_conversa import SessaoConversa
from app.schemas.usuario import Usuario
from app.services import lote_service, produto_service, sessao_conversa_service, usuario_service
from app.services.lote_service import AcaoInvalidaParaStatus, LoteNaoEncontrado
from app.services.whatsapp_client import EnvioWhatsAppFalhou, WhatsAppNaoConfigurado, enviar_mensagem_texto

ESTADO_AGUARDANDO_PRODUTO = "aguardando_produto"
ESTADO_AGUARDANDO_QUANTIDADE = "aguardando_quantidade"
ESTADO_AGUARDANDO_VALIDADE = "aguardando_validade"
ESTADO_AGUARDANDO_CONFIRMACAO_CADASTRO = "aguardando_confirmacao_cadastro"
ESTADO_AGUARDANDO_ESCOLHA_CONFIRMAR_PENDENTE = "aguardando_escolha_confirmar_pendente"
ESTADO_AGUARDANDO_ESCOLHA_CANCELAR_PENDENTE = "aguardando_escolha_cancelar_pendente"

NIVEIS_EM_RISCO = {NivelRisco.ATENCAO, NivelRisco.RISCO, NivelRisco.URGENTE, NivelRisco.VENCIDO}

MENU = (
    "Olá! O que você quer fazer?\n"
    "1 - Cadastrar produto\n"
    "2 - Ver produtos vencendo\n"
    "3 - Confirmar um cadastro pendente\n"
    "4 - Cancelar um cadastro pendente"
)


def processar_webhook(db: Session, payload: dict) -> None:
    """Extrai mensagens de texto do payload da Meta e processa cada uma.
    Ignora silenciosamente qualquer coisa que não seja mensagem de
    texto recebida (ex.: eventos de status de entrega, mídia — fora do
    escopo do piloto)."""
    for entry in payload.get("entry", []):
        for change in entry.get("changes", []):
            for mensagem in change.get("value", {}).get("messages", []):
                if mensagem.get("type") != "text":
                    continue
                telefone = mensagem.get("from")
                texto = mensagem.get("text", {}).get("body")
                if telefone and texto is not None:
                    _processar_mensagem(db, telefone, texto)


def _responder(telefone: str, texto: str) -> None:
    try:
        enviar_mensagem_texto(telefone, texto)
    except (WhatsAppNaoConfigurado, EnvioWhatsAppFalhou):
        pass


def _processar_mensagem(db: Session, telefone: str, texto: str) -> None:
    usuario = usuario_service.obter_por_telefone(db, telefone)
    if usuario is None:
        _responder(telefone, "Esse número não está cadastrado no Valida. Fale com o suporte.")
        return

    sessao = sessao_conversa_service.obter(db, usuario.id_mercado, usuario.id)
    if sessao is None:
        _tratar_comando_menu(db, usuario, texto)
    else:
        _tratar_passo_fluxo(db, usuario, sessao, texto)


def _tratar_comando_menu(db: Session, usuario: Usuario, texto: str) -> None:
    escolha = texto.strip()
    if escolha == "1":
        sessao_conversa_service.iniciar(
            db, usuario.id_mercado, usuario.id, ESTADO_AGUARDANDO_PRODUTO
        )
        _responder(usuario.telefone_whatsapp, "Qual o nome do produto?")
    elif escolha == "2":
        _responder(usuario.telefone_whatsapp, _listar_produtos_vencendo(db, usuario.id_mercado))
    elif escolha == "3":
        _iniciar_escolha_pendente(db, usuario, ESTADO_AGUARDANDO_ESCOLHA_CONFIRMAR_PENDENTE)
    elif escolha == "4":
        _iniciar_escolha_pendente(db, usuario, ESTADO_AGUARDANDO_ESCOLHA_CANCELAR_PENDENTE)
    else:
        _responder(usuario.telefone_whatsapp, MENU)


def _listar_produtos_vencendo(db: Session, id_mercado: int) -> str:
    lotes = [
        lote
        for lote in lote_service.listar(db, id_mercado, status=StatusLote.CONFIRMADO)
        if lote.nivel_risco in NIVEIS_EM_RISCO
    ]
    if not lotes:
        return "Nenhum produto próximo do vencimento no momento."

    produtos_por_id = {p.id: p.nome for p in produto_service.listar(db, id_mercado)}
    linhas = [
        f"- {produtos_por_id.get(lote.id_produto, f'produto #{lote.id_produto}')}: "
        f"{lote.quantidade} un., {lote.dias_restantes} dia(s) restante(s) ({lote.nivel_risco.value})"
        for lote in lotes
    ]
    return "Produtos próximos do vencimento:\n" + "\n".join(linhas)


def _iniciar_escolha_pendente(db: Session, usuario: Usuario, estado: str) -> None:
    lotes = lote_service.listar(db, usuario.id_mercado, status=StatusLote.PENDENTE_CONFIRMACAO)
    if not lotes:
        _responder(usuario.telefone_whatsapp, "Não há nenhum cadastro pendente no momento.")
        return

    produtos_por_id = {p.id: p.nome for p in produto_service.listar(db, usuario.id_mercado)}
    linhas = [
        f"{indice} - {produtos_por_id.get(lote.id_produto, f'produto #{lote.id_produto}')} "
        f"({lote.quantidade} un., validade {lote.data_validade.isoformat()})"
        for indice, lote in enumerate(lotes, start=1)
    ]
    sessao_conversa_service.iniciar(
        db,
        usuario.id_mercado,
        usuario.id,
        estado,
        dados_parciais={"lotes": [lote.id for lote in lotes]},
    )
    acao = "confirmar" if estado == ESTADO_AGUARDANDO_ESCOLHA_CONFIRMAR_PENDENTE else "cancelar"
    _responder(
        usuario.telefone_whatsapp,
        f"Qual cadastro pendente você quer {acao}? Responda com o número:\n" + "\n".join(linhas),
    )


def _tratar_passo_fluxo(db: Session, usuario: Usuario, sessao: SessaoConversa, texto: str) -> None:
    texto = texto.strip()
    if sessao.estado == ESTADO_AGUARDANDO_PRODUTO:
        _passo_aguardando_produto(db, usuario, texto)
    elif sessao.estado == ESTADO_AGUARDANDO_QUANTIDADE:
        _passo_aguardando_quantidade(db, usuario, texto)
    elif sessao.estado == ESTADO_AGUARDANDO_VALIDADE:
        _passo_aguardando_validade(db, usuario, texto)
    elif sessao.estado == ESTADO_AGUARDANDO_CONFIRMACAO_CADASTRO:
        _passo_aguardando_confirmacao_cadastro(db, usuario, sessao, texto)
    elif sessao.estado == ESTADO_AGUARDANDO_ESCOLHA_CONFIRMAR_PENDENTE:
        _passo_escolha_pendente(db, usuario, sessao, texto, acao="confirmar")
    elif sessao.estado == ESTADO_AGUARDANDO_ESCOLHA_CANCELAR_PENDENTE:
        _passo_escolha_pendente(db, usuario, sessao, texto, acao="cancelar")
    else:
        # Estado desconhecido (não deveria acontecer) — encerra e volta ao menu.
        sessao_conversa_service.encerrar(db, usuario.id_mercado, usuario.id)
        _responder(usuario.telefone_whatsapp, MENU)


def _passo_aguardando_produto(db: Session, usuario: Usuario, texto: str) -> None:
    if not texto:
        _responder(usuario.telefone_whatsapp, "Nome do produto inválido. Qual o nome do produto?")
        return
    sessao_conversa_service.avancar(
        db, usuario.id_mercado, usuario.id, ESTADO_AGUARDANDO_QUANTIDADE, {"produto_nome": texto}
    )
    _responder(usuario.telefone_whatsapp, "Qual a quantidade?")


def _passo_aguardando_quantidade(db: Session, usuario: Usuario, texto: str) -> None:
    try:
        quantidade = float(texto.replace(",", "."))
        if quantidade <= 0:
            raise ValueError
    except ValueError:
        _responder(
            usuario.telefone_whatsapp, "Quantidade inválida. Informe um número maior que zero."
        )
        return
    sessao_conversa_service.avancar(
        db, usuario.id_mercado, usuario.id, ESTADO_AGUARDANDO_VALIDADE, {"quantidade": quantidade}
    )
    _responder(usuario.telefone_whatsapp, "Qual a validade? (formato AAAA-MM-DD)")


def _passo_aguardando_validade(db: Session, usuario: Usuario, texto: str) -> None:
    try:
        data_validade = date.fromisoformat(texto)
    except ValueError:
        _responder(usuario.telefone_whatsapp, "Data inválida. Informe no formato AAAA-MM-DD.")
        return
    sessao = sessao_conversa_service.avancar(
        db,
        usuario.id_mercado,
        usuario.id,
        ESTADO_AGUARDANDO_CONFIRMACAO_CADASTRO,
        {"data_validade": data_validade.isoformat()},
    )
    resumo = (
        "Confirma o cadastro?\n"
        f"Produto: {sessao.dados_parciais['produto_nome']}\n"
        f"Quantidade: {sessao.dados_parciais['quantidade']}\n"
        f"Validade: {sessao.dados_parciais['data_validade']}\n"
        "Responda sim ou não."
    )
    _responder(usuario.telefone_whatsapp, resumo)


def _passo_aguardando_confirmacao_cadastro(
    db: Session, usuario: Usuario, sessao: SessaoConversa, texto: str
) -> None:
    resposta = texto.strip().lower()
    if resposta in ("sim", "s"):
        dados = sessao.dados_parciais
        request = LoteCreateRequest(
            produto_nome=dados["produto_nome"],
            quantidade=dados["quantidade"],
            data_validade=date.fromisoformat(dados["data_validade"]),
        )
        lote_service.criar_pendente(db, usuario.id_mercado, request)
        sessao_conversa_service.encerrar(db, usuario.id_mercado, usuario.id)
        _responder(
            usuario.telefone_whatsapp,
            "Cadastro registrado como pendente de confirmação. Use a opção 3 do menu quando "
            "quiser confirmar definitivamente.",
        )
    elif resposta in ("não", "nao", "n"):
        sessao_conversa_service.encerrar(db, usuario.id_mercado, usuario.id)
        _responder(usuario.telefone_whatsapp, "Cadastro cancelado.")
    else:
        _responder(usuario.telefone_whatsapp, "Não entendi. Responda sim ou não.")


def _passo_escolha_pendente(
    db: Session, usuario: Usuario, sessao: SessaoConversa, texto: str, acao: str
) -> None:
    lotes_ids = sessao.dados_parciais.get("lotes", [])
    try:
        indice = int(texto.strip()) - 1
        if indice < 0 or indice >= len(lotes_ids):
            raise ValueError
    except ValueError:
        _responder(usuario.telefone_whatsapp, "Número inválido. Responda com o número da lista.")
        return

    id_lote = lotes_ids[indice]
    try:
        if acao == "confirmar":
            lote_service.confirmar(db, usuario.id_mercado, id_lote)
            mensagem = "Cadastro confirmado."
        else:
            lote_service.cancelar(db, usuario.id_mercado, id_lote)
            mensagem = "Cadastro cancelado."
    except (LoteNaoEncontrado, AcaoInvalidaParaStatus):
        mensagem = "Não foi possível concluir — o cadastro pode já ter sido alterado."

    sessao_conversa_service.encerrar(db, usuario.id_mercado, usuario.id)
    _responder(usuario.telefone_whatsapp, mensagem)
