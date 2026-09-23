"""Registro e atualização de ações preventivas sobre itens do relatório
diário (Gestão Preventiva — Fase 1).

Isolamento por mercado (RN05): nem `itens_relatorio_diario` nem
`acoes_preventivas` têm coluna `id_mercado` (migration 0007) — a
verificação de pertencimento ao mercado é feita via JOIN, subindo a
cadeia ItemRelatorioDiarioORM -> RelatorioAcaoDiarioORM.id_mercado (e,
para uma AcaoPreventivaORM, mais um JOIN até ItemRelatorioDiarioORM).

Uma ação por item (Fase 1): não há UNIQUE CONSTRAINT em
`acoes_preventivas.id_item_relatorio` na migration 0007 — a
unicidade aqui é garantida só na camada de aplicação (`registrar`
procura uma ação existente antes de criar; se encontrar, devolve a
existente em vez de criar outra). Uma constraint de banco equivalente
poderá ser avaliada numa migration futura, se a regra continuar valendo.

`total_acoes_recomendadas`/`total_acoes_realizadas` (relatorios_acao_diaria):
`registrar` nunca altera nenhum dos dois — `total_acoes_recomendadas`
continua sendo definido só pela geração do relatório
(`relatorio_acao_diaria_service.gerar_ou_obter`). `atualizar` recalcula
`total_acoes_realizadas` (contagem completa, não incremento/decremento)
sempre que a requisição inclui uma mudança de `status`, para nunca
duplicar nem perder contagem em atualizações repetidas.
"""

from datetime import datetime

from sqlalchemy.orm import Session

from app.models.acao_preventiva import AcaoPreventivaORM
from app.models.item_relatorio_diario import ItemRelatorioDiarioORM
from app.models.relatorio_acao_diaria import RelatorioAcaoDiarioORM
from app.schemas.acao_preventiva import (
    AcaoPreventiva,
    AcaoPreventivaCreateRequest,
    AcaoPreventivaEditRequest,
)
from app.services import usuario_service

STATUS_RECOMENDADA = "recomendada"
STATUS_EM_ANDAMENTO = "em_andamento"
STATUS_CONCLUIDA = "concluida"
STATUS_CANCELADA = "cancelada"
STATUS_VALIDOS = {STATUS_RECOMENDADA, STATUS_EM_ANDAMENTO, STATUS_CONCLUIDA, STATUS_CANCELADA}


class ItemRelatorioNaoEncontrado(Exception):
    pass


class AcaoPreventivaNaoEncontrada(Exception):
    pass


class StatusAcaoPreventivaInvalido(Exception):
    pass


def registrar(
    db: Session, id_mercado: int, id_item_relatorio: int, request: AcaoPreventivaCreateRequest
) -> AcaoPreventiva:
    """Registra uma ação preventiva para um item do relatório diário, ou
    devolve a já existente para o mesmo item (idempotente — Fase 1: uma
    ação por item, protegida só na camada de aplicação)."""
    item_orm = (
        db.query(ItemRelatorioDiarioORM)
        .join(RelatorioAcaoDiarioORM, ItemRelatorioDiarioORM.id_relatorio == RelatorioAcaoDiarioORM.id)
        .filter(
            ItemRelatorioDiarioORM.id == id_item_relatorio,
            RelatorioAcaoDiarioORM.id_mercado == id_mercado,
        )
        .first()
    )
    if item_orm is None:
        # RN05: item de outro mercado é tratado como inexistente, não
        # como "proibido" — mesmo critério já usado em lotes/usuários.
        raise ItemRelatorioNaoEncontrado(id_item_relatorio)

    acao_existente = (
        db.query(AcaoPreventivaORM)
        .filter(AcaoPreventivaORM.id_item_relatorio == item_orm.id)
        .first()
    )
    if acao_existente is not None:
        return AcaoPreventiva.model_validate(acao_existente, from_attributes=True)

    if request.id_usuario_responsavel is not None:
        # Propaga UsuarioNaoEncontrado se o usuário não existir ou for de
        # outro mercado — reaproveitado de usuario_service, sem duplicar.
        usuario_service.obter(db, id_mercado, request.id_usuario_responsavel)

    acao_orm = AcaoPreventivaORM(
        id_item_relatorio=item_orm.id,
        id_usuario_responsavel=request.id_usuario_responsavel,
        # Nunca aceito do cliente (o schema nem tem esse campo) — sempre
        # copiado do item já validado acima.
        acao_recomendada=item_orm.acao_recomendada,
        acao_realizada=request.acao_realizada,
        status=STATUS_RECOMENDADA,
        observacao=request.observacao,
    )
    try:
        db.add(acao_orm)
        db.commit()
    except Exception:
        db.rollback()
        raise

    db.refresh(acao_orm)
    return AcaoPreventiva.model_validate(acao_orm, from_attributes=True)


def atualizar(
    db: Session, id_mercado: int, id_acao_preventiva: int, request: AcaoPreventivaEditRequest
) -> AcaoPreventiva:
    """Atualiza parcialmente uma ação preventiva já registrada. Quando a
    requisição inclui `status`, recalcula total_acoes_realizadas do
    relatório pai (contagem completa, não incremento/decremento)."""
    acao_orm = (
        db.query(AcaoPreventivaORM)
        .join(ItemRelatorioDiarioORM, AcaoPreventivaORM.id_item_relatorio == ItemRelatorioDiarioORM.id)
        .join(RelatorioAcaoDiarioORM, ItemRelatorioDiarioORM.id_relatorio == RelatorioAcaoDiarioORM.id)
        .filter(
            AcaoPreventivaORM.id == id_acao_preventiva,
            RelatorioAcaoDiarioORM.id_mercado == id_mercado,
        )
        .with_for_update()
        .first()
    )
    if acao_orm is None:
        # RN05: ação de outro mercado é tratada como inexistente, não
        # como "proibida" — não revela que o id existe noutro mercado.
        raise AcaoPreventivaNaoEncontrada(id_acao_preventiva)

    if request.status is not None and request.status not in STATUS_VALIDOS:
        raise StatusAcaoPreventivaInvalido(request.status)

    status_alterado = request.status is not None
    if request.status is not None:
        acao_orm.status = request.status
    if request.acao_realizada is not None:
        acao_orm.acao_realizada = request.acao_realizada
    if request.data_inicio is not None:
        acao_orm.data_inicio = request.data_inicio
    if request.data_fim is not None:
        acao_orm.data_fim = request.data_fim
    if request.resultado_operacional is not None:
        acao_orm.resultado_operacional = request.resultado_operacional
    if request.observacao is not None:
        acao_orm.observacao = request.observacao
    # Sem onupdate no banco (migration 0007 só define server_default=now()
    # na criação) — bump manual, mesma disciplina de
    # lote_service.editar_pendente com data_ultima_atualizacao.
    acao_orm.atualizada_em = datetime.now()

    try:
        if status_alterado:
            # SessionLocal usa autoflush=False (app/core/database.py) —
            # sem este flush, a contagem abaixo não veria o novo status
            # ainda pendente na sessão, só o valor anterior.
            db.flush()

            item_orm = db.get(ItemRelatorioDiarioORM, acao_orm.id_item_relatorio)
            total_concluidas = (
                db.query(AcaoPreventivaORM)
                .join(
                    ItemRelatorioDiarioORM,
                    AcaoPreventivaORM.id_item_relatorio == ItemRelatorioDiarioORM.id,
                )
                .filter(
                    ItemRelatorioDiarioORM.id_relatorio == item_orm.id_relatorio,
                    AcaoPreventivaORM.status == STATUS_CONCLUIDA,
                )
                .count()
            )
            relatorio_orm = db.get(
                RelatorioAcaoDiarioORM,
                item_orm.id_relatorio,
                with_for_update=True,
                populate_existing=True,
            )
            relatorio_orm.total_acoes_realizadas = total_concluidas

        db.commit()
    except Exception:
        db.rollback()
        raise

    db.refresh(acao_orm)
    return AcaoPreventiva.model_validate(acao_orm, from_attributes=True)
