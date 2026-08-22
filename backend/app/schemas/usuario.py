from enum import Enum
from typing import Optional

from pydantic import BaseModel, field_validator

from app.core.telefone import normalizar_telefone


class PapelUsuario(str, Enum):
    DONO = "dono"
    FUNCIONARIO = "funcionario"


class Usuario(BaseModel):
    id: int
    id_mercado: int
    telefone_whatsapp: str
    nome: str
    papel: PapelUsuario


class UsuarioCreateRequest(BaseModel):
    """Cadastro de usuário sob um mercado (RN05). `id_mercado` nunca vem
    daqui — vem do contexto de autenticação de quem chama: self-service
    via `Depends(obter_id_mercado_atual)`, ou bootstrap via admin em
    `POST /mercados/{id}/usuarios`."""

    telefone_whatsapp: str
    nome: str
    papel: PapelUsuario

    @field_validator("telefone_whatsapp")
    @classmethod
    def _normalizar_telefone(cls, v: str) -> str:
        return normalizar_telefone(v)


class UsuarioUpdateRequest(BaseModel):
    """Atualização de um usuário existente. Todos os campos são opcionais."""

    telefone_whatsapp: Optional[str] = None
    nome: Optional[str] = None
    papel: Optional[PapelUsuario] = None

    @field_validator("telefone_whatsapp")
    @classmethod
    def _normalizar_telefone(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        return normalizar_telefone(v)
