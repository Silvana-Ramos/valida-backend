from typing import Optional

from sqlalchemy import Integer
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models._shared import nivel_risco_enum


class FaixaRiscoORM(Base):
    __tablename__ = "faixas_risco"

    id: Mapped[int] = mapped_column(primary_key=True)
    nivel_risco: Mapped[str] = mapped_column(nivel_risco_enum, nullable=False, unique=True)
    dias_min: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    dias_max: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
