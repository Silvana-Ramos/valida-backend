from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.schemas.importacao import StatusImportacao


class ImportacaoORM(Base):
    __tablename__ = "importacoes"

    id: Mapped[int] = mapped_column(primary_key=True)
    id_mercado: Mapped[int] = mapped_column(ForeignKey("mercados.id"), nullable=False)
    nome_arquivo: Mapped[str] = mapped_column(String, nullable=False)
    hash_arquivo: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[StatusImportacao] = mapped_column(
        Enum(
            StatusImportacao,
            name="status_importacao",
            values_callable=lambda enum_cls: [e.value for e in enum_cls],
        ),
        nullable=False,
    )
    total_linhas: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    total_processadas: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_duplicadas: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_com_erro: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # Opcional: NULL para disparo automático (RN, docs/modelo-dados.md).
    criado_por: Mapped[Optional[int]] = mapped_column(ForeignKey("usuarios.id"), nullable=True)
    data_hora_inicio: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )
    data_hora_fim: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
