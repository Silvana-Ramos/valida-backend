from datetime import datetime, time
from decimal import Decimal
from enum import Enum
from typing import Optional

from pydantic import BaseModel, field_validator

from app.core.telefone import normalizar_telefone


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
    # Campos aditivos da Migration 0002.
    timezone: Optional[str] = None
    horario_abertura: Optional[time] = None
    horario_relatorio_diario: Optional[time] = None
    relatorio_diario_ativo: bool
    limite_valor_atencao: Optional[Decimal] = None
    limite_quantidade_atencao: Optional[Decimal] = None


class MercadoCreateRequest(BaseModel):
    """Cadastro de um mercado novo (onboarding do piloto, admin-only).
    `status` não é informado aqui — todo mercado novo nasce `ativo`
    (padrão do banco). Os campos operacionais da Migration 0002 (fuso
    horário, horário de relatório, limites de atenção) ficam para uma
    atualização posterior via `MercadoUpdateRequest`, não na criação."""

    nome: str
    telefone_whatsapp: str
    segmento: SegmentoMercado

    @field_validator("telefone_whatsapp")
    @classmethod
    def _normalizar_telefone(cls, v: str) -> str:
        return normalizar_telefone(v)


class MercadoUpdateRequest(BaseModel):
    """Atualização de um mercado existente. Todos os campos são opcionais."""

    nome: Optional[str] = None
    telefone_whatsapp: Optional[str] = None
    segmento: Optional[SegmentoMercado] = None
    status: Optional[StatusMercado] = None
    timezone: Optional[str] = None
    horario_abertura: Optional[time] = None
    horario_relatorio_diario: Optional[time] = None
    relatorio_diario_ativo: Optional[bool] = None
    limite_valor_atencao: Optional[Decimal] = None
    limite_quantidade_atencao: Optional[Decimal] = None

    @field_validator("telefone_whatsapp")
    @classmethod
    def _normalizar_telefone(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        return normalizar_telefone(v)
