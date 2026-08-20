"""Tipos de coluna compartilhados entre mais de uma tabela.

O Postgres cria um tipo ENUM nativo por nome; quando o mesmo enum é usado
em mais de uma tabela (ex.: NivelRisco em `lotes` e `faixas_risco`), as
colunas precisam compartilhar a mesma instância de `Enum` para não tentar
criar o tipo `nivel_risco` duas vezes.
"""

from sqlalchemy import Enum

from app.schemas.enums import NivelRisco

nivel_risco_enum = Enum(
    NivelRisco, name="nivel_risco", values_callable=lambda enum_cls: [e.value for e in enum_cls]
)
