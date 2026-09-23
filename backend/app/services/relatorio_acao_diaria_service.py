"""Geração da fotografia diária de risco (Gestão Preventiva — Fase 1).

Reaproveita o mesmo conceito de "lote acionável" já usado pela RN06
(nivel_risco numa faixa de risco + status_operacional disponível,
implementado hoje em whatsapp_webhook_service._listar_produtos_vencendo)
— aqui registrado como uma decisão explícita da Gestão Preventiva, sem
alterar retroativamente o texto da RN06 em docs/regras-negocio.md.

Transação única por relatório: ou o relatório inteiro (com todos os seus
itens) é gravado, ou nada é gravado. Diferente do job de RN03
(recalculo_risco_service, que comita lote a lote) e da pipeline de
importação (importacao_service, que comita linha a linha) — ali cada
unidade processada é independente e um erro isolado não deve derrubar as
demais; aqui todo o conteúdo pertence a um único relatório de um único
mercado, então uma inconsistência precisa interromper a geração inteira
sem deixar nada parcialmente gravado (ver QuantidadeDisponivelInconsistente).
"""

from datetime import date
from decimal import Decimal

from sqlalchemy.orm import Session

from app.models.item_relatorio_diario import ItemRelatorioDiarioORM
from app.models.lote import LoteORM
from app.models.relatorio_acao_diaria import RelatorioAcaoDiarioORM
from app.schemas.enums import NivelRisco, StatusLote
from app.schemas.item_relatorio_diario import ItemRelatorioDiario
from app.schemas.relatorio_acao_diaria import RelatorioAcaoDiario
from app.services.lote_service import calcular_risco, hoje_do_mercado
from app.services.movimentacao_service import (
    STATUS_OPERACIONAL_DESCARTADO,
    STATUS_OPERACIONAL_ESGOTADO,
)

# RN06, reaproveitado como decisão explícita da Gestão Preventiva — mesmo
# conceito de "lote acionável" já usado em
# whatsapp_webhook_service._listar_produtos_vencendo.
NIVEIS_ACIONAVEIS = {NivelRisco.ATENCAO, NivelRisco.RISCO, NivelRisco.URGENTE, NivelRisco.VENCIDO}
STATUS_OPERACIONAIS_SEM_ACAO = {STATUS_OPERACIONAL_ESGOTADO, STATUS_OPERACIONAL_DESCARTADO}

PRIORIDADE_POR_NIVEL = {
    NivelRisco.VENCIDO: "CRITICA",
    NivelRisco.URGENTE: "ALTA",
    NivelRisco.RISCO: "MEDIA",
    NivelRisco.ATENCAO: "BAIXA",
}

ACAO_RECOMENDADA_POR_NIVEL = {
    NivelRisco.VENCIDO: (
        "Retirar do estoque imediatamente e registrar a retirada por "
        "vencimento. Não vender."
    ),
    NivelRisco.URGENTE: "Priorizar venda seguindo FEFO e avaliar desconto, combo ou destaque.",
    NivelRisco.RISCO: "Reforçar exposição, acompanhar o giro e considerar ação promocional.",
    NivelRisco.ATENCAO: "Acompanhar o lote e manter a organização FEFO.",
}


class QuantidadeDisponivelInconsistente(Exception):
    """Lote confirmado e acionável com quantidade_disponivel nula — não
    deveria ocorrer (backfill da Migration 0002 + sincronização feita por
    lote_service.criar_pendente/editar_pendente). Tratado como
    inconsistência de dado que interrompe a geração inteira, nunca
    contornada com uma quantidade inventada ou com o campo `quantidade`
    legado."""


class RelatorioNaoEncontrado(Exception):
    pass


def gerar_ou_obter(
    db: Session, id_mercado: int, data_referencia: date | None = None
) -> RelatorioAcaoDiario:
    """Gera a fotografia diária de lotes acionáveis do mercado, ou
    devolve o relatório já existente para a mesma data — idempotente por
    (id_mercado, data_referencia): nunca regenera nem duplica."""
    hoje = hoje_do_mercado(db, id_mercado)
    data_referencia = data_referencia or hoje

    relatorio_orm = (
        db.query(RelatorioAcaoDiarioORM)
        .filter(
            RelatorioAcaoDiarioORM.id_mercado == id_mercado,
            RelatorioAcaoDiarioORM.data_referencia == data_referencia,
        )
        .first()
    )
    if relatorio_orm is not None:
        return RelatorioAcaoDiario.model_validate(relatorio_orm, from_attributes=True)

    try:
        # Construído inteiramente em memória antes de qualquer escrita: se
        # QuantidadeDisponivelInconsistente for levantada aqui, nada foi
        # tocado no banco ainda.
        itens_orm = _montar_itens(db, id_mercado, hoje)

        relatorio_orm = RelatorioAcaoDiarioORM(
            id_mercado=id_mercado,
            data_referencia=data_referencia,
            status="gerado",
            qtd_vencidos=sum(
                1 for i in itens_orm if i.classificacao_validade == NivelRisco.VENCIDO.value
            ),
            qtd_vence_hoje=sum(1 for i in itens_orm if i.dias_restantes == 0),
            qtd_urgentes=sum(
                1 for i in itens_orm if i.classificacao_validade == NivelRisco.URGENTE.value
            ),
            qtd_risco=sum(
                1 for i in itens_orm if i.classificacao_validade == NivelRisco.RISCO.value
            ),
            qtd_atencao=sum(
                1 for i in itens_orm if i.classificacao_validade == NivelRisco.ATENCAO.value
            ),
            valor_em_risco=sum(
                (i.valor_em_risco for i in itens_orm if i.valor_em_risco is not None),
                Decimal("0"),
            ),
            total_acoes_recomendadas=0,
            total_acoes_realizadas=0,
        )
        db.add(relatorio_orm)
        db.flush()  # popula relatorio_orm.id sem commitar, para vincular os itens

        for item_orm in itens_orm:
            item_orm.id_relatorio = relatorio_orm.id
            db.add(item_orm)

        db.commit()
    except Exception:
        db.rollback()
        raise

    db.refresh(relatorio_orm)
    return RelatorioAcaoDiario.model_validate(relatorio_orm, from_attributes=True)


def listar_itens(db: Session, id_mercado: int, id_relatorio: int) -> list[ItemRelatorioDiario]:
    """Lista os itens já persistidos de um relatório (RN05: só do mesmo
    mercado). Não chama gerar_ou_obter nem recalcula nada — só lê a
    fotografia já gravada."""
    relatorio_orm = (
        db.query(RelatorioAcaoDiarioORM)
        .filter(
            RelatorioAcaoDiarioORM.id == id_relatorio,
            RelatorioAcaoDiarioORM.id_mercado == id_mercado,
        )
        .first()
    )
    if relatorio_orm is None:
        # RN05: relatório inexistente ou de outro mercado levanta a mesma
        # exceção — não revela que um relatório de outro mercado existe.
        raise RelatorioNaoEncontrado(id_relatorio)

    itens_orm = (
        db.query(ItemRelatorioDiarioORM)
        .filter(ItemRelatorioDiarioORM.id_relatorio == id_relatorio)
        .order_by(ItemRelatorioDiarioORM.id)
        .all()
    )
    return [ItemRelatorioDiario.model_validate(item, from_attributes=True) for item in itens_orm]


def _montar_itens(db: Session, id_mercado: int, hoje: date) -> list[ItemRelatorioDiarioORM]:
    """Fotografia dos lotes acionáveis do mercado: confirmado + nivel_risco
    numa faixa de risco (RN01) + status_operacional disponível (RN06,
    decisão da Gestão Preventiva)."""
    lotes_orm = (
        db.query(LoteORM)
        .filter(LoteORM.id_mercado == id_mercado, LoteORM.status == StatusLote.CONFIRMADO)
        .all()
    )

    itens: list[ItemRelatorioDiarioORM] = []
    for lote_orm in lotes_orm:
        dias_restantes, nivel_risco = calcular_risco(lote_orm.data_validade, hoje=hoje)
        if nivel_risco not in NIVEIS_ACIONAVEIS:
            continue
        if lote_orm.status_operacional in STATUS_OPERACIONAIS_SEM_ACAO:
            continue

        if lote_orm.quantidade_disponivel is None:
            raise QuantidadeDisponivelInconsistente(
                f"lote {lote_orm.id}: quantidade_disponivel é None para um lote "
                "confirmado e acionável — inconsistência inesperada (RN06/Migration 0002)."
            )

        valor_em_risco = (
            None
            if lote_orm.preco_custo is None
            else lote_orm.preco_custo * lote_orm.quantidade_disponivel
        )

        itens.append(
            ItemRelatorioDiarioORM(
                id_produto=lote_orm.id_produto,
                id_lote=lote_orm.id,
                data_validade=lote_orm.data_validade,
                quantidade_disponivel=lote_orm.quantidade_disponivel,
                preco_custo=lote_orm.preco_custo,
                dias_restantes=dias_restantes,
                classificacao_validade=nivel_risco.value,
                prioridade=PRIORIDADE_POR_NIVEL[nivel_risco],
                valor_em_risco=valor_em_risco,
                acao_recomendada=ACAO_RECOMENDADA_POR_NIVEL[nivel_risco],
            )
        )
    return itens
