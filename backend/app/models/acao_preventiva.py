from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class AcaoPreventivaORM(Base):
    __tablename__ = "acoes_preventivas"

    id: Mapped[int] = mapped_column(primary_key=True)
    id_item_relatorio: Mapped[int] = mapped_column(
        ForeignKey("itens_relatorio_diario.id"), nullable=False
    )
    id_usuario_responsavel: Mapped[Optional[int]] = mapped_column(
        ForeignKey("usuarios.id"), nullable=True
    )
    acao_recomendada: Mapped[str] = mapped_column(Text, nullable=False)
    acao_realizada: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # Plain string (sem ENUM no banco) — migration 0007.
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="recomendada")
    data_inicio: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    data_fim: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    resultado_operacional: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    observacao: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    criada_em: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )
    # Sem onupdate no banco (migration 0007 só define server_default=now()
    # na criação) — quem alterar esta linha precisa setar atualizada_em
    # manualmente na camada de serviço.
    atualizada_em: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )

    # Sem coluna id_mercado: a migration 0007 não a criou nesta tabela.
    # Isolamento por mercado (RN05) só é possível via duplo JOIN:
    # AcaoPreventivaORM.id_item_relatorio -> ItemRelatorioDiarioORM.id_relatorio
    # -> RelatorioAcaoDiarioORM.id_mercado. Não adicionar essa coluna sem
    # alterar a migration primeiro.
