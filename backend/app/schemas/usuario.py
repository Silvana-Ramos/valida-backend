from enum import Enum

from pydantic import BaseModel


class PapelUsuario(str, Enum):
    DONO = "dono"
    FUNCIONARIO = "funcionario"


class Usuario(BaseModel):
    id: int
    id_mercado: int
    telefone_whatsapp: str
    nome: str
    papel: PapelUsuario
