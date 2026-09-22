from datetime import date
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel


class ItemRelatorioDiario(BaseModel):
    id: int
    id_relatorio: int
    id_produto: int
    id_lote: int
    data_validade: date
    quantidade_disponivel: Decimal
    preco_custo: Optional[Decimal] = None
    dias_restantes: int
    # Sem ENUM no banco (migration 0007) — mesmo padrão de
    # Lote.status_operacional: string livre, vocabulário definido na
    # camada de serviço, não aqui.
    classificacao_validade: str
    prioridade: str
    valor_em_risco: Optional[Decimal] = None
    acao_recomendada: str
