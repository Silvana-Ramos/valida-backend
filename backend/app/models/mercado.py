from datetime import datetime

from sqlalchemy import DateTime, Enum, String, func
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
