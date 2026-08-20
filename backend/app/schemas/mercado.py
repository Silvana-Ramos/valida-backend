from datetime import datetime
from enum import Enum

from pydantic import BaseModel


class SegmentoMercado(str, Enum):
    PADARIA = "padaria"
    ACOUGUE = "acougue"
    HORTIFRUTI = "hortifruti"
    FARMACIA = "farmacia"
    MERCEARIA = "mercearia"
    CONVENIENCIA = "conveniencia"
    OUTRO = "outro"


class StatusMercado(str, Enum):
    ATIVO = "ativo"
    INATIVO = "inativo"


class Mercado(BaseModel):
    id: int
    nome: str
    telefone_whatsapp: str
    segmento: SegmentoMercado
    status: StatusMercado
    data_cadastro: datetime
