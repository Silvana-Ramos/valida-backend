from typing import Optional

from pydantic import BaseModel

from app.schemas.enums import NivelRisco


class FaixaRisco(BaseModel):
    id: int
    nivel_risco: NivelRisco
    dias_min: Optional[int] = None
    dias_max: Optional[int] = None
