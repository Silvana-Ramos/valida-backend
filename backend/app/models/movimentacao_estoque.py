from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.schemas.movimentacao_estoque import (
    OrigemMovimentacao,
    SentidoMovimentacao,
    TipoMovimentacao,
)


class MovimentacaoEstoqueORM(Base):
    __tablename__ = "movimentacoes_estoque"

    id: Mapped[int] = mapped_column(primary_key=True)
    id_mercado: Mapped[int] = mapped_column(ForeignKey("mercados.id"), nullable=False)
    # Sem ForeignKey simples: o único vínculo real no banco é a FK composta
    # fk_movimentacoes_lote_mercado (id_lote, id_mercado) -> lotes(id,
    # id_mercado), criada na Migration 0003 para isolamento por mercado
    # (RN05) — não existe FK simples id_lote -> lotes.id.
    id_lote: Mapped[int] = mapped_column(Integer, nullable=False)
    # Sem ForeignKey: `importacoes` ainda não tem ORM próprio (pipeline de
    # importação é fase futura separada, docs/modelo-dados.md). A FK
    # composta real já existe no banco desde a Migration 0003.
    id_importacao: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    tipo_movimentacao: Mapped[TipoMovimentacao] = mapped_column(
        Enum(
            TipoMovimentacao,
            name="tipo_movimentacao",
            values_callable=lambda enum_cls: [e.value for e in enum_cls],
        ),
        nullable=False,
    )
    # Só preenchido quando tipo_movimentacao = ajuste (RN07).
    sentido: Mapped[Optional[SentidoMovimentacao]] = mapped_column(
        Enum(
            SentidoMovimentacao,
            name="sentido_movimentacao",
            values_callable=lambda enum_cls: [e.value for e in enum_cls],
        ),
        nullable=True,
    )
    quantidade_movimentada: Mapped[Decimal] = mapped_column(Numeric(14, 3), nullable=False)
    quantidade_anterior: Mapped[Decimal] = mapped_column(Numeric(14, 3), nullable=False)
    quantidade_resultante: Mapped[Decimal] = mapped_column(Numeric(14, 3), nullable=False)
    origem: Mapped[OrigemMovimentacao] = mapped_column(
        Enum(
            OrigemMovimentacao,
            name="origem_movimentacao",
            values_callable=lambda enum_cls: [e.value for e in enum_cls],
        ),
        nullable=False,
    )
    referencia_externa: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    # Autorreferenciada; só preenchida quando tipo_movimentacao = ajuste
    # (RN07). Sem ForeignKey simples pelo mesmo motivo de id_lote acima: o
    # vínculo real é a FK composta fk_movimentacoes_estornada_mercado
    # (id_movimentacao_estornada, id_mercado) -> movimentacoes_estoque(id,
    # id_mercado).
    id_movimentacao_estornada: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    criado_por: Mapped[Optional[int]] = mapped_column(ForeignKey("usuarios.id"), nullable=True)
    data_hora: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )
