from decimal import Decimal
from enum import Enum
from typing import Optional

from pydantic import BaseModel


class CategoriaProduto(str, Enum):
    LATICINIO = "laticinio"
    PADARIA = "padaria"
    HORTIFRUTI = "hortifruti"
    CARNE = "carne"
    MERCEARIA = "mercearia"
    FARMACIA = "farmacia"
    OUTRO = "outro"


class UnidadeMedida(str, Enum):
    UN = "un"
    KG = "kg"
    LITRO = "litro"
    PACOTE = "pacote"


class Produto(BaseModel):
    id: int
    id_mercado: int
    nome: str
    categoria: CategoriaProduto
    unidade_medida: UnidadeMedida
    preco_venda: Optional[Decimal] = None
