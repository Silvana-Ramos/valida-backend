"""Cadastro de lote persistido no PostgreSQL via SQLAlchemy.

Prévia x oficial (RN02/RN03): enquanto o lote está `pendente_confirmacao`,
`nivel_risco`/`dias_restantes` são apenas uma prévia, recalculada a cada
consulta — o valor gravado não é tratado como definitivo. O cálculo se
torna oficial somente em `confirmar`, quando é fixado no registro — a
partir daí só o futuro job diário (RN03, fase posterior) deve alterá-lo,
não a leitura.
"""

from datetime import date, datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy.orm import Session

from app.models.historico_acao import HistoricoAcaoORM
from app.models.lote import LoteORM
from app.models.mercado import MercadoORM
from app.schemas.enums import NivelRisco, OrigemCadastro, StatusLote, TipoAcao
from app.schemas.historico_acao import HistoricoAcao, OrigemAcao
from app.schemas.lote import Lote, LoteCreateRequest, LoteEditRequest
from app.services import produto_service

# RN01: fuso usado para "hoje" quando o mercado não tem `timezone`
# configurado (hoje a maioria, já que o campo nunca foi preenchido para
# esse fim) ou quando o valor salvo não é um fuso IANA reconhecido.
FUSO_PADRAO = "America/Sao_Paulo"


class LoteNaoEncontrado(Exception):
    pass


class AcaoInvalidaParaStatus(Exception):
    pass


def hoje_do_mercado(db: Session, id_mercado: int) -> date:
    """RN01: `dias_restantes`/`nivel_risco` nunca usam o relógio/fuso do
    servidor — sempre a data corrente no fuso do mercado dono do lote.
    Sem isso, um lote pode ser classificado como vencido (ou deixar de
    ser) horas antes/depois do que seria no horário local do comércio,
    perto da virada do dia."""
    return agora_do_mercado(db, id_mercado).date()


def agora_do_mercado(db: Session, id_mercado: int) -> datetime:
    """Mesma resolução de fuso horário de hoje_do_mercado (RN01), mas
    devolvendo o datetime completo — necessário para comparar contra um
    horário configurado (ex.: mercados.horario_relatorio_diario), não só
    a data. hoje_do_mercado reaproveita esta função, em vez de duplicar
    a resolução de fuso."""
    mercado_orm = db.get(MercadoORM, id_mercado)
    fuso = (mercado_orm.timezone if mercado_orm else None) or FUSO_PADRAO
    try:
        zona = ZoneInfo(fuso)
    except ZoneInfoNotFoundError:
        zona = ZoneInfo(FUSO_PADRAO)
    return datetime.now(zona)


def calcular_risco(data_validade: date, hoje: date | None = None) -> tuple[int, NivelRisco]:
    """Implementa a RN01. `hoje` deve vir de `hoje_do_mercado` — o default
    (`date.today()`, fuso do servidor) só existe para chamadas que ainda
    não têm um `id_mercado`/`Session` à mão (ex.: testes unitários)."""
    hoje = hoje or date.today()
    dias_restantes = (data_validade - hoje).days

    if dias_restantes < 0:
        nivel = NivelRisco.VENCIDO
    elif dias_restantes <= 3:
        nivel = NivelRisco.URGENTE
    elif dias_restantes <= 7:
        nivel = NivelRisco.RISCO
    elif dias_restantes <= 15:
        nivel = NivelRisco.ATENCAO
    else:
        nivel = NivelRisco.NORMAL
    return dias_restantes, nivel


def _registrar_historico(
    db: Session, id_mercado: int, id_lote: int, tipo_acao: TipoAcao, descricao: str
) -> None:
    historico_orm = HistoricoAcaoORM(
        id_mercado=id_mercado,
        id_lote=id_lote,
        tipo_acao=tipo_acao,
        descricao=descricao,
        origem=OrigemAcao.USUARIO,
        data_hora=datetime.now(),
    )
    db.add(historico_orm)
    db.commit()


def _para_schema(db: Session, lote_orm: LoteORM) -> Lote:
    """Converte LoteORM -> Lote, aplicando a prévia de risco se pendente."""
    dados = {
        "id": lote_orm.id,
        "id_mercado": lote_orm.id_mercado,
        "id_produto": lote_orm.id_produto,
        # Exposto pela API como estoque disponível atual (RN07), não o
        # valor de cadastro (`quantidade`) — sincronizados até a primeira
        # movimentação real de estoque, mas divergem a partir dela.
        "quantidade": lote_orm.quantidade_disponivel,
        "numero_lote": lote_orm.numero_lote,
        "data_validade": lote_orm.data_validade,
        "data_entrada": lote_orm.data_entrada,
        "origem_cadastro": lote_orm.origem_cadastro,
        "status": lote_orm.status,
        "status_operacional": lote_orm.status_operacional,
        "nivel_risco": lote_orm.nivel_risco,
        "dias_restantes": lote_orm.dias_restantes,
        "data_ultima_atualizacao": lote_orm.data_ultima_atualizacao,
        # criado_por é opcional no banco (sem autenticação real de usuário
        # ainda), mas obrigatório no contrato da API; 0 é o mesmo
        # placeholder já usado antes da persistência real.
        "criado_por": lote_orm.criado_por or 0,
        "preco_custo": lote_orm.preco_custo,
    }
    if lote_orm.status == StatusLote.PENDENTE_CONFIRMACAO:
        hoje = hoje_do_mercado(db, lote_orm.id_mercado)
        dias_restantes, nivel_risco = calcular_risco(lote_orm.data_validade, hoje=hoje)
        dados["dias_restantes"] = dias_restantes
        dados["nivel_risco"] = nivel_risco
    return Lote(**dados)


def criar_pendente(db: Session, id_mercado: int, request: LoteCreateRequest) -> Lote:
    produto, preco_venda_ignorado = produto_service.obter_ou_criar(
        db,
        id_mercado,
        request.produto_nome,
        preco_venda=request.preco_venda,
    )
    dias_restantes, nivel_risco = calcular_risco(
        request.data_validade, hoje=hoje_do_mercado(db, id_mercado)
    )
    agora = datetime.now()

    lote_orm = LoteORM(
        id_mercado=id_mercado,
        id_produto=produto.id,
        quantidade=request.quantidade,
        numero_lote=request.numero_lote,
        data_validade=request.data_validade,
        data_entrada=agora,
        origem_cadastro=OrigemCadastro.TEXTO,
        status=StatusLote.PENDENTE_CONFIRMACAO,
        nivel_risco=nivel_risco,
        dias_restantes=dias_restantes,
        data_ultima_atualizacao=agora,
        # NULL quando não informado (sem autenticação real ainda) — nunca um
        # id "placeholder" como 0, que violaria a FK para usuarios.
        criado_por=request.criado_por,
        preco_custo=request.preco_custo,
        status_operacional="disponivel",
        quantidade_disponivel=request.quantidade,
        quantidade_inicial=request.quantidade,
    )
    db.add(lote_orm)
    db.commit()
    db.refresh(lote_orm)

    descricao = (
        f"Lote criado com produto '{produto.nome}', quantidade {lote_orm.quantidade}, "
        f"validade {lote_orm.data_validade.isoformat()} (prévia: {nivel_risco.value})."
    )
    if lote_orm.preco_custo is not None:
        descricao += f" Custo deste lote: {lote_orm.preco_custo}."
    if preco_venda_ignorado:
        descricao += (
            " Preço de venda informado não foi aplicado ao produto: já existia um"
            " preço de venda cadastrado e a atualização é um fluxo próprio,"
            " ainda não implementado."
        )
    _registrar_historico(db, lote_orm.id_mercado, lote_orm.id, TipoAcao.CADASTRO, descricao)
    return _para_schema(db, lote_orm)


def obter(db: Session, id_mercado: int, id_lote: int) -> Lote:
    lote_orm = db.get(LoteORM, id_lote)
    if lote_orm is None or lote_orm.id_mercado != id_mercado:
        # RN05: lote de outro mercado é tratado como inexistente, não como
        # "proibido" — evita vazar a existência de lotes de outros mercados.
        raise LoteNaoEncontrado(id_lote)
    return _para_schema(db, lote_orm)


def listar(db: Session, id_mercado: int, status: StatusLote | None = None) -> list[Lote]:
    query = db.query(LoteORM).filter(LoteORM.id_mercado == id_mercado)
    if status is not None:
        query = query.filter(LoteORM.status == status)
    return [_para_schema(db, lote_orm) for lote_orm in query.all()]


def editar_pendente(
    db: Session, id_mercado: int, id_lote: int, request: LoteEditRequest
) -> Lote:
    lote_orm = db.get(LoteORM, id_lote)
    if lote_orm is None or lote_orm.id_mercado != id_mercado:
        raise LoteNaoEncontrado(id_lote)
    if lote_orm.status != StatusLote.PENDENTE_CONFIRMACAO:
        raise AcaoInvalidaParaStatus(lote_orm.status)

    if request.produto_nome is not None:
        produto, _ = produto_service.obter_ou_criar(db, lote_orm.id_mercado, request.produto_nome)
        lote_orm.id_produto = produto.id
    if request.quantidade is not None:
        lote_orm.quantidade = request.quantidade
        lote_orm.quantidade_disponivel = request.quantidade
        lote_orm.quantidade_inicial = request.quantidade
    if request.data_validade is not None:
        lote_orm.data_validade = request.data_validade
    if request.numero_lote is not None:
        lote_orm.numero_lote = request.numero_lote

    dias_restantes, nivel_risco = calcular_risco(
        lote_orm.data_validade, hoje=hoje_do_mercado(db, lote_orm.id_mercado)
    )
    lote_orm.dias_restantes = dias_restantes
    lote_orm.nivel_risco = nivel_risco
    lote_orm.data_ultima_atualizacao = datetime.now()

    db.commit()
    db.refresh(lote_orm)

    _registrar_historico(
        db,
        lote_orm.id_mercado,
        id_lote,
        TipoAcao.EDICAO,
        f"Lote editado (prévia atualizada: {nivel_risco.value}).",
    )
    return _para_schema(db, lote_orm)


def confirmar(db: Session, id_mercado: int, id_lote: int) -> Lote:
    lote_orm = db.get(LoteORM, id_lote)
    if lote_orm is None or lote_orm.id_mercado != id_mercado:
        raise LoteNaoEncontrado(id_lote)
    if lote_orm.status != StatusLote.PENDENTE_CONFIRMACAO:
        raise AcaoInvalidaParaStatus(lote_orm.status)

    dias_restantes, nivel_risco = calcular_risco(
        lote_orm.data_validade, hoje=hoje_do_mercado(db, lote_orm.id_mercado)
    )
    lote_orm.status = StatusLote.CONFIRMADO
    lote_orm.dias_restantes = dias_restantes
    lote_orm.nivel_risco = nivel_risco
    lote_orm.data_ultima_atualizacao = datetime.now()

    db.commit()
    db.refresh(lote_orm)

    _registrar_historico(
        db,
        lote_orm.id_mercado,
        id_lote,
        TipoAcao.CONFIRMACAO,
        f"Cadastro confirmado pelo usuário. Risco oficial consolidado: {nivel_risco.value}.",
    )
    return _para_schema(db, lote_orm)


def cancelar(db: Session, id_mercado: int, id_lote: int) -> None:
    lote_orm = db.get(LoteORM, id_lote)
    if lote_orm is None or lote_orm.id_mercado != id_mercado:
        raise LoteNaoEncontrado(id_lote)
    if lote_orm.status != StatusLote.PENDENTE_CONFIRMACAO:
        raise AcaoInvalidaParaStatus(lote_orm.status)

    db.delete(lote_orm)

    historico_orm = HistoricoAcaoORM(
        id_mercado=id_mercado,
        id_lote=id_lote,
        tipo_acao=TipoAcao.CANCELAMENTO,
        descricao=(
            "Cadastro pendente cancelado pelo usuário antes da confirmação;"
            " removido da lista operacional."
        ),
        origem=OrigemAcao.USUARIO,
        data_hora=datetime.now(),
    )
    db.add(historico_orm)
    db.commit()


def historico_do_lote(db: Session, id_mercado: int, id_lote: int) -> list[HistoricoAcao]:
    lote_orm = db.get(LoteORM, id_lote)
    if lote_orm is None or lote_orm.id_mercado != id_mercado:
        raise LoteNaoEncontrado(id_lote)

    query = (
        db.query(HistoricoAcaoORM)
        .filter(
            HistoricoAcaoORM.id_lote == id_lote,
            HistoricoAcaoORM.id_mercado == id_mercado,
        )
        .order_by(HistoricoAcaoORM.id)
    )
    return [HistoricoAcao.model_validate(h, from_attributes=True) for h in query.all()]
