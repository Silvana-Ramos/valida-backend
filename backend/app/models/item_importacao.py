from typing import Any, Optional

from sqlalchemy import Enum, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.schemas.importacao import StatusProcessamentoItem


class ItemImportacaoORM(Base):
    __tablename__ = "itens_importacao"

    id: Mapped[int] = mapped_column(primary_key=True)
    # Sem ForeignKey simples: o único vínculo real no banco é a FK composta
    # fk_itens_importacao_mercado (id_importacao, id_mercado) ->
    # importacoes(id, id_mercado), criada na Migration 0003 — mesmo padrão
    # já usado em MovimentacaoEstoqueORM.id_lote/id_importacao.
    id_importacao: Mapped[int] = mapped_column(Integer, nullable=False)
    id_mercado: Mapped[int] = mapped_column(ForeignKey("mercados.id"), nullable=False)
    numero_linha: Mapped[int] = mapped_column(Integer, nullable=False)
    referencia_externa: Mapped[str] = mapped_column(String, nullable=False)
    id_produto: Mapped[Optional[int]] = mapped_column(ForeignKey("produtos.id"), nullable=True)
    # Sem ForeignKey simples pelo mesmo motivo de id_importacao: só existe
    # via FK composta fk_itens_lote_mercado (id_lote, id_mercado) ->
    # lotes(id, id_mercado).
    id_lote: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    # Idem: fk_itens_movimentacao_mercado (id_movimentacao, id_mercado) ->
    # movimentacoes_estoque(id, id_mercado).
    id_movimentacao: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    status_processamento: Mapped[StatusProcessamentoItem] = mapped_column(
        Enum(
            StatusProcessamentoItem,
            name="status_processamento_item",
            values_callable=lambda enum_cls: [e.value for e in enum_cls],
        ),
        nullable=False,
    )
    mensagem_erro: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # Linha original do arquivo, para auditoria (RN07/Documento Mestre).
    dados_brutos: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
