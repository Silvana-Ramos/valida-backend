from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, Numeric, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.schemas.enums import TipoAcao
from app.schemas.historico_acao import OrigemAcao


class HistoricoAcaoORM(Base):
    __tablename__ = "historico_acoes"

    id: Mapped[int] = mapped_column(primary_key=True)
    id_mercado: Mapped[int] = mapped_column(ForeignKey("mercados.id"), nullable=False)
    # Proposital: SEM ForeignKey. Precisa continuar referenciando um lote já
    # removido da tabela `lotes` (cancelamento, RN02) — só indexado para
    # consulta, sem integridade referencial imposta pelo banco.
    id_lote: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, index=True)
    tipo_acao: Mapped[TipoAcao] = mapped_column(
        Enum(
            TipoAcao,
            name="tipo_acao",
            values_callable=lambda enum_cls: [e.value for e in enum_cls],
        ),
        nullable=False,
    )
    descricao: Mapped[str] = mapped_column(Text, nullable=False)
    origem: Mapped[OrigemAcao] = mapped_column(
        Enum(
            OrigemAcao,
            name="origem_acao",
            values_callable=lambda enum_cls: [e.value for e in enum_cls],
        ),
        nullable=False,
    )
    data_hora: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )
    # Migration 0003 (RN07): preenchidas somente quando a ação altera
    # efetivamente o estoque (entrada, venda, retirada_vencimento, ajuste,
    # ou correcao que altere quantidade_disponivel); NULL em qualquer
    # outra ação.
    quantidade_anterior: Mapped[Optional[Decimal]] = mapped_column(Numeric(14, 3), nullable=True)
    quantidade_movimentada: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(14, 3), nullable=True
    )
    quantidade_resultante: Mapped[Optional[Decimal]] = mapped_column(Numeric(14, 3), nullable=True)
