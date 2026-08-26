from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel

from app.schemas.enums import NivelRisco, OrigemCadastro, StatusLote


class Lote(BaseModel):
    id: int
    id_mercado: int
    id_produto: int
    quantidade: float
    numero_lote: Optional[str] = None
    data_validade: date
    data_entrada: datetime
    origem_cadastro: OrigemCadastro
    status: StatusLote
    # Complementar a `status` (RN06): reflete a disponibilidade do lote
    # para fins operacionais (disponivel/esgotado/descartado), derivada
    # das movimentações de estoque (RN07) — `status` sozinho não muda com
    # venda/retirada. Sem CHECK/ENUM no banco (RN06); `None` só ocorre
    # para lotes anteriores à Migration 0002 sem backfill retroativo.
    status_operacional: Optional[str] = None
    nivel_risco: NivelRisco
    dias_restantes: int
    data_ultima_atualizacao: datetime
    criado_por: int
    preco_custo: Optional[Decimal] = None


class LoteCreateRequest(BaseModel):
    """Entrada do cadastro de lote por texto (RN02: entra como pendente_confirmacao).

    `id_mercado` não vem daqui — vem do contexto de autenticação de quem
    chama (`Depends(obter_id_mercado_atual)`), nunca do corpo da
    requisição (RN05)."""

    produto_nome: str
    quantidade: float
    data_validade: date
    numero_lote: Optional[str] = None
    criado_por: Optional[int] = None
    preco_custo: Optional[Decimal] = None
    preco_venda: Optional[Decimal] = None


class LoteEditRequest(BaseModel):
    """Edição de um lote ainda pendente_confirmacao. Todos os campos são opcionais."""

    produto_nome: Optional[str] = None
    quantidade: Optional[float] = None
    data_validade: Optional[date] = None
    numero_lote: Optional[str] = None
