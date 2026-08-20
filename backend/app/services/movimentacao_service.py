"""Serviço de movimentações de estoque (RN07).

Implementa `entrada`, `venda`, `retirada` e `ajuste`. Cada chamada roda
numa única transação: `SELECT ... FOR UPDATE` trava o lote (e, em
`ajuste` com estorno, também a movimentação referenciada), a movimentação
e o histórico são gravados na mesma sessão, e um único `db.commit()` no
final cobre as escritas (lote, `movimentacoes_estoque`, `historico_acoes`)
— conforme a regra de concorrência da RN07 e RN04 (rastreabilidade).
"""

from datetime import datetime

from sqlalchemy.orm import Session

from app.models.historico_acao import HistoricoAcaoORM
from app.models.lote import LoteORM
from app.models.movimentacao_estoque import MovimentacaoEstoqueORM
from app.schemas.enums import StatusLote, TipoAcao
from app.schemas.historico_acao import OrigemAcao
from app.schemas.movimentacao_estoque import (
    AjusteEstoqueRequest,
    EntradaEstoqueRequest,
    MovimentacaoEstoque,
    OrigemMovimentacao,
    RetiradaEstoqueRequest,
    SentidoMovimentacao,
    TipoMovimentacao,
    VendaEstoqueRequest,
)
from app.services.lote_service import AcaoInvalidaParaStatus, LoteNaoEncontrado, calcular_risco

STATUS_OPERACIONAL_DISPONIVEL = "disponivel"
STATUS_OPERACIONAL_ESGOTADO = "esgotado"
STATUS_OPERACIONAL_DESCARTADO = "descartado"


class LoteDescartadoNaoAceitaEntrada(Exception):
    pass


class SaldoInsuficienteParaVenda(Exception):
    pass


class LoteNaoVencidoNaoAceitaRetirada(Exception):
    pass


class SaldoInsuficienteParaRetirada(Exception):
    pass


class SaldoInsuficienteParaAjuste(Exception):
    pass


class MovimentacaoEstornadaNaoEncontrada(Exception):
    pass


class MovimentacaoJaEstornada(Exception):
    pass


def registrar_entrada(
    db: Session, id_mercado: int, id_lote: int, request: EntradaEstoqueRequest
) -> MovimentacaoEstoque:
    """Entrada de estoque sobre um lote confirmado (RN07 + adendo de
    2026-08-18 em docs/regras-negocio.md): lote `disponivel` continua
    `disponivel`; lote `esgotado` volta a `disponivel`; lote `descartado`
    rejeita a entrada. Só `quantidade_disponivel` muda — `quantidade_inicial`
    nunca é tocada.

    `id_mercado` deve vir de uma fonte confiável (sessão/autenticação do
    chamador, não do corpo da requisição) — RN05 exige isolamento entre
    mercados; um lote de outro mercado é tratado como inexistente."""
    try:
        # populate_existing=True evita que Session.get() devolva um objeto
        # já presente no identity map (de uma query anterior sem lock) sem
        # de fato reemitir o SELECT ... FOR UPDATE — armadilha documentada
        # do SQLAlchemy.
        lote_orm = db.get(LoteORM, id_lote, with_for_update=True, populate_existing=True)
        if lote_orm is None or lote_orm.id_mercado != id_mercado:
            # RN05: lote de outro mercado é tratado como inexistente, não
            # como "proibido" — evita vazar a existência de lotes de
            # outros mercados.
            raise LoteNaoEncontrado(id_lote)
        if lote_orm.status != StatusLote.CONFIRMADO:
            raise AcaoInvalidaParaStatus(lote_orm.status)
        if lote_orm.status_operacional == STATUS_OPERACIONAL_DESCARTADO:
            raise LoteDescartadoNaoAceitaEntrada(id_lote)

        quantidade_anterior = lote_orm.quantidade_disponivel
        quantidade_movimentada = request.quantidade
        quantidade_resultante = quantidade_anterior + quantidade_movimentada

        lote_orm.quantidade_disponivel = quantidade_resultante
        lote_orm.status_operacional = STATUS_OPERACIONAL_DISPONIVEL
        lote_orm.data_ultima_atualizacao = datetime.now()

        movimentacao_orm = MovimentacaoEstoqueORM(
            id_mercado=lote_orm.id_mercado,
            id_lote=lote_orm.id,
            tipo_movimentacao=TipoMovimentacao.ENTRADA,
            quantidade_movimentada=quantidade_movimentada,
            quantidade_anterior=quantidade_anterior,
            quantidade_resultante=quantidade_resultante,
            origem=OrigemMovimentacao.USUARIO,
            criado_por=request.criado_por,
            data_hora=datetime.now(),
        )
        db.add(movimentacao_orm)

        historico_orm = HistoricoAcaoORM(
            id_mercado=lote_orm.id_mercado,
            id_lote=lote_orm.id,
            tipo_acao=TipoAcao.ENTRADA,
            descricao=(
                f"Entrada de estoque: +{quantidade_movimentada} "
                f"(saldo {quantidade_anterior} -> {quantidade_resultante})."
            ),
            origem=OrigemAcao.USUARIO,
            data_hora=datetime.now(),
            quantidade_anterior=quantidade_anterior,
            quantidade_movimentada=quantidade_movimentada,
            quantidade_resultante=quantidade_resultante,
        )
        db.add(historico_orm)

        db.commit()
    except Exception:
        db.rollback()
        raise

    db.refresh(movimentacao_orm)
    return MovimentacaoEstoque.model_validate(movimentacao_orm, from_attributes=True)


def registrar_venda(
    db: Session,
    id_mercado: int,
    id_lote: int,
    request: VendaEstoqueRequest,
    origem: OrigemMovimentacao = OrigemMovimentacao.USUARIO,
    referencia_externa: str | None = None,
) -> MovimentacaoEstoque:
    """Venda de estoque sobre um lote confirmado (RN07): venda parcial
    mantém `status_operacional = disponivel`; venda que zera o saldo muda
    para `esgotado`. Saldo insuficiente é rejeitado sem gravar nada — isso
    também cobre, sem checagem separada, lote já `esgotado` ou `descartado`
    (ambos sempre têm `quantidade_disponivel = 0`, RN07). Só
    `quantidade_disponivel` muda — `quantidade_inicial` nunca é tocada.

    `id_mercado` deve vir de uma fonte confiável (sessão/autenticação do
    chamador, não do corpo da requisição) — RN05 exige isolamento entre
    mercados; um lote de outro mercado é tratado como inexistente.

    `origem`/`referencia_externa` são opcionais e retrocompatíveis (padrão
    `usuario`/`None`, igual ao comportamento anterior) — usados pela
    pipeline de importação (RN07, item 6) para marcar a movimentação como
    `importacao_externa` com a referência da linha do arquivo. O `CHECK`
    do banco (`origem != 'importacao_externa' OR referencia_externa IS
    NOT NULL`) é conferido aqui antes de qualquer escrita, para falhar com
    uma mensagem clara em vez de um erro de banco cru."""
    if origem == OrigemMovimentacao.IMPORTACAO_EXTERNA and not referencia_externa:
        raise ValueError(
            "referencia_externa é obrigatória quando origem = importacao_externa."
        )
    try:
        # populate_existing=True evita que Session.get() devolva um objeto
        # já presente no identity map (de uma query anterior sem lock) sem
        # de fato reemitir o SELECT ... FOR UPDATE — armadilha documentada
        # do SQLAlchemy.
        lote_orm = db.get(LoteORM, id_lote, with_for_update=True, populate_existing=True)
        if lote_orm is None or lote_orm.id_mercado != id_mercado:
            # RN05: lote de outro mercado é tratado como inexistente, não
            # como "proibido" — evita vazar a existência de lotes de
            # outros mercados.
            raise LoteNaoEncontrado(id_lote)
        if lote_orm.status != StatusLote.CONFIRMADO:
            raise AcaoInvalidaParaStatus(lote_orm.status)

        quantidade_anterior = lote_orm.quantidade_disponivel
        quantidade_movimentada = request.quantidade
        if quantidade_movimentada > quantidade_anterior:
            raise SaldoInsuficienteParaVenda(id_lote)
        quantidade_resultante = quantidade_anterior - quantidade_movimentada

        lote_orm.quantidade_disponivel = quantidade_resultante
        lote_orm.status_operacional = (
            STATUS_OPERACIONAL_ESGOTADO
            if quantidade_resultante == 0
            else STATUS_OPERACIONAL_DISPONIVEL
        )
        lote_orm.data_ultima_atualizacao = datetime.now()

        movimentacao_orm = MovimentacaoEstoqueORM(
            id_mercado=lote_orm.id_mercado,
            id_lote=lote_orm.id,
            tipo_movimentacao=TipoMovimentacao.VENDA,
            quantidade_movimentada=quantidade_movimentada,
            quantidade_anterior=quantidade_anterior,
            quantidade_resultante=quantidade_resultante,
            origem=origem,
            referencia_externa=referencia_externa,
            criado_por=request.criado_por,
            data_hora=datetime.now(),
        )
        db.add(movimentacao_orm)

        historico_orm = HistoricoAcaoORM(
            id_mercado=lote_orm.id_mercado,
            id_lote=lote_orm.id,
            tipo_acao=TipoAcao.VENDA,
            descricao=(
                f"Venda de estoque: -{quantidade_movimentada} "
                f"(saldo {quantidade_anterior} -> {quantidade_resultante})."
            ),
            origem=OrigemAcao.USUARIO,
            data_hora=datetime.now(),
            quantidade_anterior=quantidade_anterior,
            quantidade_movimentada=quantidade_movimentada,
            quantidade_resultante=quantidade_resultante,
        )
        db.add(historico_orm)

        db.commit()
    except Exception:
        db.rollback()
        raise

    db.refresh(movimentacao_orm)
    return MovimentacaoEstoque.model_validate(movimentacao_orm, from_attributes=True)


def registrar_retirada(
    db: Session, id_mercado: int, id_lote: int, request: RetiradaEstoqueRequest
) -> MovimentacaoEstoque:
    """Retirada de produto vencido sobre um lote confirmado (RN07): exige
    que o lote esteja de fato vencido — `dias_restantes` é recalculado na
    hora via `lote_service.calcular_risco(lote_orm.data_validade)`, nunca
    confiando em `nivel_risco`/`dias_restantes` persistidos (só oficiais
    até o próximo job diário, RN03). Retirada parcial mantém
    `status_operacional = disponivel`; retirada que zera o saldo muda para
    `descartado` (não `esgotado` — esse é o destino exclusivo de `venda`).
    Saldo insuficiente é rejeitado sem gravar nada — isso também cobre,
    sem checagem separada, lote já `esgotado` ou `descartado` (ambos
    sempre têm `quantidade_disponivel = 0`, RN07). Só
    `quantidade_disponivel` muda — `quantidade_inicial` nunca é tocada.

    `id_mercado` deve vir de uma fonte confiável (sessão/autenticação do
    chamador, não do corpo da requisição) — RN05 exige isolamento entre
    mercados; um lote de outro mercado é tratado como inexistente."""
    try:
        # populate_existing=True evita que Session.get() devolva um objeto
        # já presente no identity map (de uma query anterior sem lock) sem
        # de fato reemitir o SELECT ... FOR UPDATE — armadilha documentada
        # do SQLAlchemy.
        lote_orm = db.get(LoteORM, id_lote, with_for_update=True, populate_existing=True)
        if lote_orm is None or lote_orm.id_mercado != id_mercado:
            # RN05: lote de outro mercado é tratado como inexistente, não
            # como "proibido" — evita vazar a existência de lotes de
            # outros mercados.
            raise LoteNaoEncontrado(id_lote)
        if lote_orm.status != StatusLote.CONFIRMADO:
            raise AcaoInvalidaParaStatus(lote_orm.status)

        dias_restantes, _ = calcular_risco(lote_orm.data_validade)
        if dias_restantes >= 0:
            raise LoteNaoVencidoNaoAceitaRetirada(id_lote)

        quantidade_anterior = lote_orm.quantidade_disponivel
        quantidade_movimentada = request.quantidade
        if quantidade_movimentada > quantidade_anterior:
            raise SaldoInsuficienteParaRetirada(id_lote)
        quantidade_resultante = quantidade_anterior - quantidade_movimentada

        lote_orm.quantidade_disponivel = quantidade_resultante
        lote_orm.status_operacional = (
            STATUS_OPERACIONAL_DESCARTADO
            if quantidade_resultante == 0
            else STATUS_OPERACIONAL_DISPONIVEL
        )
        lote_orm.data_ultima_atualizacao = datetime.now()

        movimentacao_orm = MovimentacaoEstoqueORM(
            id_mercado=lote_orm.id_mercado,
            id_lote=lote_orm.id,
            tipo_movimentacao=TipoMovimentacao.RETIRADA,
            quantidade_movimentada=quantidade_movimentada,
            quantidade_anterior=quantidade_anterior,
            quantidade_resultante=quantidade_resultante,
            origem=OrigemMovimentacao.USUARIO,
            criado_por=request.criado_por,
            data_hora=datetime.now(),
        )
        db.add(movimentacao_orm)

        historico_orm = HistoricoAcaoORM(
            id_mercado=lote_orm.id_mercado,
            id_lote=lote_orm.id,
            tipo_acao=TipoAcao.RETIRADA_VENCIMENTO,
            descricao=(
                f"Retirada por vencimento: -{quantidade_movimentada} "
                f"(saldo {quantidade_anterior} -> {quantidade_resultante})."
            ),
            origem=OrigemAcao.USUARIO,
            data_hora=datetime.now(),
            quantidade_anterior=quantidade_anterior,
            quantidade_movimentada=quantidade_movimentada,
            quantidade_resultante=quantidade_resultante,
        )
        db.add(historico_orm)

        db.commit()
    except Exception:
        db.rollback()
        raise

    db.refresh(movimentacao_orm)
    return MovimentacaoEstoque.model_validate(movimentacao_orm, from_attributes=True)


def registrar_ajuste(
    db: Session, id_mercado: int, id_lote: int, request: AjusteEstoqueRequest
) -> MovimentacaoEstoque:
    """Ajuste de estoque (correção/estorno) sobre um lote confirmado
    (RN07): nunca altera ou remove a movimentação original — sempre uma
    nova linha, com `sentido` e, opcionalmente, `id_movimentacao_estornada`.

    `sentido = entrada` segue a mesma regra de `entrada`: lote `esgotado`
    reativa para `disponivel`; lote `descartado` rejeita (reaproveita
    `LoteDescartadoNaoAceitaEntrada`). `sentido = saida` segue a mesma
    regra de `venda`: saldo insuficiente é rejeitado; saldo zerado muda
    `status_operacional` para `esgotado` (nunca `descartado` — exclusivo
    de `retirada`).

    Quando `id_movimentacao_estornada` é informado, a movimentação
    referenciada é travada (`SELECT ... FOR UPDATE`) antes de validar que
    existe no mesmo lote/mercado e que ainda não foi estornada por
    nenhuma outra linha — o lock serializa tentativas concorrentes de
    estornar a mesma movimentação duas vezes.

    Só `quantidade_disponivel` muda — `quantidade_inicial` nunca é tocada.

    `id_mercado` deve vir de uma fonte confiável (sessão/autenticação do
    chamador, não do corpo da requisição) — RN05 exige isolamento entre
    mercados; um lote de outro mercado é tratado como inexistente."""
    try:
        # populate_existing=True evita que Session.get() devolva um objeto
        # já presente no identity map (de uma query anterior sem lock) sem
        # de fato reemitir o SELECT ... FOR UPDATE — armadilha documentada
        # do SQLAlchemy.
        lote_orm = db.get(LoteORM, id_lote, with_for_update=True, populate_existing=True)
        if lote_orm is None or lote_orm.id_mercado != id_mercado:
            # RN05: lote de outro mercado é tratado como inexistente, não
            # como "proibido" — evita vazar a existência de lotes de
            # outros mercados.
            raise LoteNaoEncontrado(id_lote)
        if lote_orm.status != StatusLote.CONFIRMADO:
            raise AcaoInvalidaParaStatus(lote_orm.status)

        if request.id_movimentacao_estornada is not None:
            movimentacao_estornada_orm = db.get(
                MovimentacaoEstoqueORM,
                request.id_movimentacao_estornada,
                with_for_update=True,
                populate_existing=True,
            )
            if (
                movimentacao_estornada_orm is None
                or movimentacao_estornada_orm.id_mercado != id_mercado
                or movimentacao_estornada_orm.id_lote != id_lote
            ):
                raise MovimentacaoEstornadaNaoEncontrada(request.id_movimentacao_estornada)

            ja_estornada = (
                db.query(MovimentacaoEstoqueORM)
                .filter(
                    MovimentacaoEstoqueORM.id_movimentacao_estornada
                    == request.id_movimentacao_estornada
                )
                .first()
            )
            if ja_estornada is not None:
                raise MovimentacaoJaEstornada(request.id_movimentacao_estornada)

        quantidade_anterior = lote_orm.quantidade_disponivel
        quantidade_movimentada = request.quantidade

        if request.sentido == SentidoMovimentacao.ENTRADA:
            if lote_orm.status_operacional == STATUS_OPERACIONAL_DESCARTADO:
                raise LoteDescartadoNaoAceitaEntrada(id_lote)
            quantidade_resultante = quantidade_anterior + quantidade_movimentada
            status_operacional_novo = STATUS_OPERACIONAL_DISPONIVEL
        else:
            if quantidade_movimentada > quantidade_anterior:
                raise SaldoInsuficienteParaAjuste(id_lote)
            quantidade_resultante = quantidade_anterior - quantidade_movimentada
            status_operacional_novo = (
                STATUS_OPERACIONAL_ESGOTADO
                if quantidade_resultante == 0
                else STATUS_OPERACIONAL_DISPONIVEL
            )

        lote_orm.quantidade_disponivel = quantidade_resultante
        lote_orm.status_operacional = status_operacional_novo
        lote_orm.data_ultima_atualizacao = datetime.now()

        sinal = "+" if request.sentido == SentidoMovimentacao.ENTRADA else "-"
        movimentacao_orm = MovimentacaoEstoqueORM(
            id_mercado=lote_orm.id_mercado,
            id_lote=lote_orm.id,
            tipo_movimentacao=TipoMovimentacao.AJUSTE,
            sentido=request.sentido,
            quantidade_movimentada=quantidade_movimentada,
            quantidade_anterior=quantidade_anterior,
            quantidade_resultante=quantidade_resultante,
            origem=OrigemMovimentacao.USUARIO,
            id_movimentacao_estornada=request.id_movimentacao_estornada,
            criado_por=request.criado_por,
            data_hora=datetime.now(),
        )
        db.add(movimentacao_orm)

        historico_orm = HistoricoAcaoORM(
            id_mercado=lote_orm.id_mercado,
            id_lote=lote_orm.id,
            tipo_acao=TipoAcao.AJUSTE,
            descricao=(
                f"Ajuste de estoque ({request.sentido.value}): "
                f"{sinal}{quantidade_movimentada} "
                f"(saldo {quantidade_anterior} -> {quantidade_resultante})."
            ),
            origem=OrigemAcao.USUARIO,
            data_hora=datetime.now(),
            quantidade_anterior=quantidade_anterior,
            quantidade_movimentada=quantidade_movimentada,
            quantidade_resultante=quantidade_resultante,
        )
        db.add(historico_orm)

        db.commit()
    except Exception:
        db.rollback()
        raise

    db.refresh(movimentacao_orm)
    return MovimentacaoEstoque.model_validate(movimentacao_orm, from_attributes=True)
