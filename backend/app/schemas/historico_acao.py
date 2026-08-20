from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Optional

from pydantic import BaseModel

from app.schemas.enums import TipoAcao


class OrigemAcao(str, Enum):
    SISTEMA = "sistema"
    USUARIO = "usuario"


class HistoricoAcao(BaseModel):
    id: int
    id_mercado: int
    id_lote: Optional[int] = None
    tipo_acao: TipoAcao
    descricao: str
    origem: OrigemAcao
    data_hora: datetime
    # Migration 0003 (RN07): preenchidos somente quando a ação altera
    # efetivamente o estoque; None em qualquer outra ação.
    quantidade_anterior: Optional[Decimal] = None
    quantidade_movimentada: Optional[Decimal] = None
    quantidade_resultante: Optional[Decimal] = None
