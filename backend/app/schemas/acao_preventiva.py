from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class AcaoPreventiva(BaseModel):
    id: int
    id_item_relatorio: int
    id_usuario_responsavel: Optional[int] = None
    acao_recomendada: str
    acao_realizada: Optional[str] = None
    # Sem ENUM no banco (migration 0007) — mesmo padrão de
    # Lote.status_operacional: string livre, vocabulário definido na
    # camada de serviço, não aqui.
    status: str
    data_inicio: Optional[datetime] = None
    data_fim: Optional[datetime] = None
    resultado_operacional: Optional[str] = None
    observacao: Optional[str] = None
    criada_em: datetime
    atualizada_em: datetime


class AcaoPreventivaCreateRequest(BaseModel):
    """Registro de uma ação preventiva sobre um item do relatório diário.

    `id_item_relatorio` não vem daqui — vem da rota. `acao_recomendada` não
    vem daqui — é copiada do item pelo serviço. `id_mercado` não vem daqui —
    vem do contexto de autenticação de quem chama
    (`Depends(obter_id_mercado_atual)`), nunca do corpo da requisição (RN05)."""

    id_usuario_responsavel: Optional[int] = None
    acao_realizada: Optional[str] = None
    observacao: Optional[str] = None


class AcaoPreventivaEditRequest(BaseModel):
    """Atualização de uma ação preventiva já registrada. Todos os campos são opcionais."""

    status: Optional[str] = None
    acao_realizada: Optional[str] = None
    data_inicio: Optional[datetime] = None
    data_fim: Optional[datetime] = None
    resultado_operacional: Optional[str] = None
    observacao: Optional[str] = None
