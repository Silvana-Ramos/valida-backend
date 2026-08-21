"""Cadastro de mercado (onboarding do piloto) persistido no PostgreSQL via
SQLAlchemy.

`criar` é uma ação administrativa — não passa por `Depends(obter_id_mercado_atual)`
(não existe `id_mercado` ainda antes do mercado existir). O router que vai
expor isso precisa de uma autenticação de admin separada, não a chave por
mercado usada no resto da API.
"""

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.mercado import MercadoORM
from app.schemas.mercado import Mercado, MercadoCreateRequest, MercadoUpdateRequest


class MercadoNaoEncontrado(Exception):
    pass


class TelefoneJaCadastrado(Exception):
    pass


def criar(db: Session, request: MercadoCreateRequest) -> Mercado:
    mercado_orm = MercadoORM(
        nome=request.nome.strip(),
        telefone_whatsapp=request.telefone_whatsapp.strip(),
        segmento=request.segmento,
    )
    db.add(mercado_orm)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise TelefoneJaCadastrado(request.telefone_whatsapp)
    db.refresh(mercado_orm)
    return Mercado.model_validate(mercado_orm, from_attributes=True)


def obter(db: Session, id_mercado: int) -> Mercado:
    mercado_orm = db.get(MercadoORM, id_mercado)
    if mercado_orm is None:
        raise MercadoNaoEncontrado(id_mercado)
    return Mercado.model_validate(mercado_orm, from_attributes=True)


def listar(db: Session) -> list[Mercado]:
    return [
        Mercado.model_validate(mercado_orm, from_attributes=True)
        for mercado_orm in db.query(MercadoORM).all()
    ]


def atualizar(db: Session, id_mercado: int, request: MercadoUpdateRequest) -> Mercado:
    mercado_orm = db.get(MercadoORM, id_mercado)
    if mercado_orm is None:
        raise MercadoNaoEncontrado(id_mercado)

    if request.nome is not None:
        mercado_orm.nome = request.nome.strip()
    if request.telefone_whatsapp is not None:
        mercado_orm.telefone_whatsapp = request.telefone_whatsapp.strip()
    if request.segmento is not None:
        mercado_orm.segmento = request.segmento
    if request.status is not None:
        mercado_orm.status = request.status
    if request.timezone is not None:
        mercado_orm.timezone = request.timezone
    if request.horario_abertura is not None:
        mercado_orm.horario_abertura = request.horario_abertura
    if request.horario_relatorio_diario is not None:
        mercado_orm.horario_relatorio_diario = request.horario_relatorio_diario
    if request.relatorio_diario_ativo is not None:
        mercado_orm.relatorio_diario_ativo = request.relatorio_diario_ativo
    if request.limite_valor_atencao is not None:
        mercado_orm.limite_valor_atencao = request.limite_valor_atencao
    if request.limite_quantidade_atencao is not None:
        mercado_orm.limite_quantidade_atencao = request.limite_quantidade_atencao

    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise TelefoneJaCadastrado(request.telefone_whatsapp)
    db.refresh(mercado_orm)
    return Mercado.model_validate(mercado_orm, from_attributes=True)
