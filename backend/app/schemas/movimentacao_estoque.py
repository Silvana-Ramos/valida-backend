from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class TipoMovimentacao(str, Enum):
    ENTRADA = "entrada"
    VENDA = "venda"
    RETIRADA = "retirada"
    AJUSTE = "ajuste"


class SentidoMovimentacao(str, Enum):
    ENTRADA = "entrada"
    SAIDA = "saida"


class OrigemMovimentacao(str, Enum):
    USUARIO = "usuario"
    SISTEMA = "sistema"
    IMPORTACAO_EXTERNA = "importacao_externa"


class MovimentacaoEstoque(BaseModel):
    id: int
    id_mercado: int
    id_lote: int
    id_importacao: Optional[int] = None
    tipo_movimentacao: TipoMovimentacao
    # Só preenchido quando tipo_movimentacao = ajuste (RN07).
    sentido: Optional[SentidoMovimentacao] = None
    quantidade_movimentada: Decimal
    quantidade_anterior: Decimal
    quantidade_resultante: Decimal
    origem: OrigemMovimentacao
    referencia_externa: Optional[str] = None
    # Autorreferenciada; só preenchido quando tipo_movimentacao = ajuste (RN07).
    id_movimentacao_estornada: Optional[int] = None
    criado_por: Optional[int] = None
    data_hora: datetime


class EntradaEstoqueRequest(BaseModel):
    """Entrada de estoque sobre um lote já confirmado (RN07). `id_lote` vem
    da rota, não do corpo — mesmo padrão de `/lotes/{id_lote}/confirmar`."""

    quantidade: Decimal = Field(gt=0)
    criado_por: Optional[int] = None


class VendaEstoqueRequest(BaseModel):
    """Venda de estoque sobre um lote já confirmado (RN07). `id_lote` vem
    da rota, não do corpo — mesmo padrão de `/lotes/{id_lote}/confirmar`."""

    quantidade: Decimal = Field(gt=0)
    criado_por: Optional[int] = None


class RetiradaEstoqueRequest(BaseModel):
    """Retirada de produto vencido sobre um lote já confirmado (RN07).
    `id_lote` vem da rota, não do corpo — mesmo padrão de
    `/lotes/{id_lote}/confirmar`."""

    quantidade: Decimal = Field(gt=0)
    criado_por: Optional[int] = None


class AjusteEstoqueRequest(BaseModel):
    """Ajuste de estoque (correção/estorno) sobre um lote já confirmado
    (RN07). `id_lote` vem da rota, não do corpo — mesmo padrão de
    `/lotes/{id_lote}/confirmar`. `id_movimentacao_estornada` é opcional:
    quando informado, o ajuste estorna uma movimentação específica (nunca
    a altera ou remove, só cria esta nova linha apontando para ela);
    quando omitido, é uma correção livre de contagem/inventário."""

    quantidade: Decimal = Field(gt=0)
    sentido: SentidoMovimentacao
    id_movimentacao_estornada: Optional[int] = None
    criado_por: Optional[int] = None
