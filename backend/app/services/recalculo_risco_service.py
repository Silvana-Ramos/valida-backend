"""Recálculo diário do nível de risco (RN03). Roda como job de sistema,
via `backend/scripts/recalcular_risco_diario.py` — percorre todos os
lotes confirmados de todos os mercados, sem escopo de `id_mercado`: não
é uma requisição em nome de nenhum mercado, é uma rotina de manutenção.
RN05 protege contra vazamento entre mercados numa consulta feita em
nome de alguém; não se aplica aqui, já que cada lote continua sendo
processado isoladamente, um de cada vez.

`dias_restantes`/`data_ultima_atualizacao` são atualizados em toda
execução, para todo lote confirmado. `historico_acoes` só recebe um
registro novo quando `nivel_risco` muda de faixa em relação ao valor já
persistido (RN03) — por isso o job é naturalmente idempotente: rodar
duas vezes no mesmo dia não duplica histórico, porque a segunda vez já
não encontra mudança nenhuma.

Cada lote é travado (`SELECT ... FOR UPDATE`) e commitado
individualmente, não numa transação única para o job inteiro — um erro
num lote fica registrado no resumo e não impede os demais de serem
processados."""

from dataclasses import dataclass, field
from datetime import datetime

from sqlalchemy.orm import Session

from app.models.historico_acao import HistoricoAcaoORM
from app.models.lote import LoteORM
from app.schemas.enums import StatusLote, TipoAcao
from app.schemas.historico_acao import OrigemAcao
from app.services.lote_service import calcular_risco, hoje_do_mercado


@dataclass
class ResumoRecalculo:
    total_processados: int = 0
    total_mudaram_faixa: int = 0
    erros: list[str] = field(default_factory=list)


def recalcular_todos(db: Session) -> ResumoRecalculo:
    resumo = ResumoRecalculo()

    ids_confirmados = [
        id_lote
        for (id_lote,) in (
            db.query(LoteORM.id).filter(LoteORM.status == StatusLote.CONFIRMADO).all()
        )
    ]

    for id_lote in ids_confirmados:
        try:
            mudou_faixa = _recalcular_um(db, id_lote)
        except Exception as exc:
            db.rollback()
            resumo.erros.append(f"lote {id_lote}: {exc}")
            continue
        if mudou_faixa is None:
            continue  # lote não estava mais confirmado nesse instante — nada a fazer
        resumo.total_processados += 1
        if mudou_faixa:
            resumo.total_mudaram_faixa += 1

    return resumo


def _recalcular_um(db: Session, id_lote: int) -> bool | None:
    # populate_existing=True evita que Session.get() devolva um objeto já
    # presente no identity map (de uma query anterior sem lock) sem de
    # fato reemitir o SELECT ... FOR UPDATE — mesma armadilha documentada
    # em movimentacao_service.py.
    lote_orm = db.get(LoteORM, id_lote, with_for_update=True, populate_existing=True)
    if lote_orm is None or lote_orm.status != StatusLote.CONFIRMADO:
        # Nunca deveria acontecer na prática (um lote confirmado nunca é
        # removido nem muda de status), mas defensivo contra a corrida
        # teórica entre a listagem e este ponto.
        db.rollback()
        return None

    # RN01: "hoje" é resolvido por lote, a partir do fuso do mercado dono
    # do lote — não existe um "hoje" único para a execução inteira do
    # job, já que mercados diferentes podem estar em fusos diferentes.
    hoje = hoje_do_mercado(db, lote_orm.id_mercado)
    dias_restantes, nivel_risco_novo = calcular_risco(lote_orm.data_validade, hoje=hoje)
    nivel_risco_anterior = lote_orm.nivel_risco

    lote_orm.dias_restantes = dias_restantes
    lote_orm.data_ultima_atualizacao = datetime.now()

    mudou_faixa = nivel_risco_novo != nivel_risco_anterior
    if mudou_faixa:
        lote_orm.nivel_risco = nivel_risco_novo
        db.add(
            HistoricoAcaoORM(
                id_mercado=lote_orm.id_mercado,
                id_lote=lote_orm.id,
                tipo_acao=TipoAcao.STATUS_ALTERADO,
                descricao=(
                    f"Recálculo diário: nível de risco mudou de {nivel_risco_anterior.value} "
                    f"para {nivel_risco_novo.value} ({dias_restantes} dia(s) restante(s))."
                ),
                origem=OrigemAcao.SISTEMA,
                data_hora=datetime.now(),
            )
        )

    db.commit()
    return mudou_faixa
