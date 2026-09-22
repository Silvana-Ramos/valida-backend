from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Date, DateTime, ForeignKey, Integer, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class RelatorioAcaoDiarioORM(Base):
    __tablename__ = "relatorios_acao_diaria"

    id: Mapped[int] = mapped_column(primary_key=True)
    id_mercado: Mapped[int] = mapped_column(ForeignKey("mercados.id"), nullable=False)
    data_referencia: Mapped[date] = mapped_column(Date, nullable=False)
    gerado_em: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )
    # Plain string (sem ENUM no banco) — migration 0007 não criou tipo ENUM
    # para esta coluna, mesmo padrão de status_operacional em LoteORM.
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="gerado")
    qtd_vencidos: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    qtd_vence_hoje: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    qtd_urgentes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    qtd_risco: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    qtd_atencao: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    valor_em_risco: Mapped[Decimal] = mapped_column(
        Numeric(14, 2), nullable=False, default=Decimal("0")
    )
    total_acoes_recomendadas: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_acoes_realizadas: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
