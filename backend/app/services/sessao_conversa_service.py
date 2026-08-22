"""CRUD da sessão de conversa guiada por menu do WhatsApp (fatia 6 do
plano de integração — `sessoes_whatsapp`, Migration 0006). Ainda sem
nenhum consumidor real: o webhook que vai chamar este serviço é a
fatia 7, não implementada.

`id_usuario` é a chave (PK da tabela, um FK para `usuarios.id`) — quem
chama já resolveu o usuário por uma fonte confiável (o telefone
normalizado, `app/core/telefone.py`), então `id_mercado` aqui é só a
mesma checagem defensiva de posse (RN05) já usada em `lote_service`,
não uma fonte de verdade paralela: como `id_usuario -> id_mercado` é
fixo (nunca muda por `PATCH /usuarios`), essa checagem nunca deveria
falhar na prática, exceto por um bug de quem chama.

Ausência de linha significa "sem conversa ativa" (ver
`docs/modelo-dados.md`) — por isso `obter` retorna `None`, não levanta
exceção, diferente do padrão usado para entidades permanentes como
`Lote`/`Usuario` (onde a ausência é sempre um erro de busca)."""

from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from app.models.sessao_conversa import SessaoConversaORM
from app.schemas.sessao_conversa import SessaoConversa


class SessaoConversaNaoEncontrada(Exception):
    pass


def obter(db: Session, id_mercado: int, id_usuario: int) -> SessaoConversa | None:
    sessao_orm = db.get(SessaoConversaORM, id_usuario)
    if sessao_orm is None or sessao_orm.id_mercado != id_mercado:
        return None
    return SessaoConversa.model_validate(sessao_orm, from_attributes=True)


def iniciar(
    db: Session,
    id_mercado: int,
    id_usuario: int,
    estado: str,
    dados_parciais: dict[str, Any] | None = None,
) -> SessaoConversa:
    """Cria uma sessão nova ou substitui uma já existente para esse
    usuário — iniciar um fluxo novo abandona qualquer estado anterior
    (só existe uma conversa ativa por usuário)."""
    agora = datetime.now()
    sessao_orm = db.get(SessaoConversaORM, id_usuario)
    if sessao_orm is not None:
        sessao_orm.estado = estado
        sessao_orm.dados_parciais = dados_parciais or {}
        sessao_orm.atualizado_em = agora
    else:
        sessao_orm = SessaoConversaORM(
            id_usuario=id_usuario,
            id_mercado=id_mercado,
            estado=estado,
            dados_parciais=dados_parciais or {},
            criado_em=agora,
            atualizado_em=agora,
        )
        db.add(sessao_orm)
    db.commit()
    db.refresh(sessao_orm)
    return SessaoConversa.model_validate(sessao_orm, from_attributes=True)


def avancar(
    db: Session,
    id_mercado: int,
    id_usuario: int,
    estado: str,
    dados_parciais: dict[str, Any] | None = None,
) -> SessaoConversa:
    """Avança o passo do fluxo já em andamento. `dados_parciais` é
    mesclado com o que já estava salvo (não substitui) — cada passo do
    fluxo guiado só informa o campo que acabou de coletar, não o
    histórico inteiro."""
    sessao_orm = db.get(SessaoConversaORM, id_usuario)
    if sessao_orm is None or sessao_orm.id_mercado != id_mercado:
        raise SessaoConversaNaoEncontrada(id_usuario)

    sessao_orm.estado = estado
    if dados_parciais:
        sessao_orm.dados_parciais = {**sessao_orm.dados_parciais, **dados_parciais}
    sessao_orm.atualizado_em = datetime.now()

    db.commit()
    db.refresh(sessao_orm)
    return SessaoConversa.model_validate(sessao_orm, from_attributes=True)


def encerrar(db: Session, id_mercado: int, id_usuario: int) -> None:
    """Idempotente: encerrar uma sessão que não existe (ou já foi
    encerrada) não é erro — mesma semântica de "ausência = sem conversa
    ativa" usada em `obter`."""
    sessao_orm = db.get(SessaoConversaORM, id_usuario)
    if sessao_orm is None or sessao_orm.id_mercado != id_mercado:
        return
    db.delete(sessao_orm)
    db.commit()
