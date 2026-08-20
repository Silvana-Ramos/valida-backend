"""Enums compartilhados entre schemas, conforme docs/modelo-dados.md.

Centralizados aqui porque são usados em mais de um schema (ex.: NivelRisco
aparece em `lote.py` e em `faixa_risco.py`) ou porque representam valores
fixos definidos nas regras de negócio (docs/regras-negocio.md).
"""

from enum import Enum


class StatusLote(str, Enum):
    PENDENTE_CONFIRMACAO = "pendente_confirmacao"
    CONFIRMADO = "confirmado"
    VENDIDO = "vendido"
    DESCARTADO = "descartado"


class NivelRisco(str, Enum):
    NORMAL = "normal"
    ATENCAO = "atencao"
    RISCO = "risco"
    URGENTE = "urgente"
    VENCIDO = "vencido"


class OrigemCadastro(str, Enum):
    TEXTO = "texto"
    FOTO = "foto"
    NOTA_FISCAL = "nota_fiscal"


class TipoAcao(str, Enum):
    CADASTRO = "cadastro"
    CONFIRMACAO = "confirmacao"
    EDICAO = "edicao"
    STATUS_ALTERADO = "status_alterado"
    ALERTA_ENVIADO = "alerta_enviado"
    SUGESTAO_GERADA = "sugestao_gerada"
    DESCONTO_APLICADO = "desconto_aplicado"
    COMBO_SUGERIDO = "combo_sugerido"
    DESTAQUE_SUGERIDO = "destaque_sugerido"
    REORGANIZACAO_SUGERIDA = "reorganizacao_sugerida"
    MARCADO_VENDIDO = "marcado_vendido"
    MARCADO_DESCARTADO = "marcado_descartado"
    CANCELAMENTO = "cancelamento"
    # Adicionados pelo Documento Mestre / Migration 0004 (RN04, RN07).
    ENTRADA = "entrada"
    VENDA = "venda"
    RETIRADA_VENCIMENTO = "retirada_vencimento"
    AJUSTE = "ajuste"
    CORRECAO = "correcao"
    IMPORTACAO = "importacao"
