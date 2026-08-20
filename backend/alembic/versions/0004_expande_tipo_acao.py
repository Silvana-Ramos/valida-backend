"""Expande o ENUM tipo_acao com os 6 valores exigidos pela RN04/RN07
(entrada, venda, retirada_vencimento, ajuste, correcao, importacao), que
ainda não existiam no tipo criado pela Migration 0001.

Migration puramente aditiva: nenhuma tabela, coluna, índice ou constraint
é criada, alterada ou removida. Nenhuma linha existente é tocada.

O downgrade recria o tipo `tipo_acao` reduzido aos 13 valores originais —
o PostgreSQL não tem `ALTER TYPE ... DROP VALUE`. Antes disso, uma
checagem protegida (somente leitura) verifica se algum registro de
`historico_acoes` já usa um dos 6 valores novos; se usar, o downgrade é
abortado com `RuntimeError` para evitar perda de dados por um cast
incompatível.

Revision ID: 0004
Revises: 0003
Create Date: 2026-08-17
"""

from alembic import op
import sqlalchemy as sa

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None

NOVOS_VALORES = (
    "entrada",
    "venda",
    "retirada_vencimento",
    "ajuste",
    "correcao",
    "importacao",
)

VALORES_ORIGINAIS = (
    "cadastro",
    "confirmacao",
    "edicao",
    "status_alterado",
    "alerta_enviado",
    "sugestao_gerada",
    "desconto_aplicado",
    "combo_sugerido",
    "destaque_sugerido",
    "reorganizacao_sugerida",
    "marcado_vendido",
    "marcado_descartado",
    "cancelamento",
)


def upgrade() -> None:
    for valor in NOVOS_VALORES:
        op.execute(f"ALTER TYPE public.tipo_acao ADD VALUE IF NOT EXISTS '{valor}'")


def downgrade() -> None:
    bind = op.get_bind()

    # Proteção obrigatória: aborta o downgrade se qualquer linha de
    # historico_acoes já usar um dos 6 valores novos de tipo_acao — o
    # ALTER TABLE ... USING abaixo falharia de qualquer forma nesse caso
    # (cast incompatível), mas a checagem aborta ANTES, com mensagem clara,
    # em vez de deixar o erro de cast do Postgres explicar o problema.
    em_uso = bind.execute(
        sa.text("SELECT count(*) FROM historico_acoes WHERE tipo_acao::text = ANY(:valores)"),
        {"valores": list(NOVOS_VALORES)},
    ).scalar()
    if em_uso > 0:
        raise RuntimeError(
            f"Downgrade de tipo_acao abortado: {em_uso} registro(s) em "
            f"historico_acoes usam um dos novos valores "
            f"({', '.join(NOVOS_VALORES)}). Reverter o ENUM apagaria a "
            "possibilidade de representar esses registros. Decisão explícita "
            "necessária antes de prosseguir (ex.: arquivar/migrar essas linhas "
            "para outro destino, ou cancelar o downgrade)."
        )

    # Só executa a partir daqui se a checagem acima passar (nenhuma linha
    # usando os novos valores) — recria o ENUM reduzido aos 13 valores
    # originais.
    op.execute("ALTER TYPE public.tipo_acao RENAME TO tipo_acao_old")
    valores_sql = ",".join(f"'{v}'" for v in VALORES_ORIGINAIS)
    op.execute(f"CREATE TYPE public.tipo_acao AS ENUM ({valores_sql})")
    op.execute(
        "ALTER TABLE historico_acoes "
        "ALTER COLUMN tipo_acao TYPE public.tipo_acao USING tipo_acao::text::public.tipo_acao"
    )
    op.execute("DROP TYPE public.tipo_acao_old")
