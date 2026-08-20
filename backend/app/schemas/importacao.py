from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel


class StatusImportacao(str, Enum):
    PENDENTE = "pendente"
    PROCESSANDO = "processando"
    CONCLUIDA = "concluida"
    CONCLUIDA_COM_ERROS = "concluida_com_erros"
    FALHOU = "falhou"


class StatusProcessamentoItem(str, Enum):
    PENDENTE = "pendente"
    PROCESSADA = "processada"
    DUPLICADA = "duplicada"
    ERRO = "erro"


class Importacao(BaseModel):
    id: int
    id_mercado: int
    nome_arquivo: str
    hash_arquivo: str
    status: StatusImportacao
    total_linhas: Optional[int] = None
    total_processadas: int
    total_duplicadas: int
    total_com_erro: int
    criado_por: Optional[int] = None
    data_hora_inicio: datetime
    data_hora_fim: Optional[datetime] = None


class ItemImportacao(BaseModel):
    id: int
    id_importacao: int
    id_mercado: int
    numero_linha: int
    referencia_externa: str
    id_produto: Optional[int] = None
    id_lote: Optional[int] = None
    id_movimentacao: Optional[int] = None
    status_processamento: StatusProcessamentoItem
    mensagem_erro: Optional[str] = None
    # Linha original do arquivo, para auditoria (RN07/Documento Mestre).
    dados_brutos: dict[str, Any]
