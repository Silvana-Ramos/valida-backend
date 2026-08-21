"""Cadastro de usuário (pessoa que interage pelo WhatsApp em nome de um
mercado) persistido no PostgreSQL via SQLAlchemy.

`id_mercado` é sempre um parâmetro confiável do serviço, nunca lido do
corpo da requisição — quem chama (o router) é responsável por resolvê-lo
de uma fonte confiável (RN05): a chave do próprio mercado para
self-service, ou uma autenticação de admin para o bootstrap do primeiro
usuário de um mercado novo. Um usuário de outro mercado é tratado como
inexistente, não como "proibido" — mesmo critério já usado em lotes e
movimentações, para não vazar a existência de registros de outros
mercados.
"""

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.usuario import UsuarioORM
from app.schemas.usuario import Usuario, UsuarioCreateRequest, UsuarioUpdateRequest


class UsuarioNaoEncontrado(Exception):
    pass


class TelefoneJaCadastrado(Exception):
    pass


def criar(db: Session, id_mercado: int, request: UsuarioCreateRequest) -> Usuario:
    usuario_orm = UsuarioORM(
        id_mercado=id_mercado,
        telefone_whatsapp=request.telefone_whatsapp.strip(),
        nome=request.nome.strip(),
        papel=request.papel,
    )
    db.add(usuario_orm)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise TelefoneJaCadastrado(request.telefone_whatsapp)
    db.refresh(usuario_orm)
    return Usuario.model_validate(usuario_orm, from_attributes=True)


def obter(db: Session, id_mercado: int, id_usuario: int) -> Usuario:
    usuario_orm = db.get(UsuarioORM, id_usuario)
    if usuario_orm is None or usuario_orm.id_mercado != id_mercado:
        raise UsuarioNaoEncontrado(id_usuario)
    return Usuario.model_validate(usuario_orm, from_attributes=True)


def listar(db: Session, id_mercado: int) -> list[Usuario]:
    query = db.query(UsuarioORM).filter(UsuarioORM.id_mercado == id_mercado)
    return [Usuario.model_validate(usuario_orm, from_attributes=True) for usuario_orm in query.all()]


def atualizar(
    db: Session, id_mercado: int, id_usuario: int, request: UsuarioUpdateRequest
) -> Usuario:
    usuario_orm = db.get(UsuarioORM, id_usuario)
    if usuario_orm is None or usuario_orm.id_mercado != id_mercado:
        raise UsuarioNaoEncontrado(id_usuario)

    if request.telefone_whatsapp is not None:
        usuario_orm.telefone_whatsapp = request.telefone_whatsapp.strip()
    if request.nome is not None:
        usuario_orm.nome = request.nome.strip()
    if request.papel is not None:
        usuario_orm.papel = request.papel

    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise TelefoneJaCadastrado(request.telefone_whatsapp)
    db.refresh(usuario_orm)
    return Usuario.model_validate(usuario_orm, from_attributes=True)
