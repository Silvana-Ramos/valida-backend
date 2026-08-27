"""Serviço de orquestração da pipeline de importação (RN07, item 6 de
"Ordem de implementação" em docs/modelo-dados.md).

MVP: só importação de **vendas** via CSV — reaproveita
`movimentacao_service.registrar_venda` linha a linha, sem duplicar a
lógica de saldo/lock/histórico. Entrada/retirada/ajuste via arquivo e
Excel ficam para uma fase futura.

Erro crítico (arquivo vazio/ilegível/sem colunas, arquivo já processado,
acima do limite de linhas) aborta a importação inteira antes de qualquer
linha ser processada. Erro de linha (produto/lote não encontrado, saldo
insuficiente, quantidade inválida, requer múltiplos lotes) fica isolado
naquela linha — o restante do arquivo continua.
"""

import hashlib
from datetime import datetime
from decimal import Decimal, InvalidOperation

from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.models.importacao import ImportacaoORM
from app.models.item_importacao import ItemImportacaoORM
from app.models.lote import LoteORM
from app.models.produto import ProdutoORM
from app.schemas.enums import StatusLote
from app.schemas.importacao import StatusImportacao, StatusProcessamentoItem
from app.schemas.movimentacao_estoque import OrigemMovimentacao, VendaEstoqueRequest
from app.services import movimentacao_service
from app.services.importacao_parser import ArquivoInvalido, parsear_csv
from app.services.lote_service import AcaoInvalidaParaStatus, LoteNaoEncontrado, hoje_do_mercado
from app.services.movimentacao_service import SaldoInsuficienteParaVenda

MAX_LINHAS_IMPORTACAO = 500


class ArquivoJaProcessado(Exception):
    pass


class ImportacaoNaoEncontrada(Exception):
    pass


class ProdutoNaoEncontradoNaImportacao(Exception):
    pass


class LoteNaoEncontradoNaImportacao(Exception):
    pass


# Exceções de linha: capturadas e gravadas em ItemImportacaoORM, nunca
# propagadas — um erro numa linha não pode interromper as demais.
ERROS_DE_LINHA = (
    ProdutoNaoEncontradoNaImportacao,
    LoteNaoEncontradoNaImportacao,
    InvalidOperation,
    ValidationError,
    LoteNaoEncontrado,
    AcaoInvalidaParaStatus,
    SaldoInsuficienteParaVenda,
)


def _resolver_produto(db: Session, id_mercado: int, texto_produto: str) -> ProdutoORM:
    texto = texto_produto.strip()
    produto_orm = (
        db.query(ProdutoORM)
        .filter(ProdutoORM.id_mercado == id_mercado, ProdutoORM.codigo_sistema_origem == texto)
        .first()
    )
    if produto_orm is None:
        produto_orm = (
            db.query(ProdutoORM)
            .filter(ProdutoORM.id_mercado == id_mercado, ProdutoORM.codigo_barras == texto)
            .first()
        )
    if produto_orm is None:
        produto_orm = (
            db.query(ProdutoORM)
            .filter(ProdutoORM.id_mercado == id_mercado, ProdutoORM.nome == texto)
            .first()
        )
    if produto_orm is None:
        raise ProdutoNaoEncontradoNaImportacao(texto)
    return produto_orm


def _resolver_lote(
    db: Session, id_mercado: int, id_produto: int, numero_lote: str, quantidade: Decimal
) -> LoteORM:
    if numero_lote:
        candidatos = (
            db.query(LoteORM)
            .filter(
                LoteORM.id_mercado == id_mercado,
                LoteORM.id_produto == id_produto,
                LoteORM.numero_lote == numero_lote,
                LoteORM.status == StatusLote.CONFIRMADO,
            )
            .all()
        )
        if len(candidatos) != 1:
            raise LoteNaoEncontradoNaImportacao(
                f"Lote '{numero_lote}' não encontrado ou ambíguo para este produto."
            )
        return candidatos[0]

    # Sem número de lote informado: FEFO de lote único (MVP — ver
    # docs/checkpoint-rn07-ajuste.md e a revisão de desenho da pipeline
    # para a limitação de não dividir a baixa entre múltiplos lotes ainda).
    candidatos = (
        db.query(LoteORM)
        .filter(
            LoteORM.id_mercado == id_mercado,
            LoteORM.id_produto == id_produto,
            LoteORM.status == StatusLote.CONFIRMADO,
            LoteORM.quantidade_disponivel > 0,
            LoteORM.data_validade >= hoje_do_mercado(db, id_mercado),
        )
        .order_by(LoteORM.data_validade.asc())
        .all()
    )
    for candidato in candidatos:
        if candidato.quantidade_disponivel >= quantidade:
            return candidato
    raise LoteNaoEncontradoNaImportacao(
        "Nenhum lote não vencido cobre sozinho a quantidade — "
        "requer múltiplos lotes, não suportado nesta fase."
    )


def _processar_linha(
    db: Session,
    id_mercado: int,
    linha_bruta: dict[str, str],
    referencia_externa: str,
    criado_por: int | None,
) -> tuple[StatusProcessamentoItem, str | None, int | None, int | None, int | None]:
    """Retorna (status, mensagem_erro, id_produto, id_lote, id_movimentacao)."""
    quantidade = Decimal(linha_bruta.get("quantidade", "").strip())
    produto_orm = _resolver_produto(db, id_mercado, linha_bruta.get("produto", ""))
    numero_lote = (linha_bruta.get("numero_lote") or "").strip()
    lote_orm = _resolver_lote(db, id_mercado, produto_orm.id, numero_lote, quantidade)

    request = VendaEstoqueRequest(quantidade=quantidade, criado_por=criado_por)
    movimentacao = movimentacao_service.registrar_venda(
        db,
        id_mercado,
        lote_orm.id,
        request,
        origem=OrigemMovimentacao.IMPORTACAO_EXTERNA,
        referencia_externa=referencia_externa,
    )

    return (
        StatusProcessamentoItem.PROCESSADA,
        None,
        produto_orm.id,
        lote_orm.id,
        movimentacao.id,
    )


def processar_arquivo_venda(
    db: Session,
    id_mercado: int,
    nome_arquivo: str,
    conteudo: bytes,
    criado_por: int | None = None,
) -> ImportacaoORM:
    hash_arquivo = hashlib.sha256(conteudo).hexdigest()

    ja_processado = (
        db.query(ImportacaoORM)
        .filter(ImportacaoORM.id_mercado == id_mercado, ImportacaoORM.hash_arquivo == hash_arquivo)
        .first()
    )
    if ja_processado is not None:
        raise ArquivoJaProcessado(ja_processado.id)

    linhas = parsear_csv(conteudo)  # ArquivoInvalido propaga — erro crítico
    if len(linhas) > MAX_LINHAS_IMPORTACAO:
        raise ArquivoInvalido(
            f"Arquivo com {len(linhas)} linhas excede o limite de "
            f"{MAX_LINHAS_IMPORTACAO} desta fase — divida o arquivo."
        )

    importacao_orm = ImportacaoORM(
        id_mercado=id_mercado,
        nome_arquivo=nome_arquivo,
        hash_arquivo=hash_arquivo,
        status=StatusImportacao.PROCESSANDO,
        total_linhas=len(linhas),
        criado_por=criado_por,
    )
    db.add(importacao_orm)
    db.commit()
    db.refresh(importacao_orm)

    total_processadas = 0
    total_duplicadas = 0
    total_com_erro = 0

    for numero_linha, linha_bruta in enumerate(linhas, start=1):
        referencia_externa = (linha_bruta.get("referencia_externa") or "").strip()

        item_orm = ItemImportacaoORM(
            id_importacao=importacao_orm.id,
            id_mercado=id_mercado,
            numero_linha=numero_linha,
            referencia_externa=referencia_externa,
            dados_brutos=linha_bruta,
            status_processamento=StatusProcessamentoItem.PENDENTE,
        )

        if not referencia_externa:
            item_orm.status_processamento = StatusProcessamentoItem.ERRO
            item_orm.mensagem_erro = "referencia_externa vazia."
            total_com_erro += 1
        else:
            duplicada = (
                db.query(ItemImportacaoORM)
                .filter(
                    ItemImportacaoORM.id_mercado == id_mercado,
                    ItemImportacaoORM.referencia_externa == referencia_externa,
                )
                .first()
            )
            if duplicada is not None:
                item_orm.status_processamento = StatusProcessamentoItem.DUPLICADA
                total_duplicadas += 1
            else:
                try:
                    (
                        item_orm.status_processamento,
                        item_orm.mensagem_erro,
                        item_orm.id_produto,
                        item_orm.id_lote,
                        item_orm.id_movimentacao,
                    ) = _processar_linha(
                        db, id_mercado, linha_bruta, referencia_externa, criado_por
                    )
                    total_processadas += 1
                except ERROS_DE_LINHA as exc:
                    item_orm.status_processamento = StatusProcessamentoItem.ERRO
                    item_orm.mensagem_erro = str(exc)
                    total_com_erro += 1

        db.add(item_orm)
        db.commit()

    importacao_orm.total_processadas = total_processadas
    importacao_orm.total_duplicadas = total_duplicadas
    importacao_orm.total_com_erro = total_com_erro
    importacao_orm.status = (
        StatusImportacao.CONCLUIDA
        if total_com_erro == 0 and total_duplicadas == 0
        else StatusImportacao.CONCLUIDA_COM_ERROS
    )
    importacao_orm.data_hora_fim = datetime.now()
    db.commit()
    db.refresh(importacao_orm)
    return importacao_orm


def obter_importacao(db: Session, id_mercado: int, id_importacao: int) -> ImportacaoORM:
    importacao_orm = db.get(ImportacaoORM, id_importacao)
    if importacao_orm is None or importacao_orm.id_mercado != id_mercado:
        # RN05: importação de outro mercado é tratada como inexistente,
        # não como "proibida" — mesmo critério já usado para lotes.
        raise ImportacaoNaoEncontrada(id_importacao)
    return importacao_orm


def listar_itens_importacao(
    db: Session, id_mercado: int, id_importacao: int
) -> list[ItemImportacaoORM]:
    obter_importacao(db, id_mercado, id_importacao)  # valida existência/isolamento
    return (
        db.query(ItemImportacaoORM)
        .filter(
            ItemImportacaoORM.id_importacao == id_importacao,
            ItemImportacaoORM.id_mercado == id_mercado,
        )
        .order_by(ItemImportacaoORM.numero_linha)
        .all()
    )
