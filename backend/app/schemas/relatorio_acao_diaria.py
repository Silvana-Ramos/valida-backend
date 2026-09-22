from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel


class RelatorioAcaoDiario(BaseModel):
    id: int
    id_mercado: int
    data_referencia: date
    gerado_em: datetime
    # Sem ENUM no banco (migration 0007) — mesmo padrão de
    # Lote.status_operacional: string livre, vocabulário definido na
    # camada de serviço, não aqui.
    status: str
    qtd_vencidos: int
    qtd_vence_hoje: int
    qtd_urgentes: int
    qtd_risco: int
    qtd_atencao: int
    valor_em_risco: Decimal
    total_acoes_recomendadas: int
    total_acoes_realizadas: int
