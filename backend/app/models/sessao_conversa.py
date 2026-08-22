from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class SessaoConversaORM(Base):
    __tablename__ = "sessoes_whatsapp"

    # Sem PK surrogate: uma sessão ativa por usuário (Migration 0006).
    id_usuario: Mapped[int] = mapped_column(
        ForeignKey("usuarios.id", ondelete="CASCADE"), primary_key=True
    )
    id_mercado: Mapped[int] = mapped_column(ForeignKey("mercados.id"), nullable=False)
    estado: Mapped[str] = mapped_column(String, nullable=False)
    dados_parciais: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default="{}"
    )
    criado_em: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )
    atualizado_em: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )
