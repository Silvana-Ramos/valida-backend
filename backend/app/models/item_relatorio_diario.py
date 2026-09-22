from datetime import date
from decimal import Decimal
from typing import Optional

from sqlalchemy import Date, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class ItemRelatorioDiarioORM(Base):
    __tablename__ = "itens_relatorio_diario"

    id: Mapped[int] = mapped_column(primary_key=True)
    id_relatorio: Mapped[int] = mapped_column(
        ForeignKey("relatorios_acao_diaria.id"), nullable=False
    )
    id_produto: Mapped[int] = mapped_column(ForeignKey("produtos.id"), nullable=False)
    id_lote: Mapped[int] = mapped_column(ForeignKey("lotes.id"), nullable=False)
    data_validade: Mapped[date] = mapped_column(Date, nullable=False)
    quantidade_disponivel: Mapped[Decimal] = mapped_column(Numeric(14, 3), nullable=False)
    preco_custo: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 2), nullable=True)
    dias_restantes: Mapped[int] = mapped_column(Integer, nullable=False)
    # Plain string (sem ENUM no banco) — migration 0007. Espelha os valores
    # de NivelRisco, mas não reusa nivel_risco_enum porque a coluna no
    # banco não é um tipo ENUM do Postgres.
    classificacao_validade: Mapped[str] = mapped_column(String(20), nullable=False)
    # Plain string (sem ENUM no banco) — migration 0007.
    prioridade: Mapped[str] = mapped_column(String(20), nullable=False)
    valor_em_risco: Mapped[Optional[Decimal]] = mapped_column(Numeric(14, 2), nullable=True)
    acao_recomendada: Mapped[str] = mapped_column(Text, nullable=False)

    # Sem coluna id_mercado: a migration 0007 não a criou nesta tabela.
    # Isolamento por mercado (RN05) só é possível via JOIN:
    # ItemRelatorioDiarioORM.id_relatorio -> RelatorioAcaoDiarioORM.id_mercado.
    # Não adicionar essa coluna sem alterar a migration primeiro.
