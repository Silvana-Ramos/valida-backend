from datetime import datetime
from typing import Any

from pydantic import BaseModel


class SessaoConversa(BaseModel):
    id_usuario: int
    id_mercado: int
    estado: str
    dados_parciais: dict[str, Any]
    criado_em: datetime
    atualizado_em: datetime
