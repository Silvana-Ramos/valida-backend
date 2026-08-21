from datetime import datetime, time
from decimal import Decimal
from typing import Optional

from sqlalchemy import Boolean, DateTime, Enum, Numeric, String, Time, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.schemas.mercado import SegmentoMercado, StatusMercado


class MercadoORM(Base):
    __tablename__ = "mercados"

    id: Mapped[int] = mapped_column(primary_key=True)
    nome: Mapped[str] = mapped_column(String, nullable=False)
    telefone_whatsapp: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    segmento: Mapped[SegmentoMercado] = mapped_column(
        Enum(
            SegmentoMercado,
            name="segmento_mercado",
            values_callable=lambda enum_cls: [e.value for e in enum_cls],
        ),
        nullable=False,
    )
    status: Mapped[StatusMercado] = mapped_column(
        Enum(
            StatusMercado,
            name="status_mercado",
            values_callable=lambda enum_cls: [e.value for e in enum_cls],
        ),
        nullable=False,
        default=StatusMercado.ATIVO,
    )
    data_cadastro: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )

    # Campos aditivos da Migration 0002 — configuração operacional do
    # mercado (fuso horário, relatório diário, limites de atenção).
    timezone: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    horario_abertura: Mapped[Optional[time]] = mapped_column(Time, nullable=True)
    horario_relatorio_diario: Mapped[Optional[time]] = mapped_column(Time, nullable=True)
    relatorio_diario_ativo: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    limite_valor_atencao: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(14, 2), nullable=True
    )
    limite_quantidade_atencao: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(14, 3), nullable=True
    )
