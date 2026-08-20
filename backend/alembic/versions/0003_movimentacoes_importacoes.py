"""Cria movimentacoes_estoque, importacoes e itens_importacao; adiciona
campos aditivos de quantidade em historico_acoes.

Não altera nenhum campo ou tabela existente além de:
- adicionar `UNIQUE (id, id_mercado)` em `lotes` (nova constraint, sem
  impacto em dado existente, já que `id` já é único);
- adicionar 3 colunas opcionais (`quantidade_anterior`,
  `quantidade_movimentada`, `quantidade_resultante`) em `historico_acoes`,
  sem valor padrão e sem preenchimento retroativo.

Não cria nem altera nenhum tipo ENUM existente. Em particular,
`historico_acoes.tipo_acao` NÃO é alterado nesta migration — a expansão
desse ENUM com os valores `entrada`, `venda`, `retirada_vencimento`,
`ajuste`, `correcao` e `importacao` fica deliberadamente para uma
migration futura e isolada, aplicada apenas quando o código de serviço
estiver pronto para gravar esses valores (RN07, docs/modelo-dados.md).

Nenhum comando de dados (INSERT/UPDATE/DELETE) é executado — as 3 tabelas
novas nascem vazias e as 3 colunas novas de `historico_acoes` são
opcionais, sem backfill.

Revision ID: 0003
Revises: 0002
Create Date: 2026-08-14
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


status_importacao = sa.Enum(
    "pendente",
    "processando",
    "concluida",
    "concluida_com_erros",
    "falhou",
    name="status_importacao",
)
tipo_movimentacao = sa.Enum(
    "entrada", "venda", "retirada", "ajuste", name="tipo_movimentacao"
)
sentido_movimentacao = sa.Enum("entrada", "saida", name="sentido_movimentacao")
origem_movimentacao = sa.Enum(
    "usuario", "sistema", "importacao_externa", name="origem_movimentacao"
)
status_processamento_item = sa.Enum(
    "pendente", "processada", "duplicada", "erro", name="status_processamento_item"
)


def upgrade() -> None:
    # --- importacoes ---
    op.create_table(
        "importacoes",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("id_mercado", sa.Integer, sa.ForeignKey("mercados.id"), nullable=False),
        sa.Column("nome_arquivo", sa.String, nullable=False),
        sa.Column("hash_arquivo", sa.String, nullable=False),
        sa.Column("status", status_importacao, nullable=False),
        sa.Column("total_linhas", sa.Integer, nullable=True),
        sa.Column("total_processadas", sa.Integer, nullable=False, server_default="0"),
        sa.Column("total_duplicadas", sa.Integer, nullable=False, server_default="0"),
        sa.Column("total_com_erro", sa.Integer, nullable=False, server_default="0"),
        sa.Column("criado_por", sa.Integer, sa.ForeignKey("usuarios.id"), nullable=True),
        sa.Column(
            "data_hora_inicio", sa.DateTime, nullable=False, server_default=sa.func.now()
        ),
        sa.Column("data_hora_fim", sa.DateTime, nullable=True),
        sa.UniqueConstraint("id_mercado", "hash_arquivo", name="uq_importacoes_mercado_hash"),
        sa.UniqueConstraint("id", "id_mercado", name="uq_importacoes_id_mercado"),
        sa.CheckConstraint("total_processadas >= 0", name="ck_importacoes_total_processadas"),
        sa.CheckConstraint("total_duplicadas >= 0", name="ck_importacoes_total_duplicadas"),
        sa.CheckConstraint("total_com_erro >= 0", name="ck_importacoes_total_com_erro"),
        sa.CheckConstraint(
            "total_linhas IS NULL OR total_linhas >= 0", name="ck_importacoes_total_linhas"
        ),
    )
    op.create_index(
        "ix_importacoes_mercado_data_inicio", "importacoes", ["id_mercado", "data_hora_inicio"]
    )

    # --- lotes: UNIQUE (id, id_mercado), alvo de FKs compostas ---
    op.create_unique_constraint("uq_lotes_id_mercado", "lotes", ["id", "id_mercado"])

    # --- movimentacoes_estoque ---
    op.create_table(
        "movimentacoes_estoque",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("id_mercado", sa.Integer, sa.ForeignKey("mercados.id"), nullable=False),
        sa.Column("id_lote", sa.Integer, nullable=False),
        sa.Column("id_importacao", sa.Integer, nullable=True),
        sa.Column("tipo_movimentacao", tipo_movimentacao, nullable=False),
        sa.Column("sentido", sentido_movimentacao, nullable=True),
        sa.Column("quantidade_movimentada", sa.Numeric(14, 3), nullable=False),
        sa.Column("quantidade_anterior", sa.Numeric(14, 3), nullable=False),
        sa.Column("quantidade_resultante", sa.Numeric(14, 3), nullable=False),
        sa.Column("origem", origem_movimentacao, nullable=False),
        sa.Column("referencia_externa", sa.String, nullable=True),
        sa.Column("id_movimentacao_estornada", sa.Integer, nullable=True),
        sa.Column("criado_por", sa.Integer, sa.ForeignKey("usuarios.id"), nullable=True),
        sa.Column("data_hora", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("id", "id_mercado", name="uq_movimentacoes_id_mercado"),
        sa.ForeignKeyConstraint(
            ["id_lote", "id_mercado"],
            ["lotes.id", "lotes.id_mercado"],
            name="fk_movimentacoes_lote_mercado",
        ),
        sa.ForeignKeyConstraint(
            ["id_importacao", "id_mercado"],
            ["importacoes.id", "importacoes.id_mercado"],
            name="fk_movimentacoes_importacao_mercado",
        ),
        sa.ForeignKeyConstraint(
            ["id_movimentacao_estornada", "id_mercado"],
            ["movimentacoes_estoque.id", "movimentacoes_estoque.id_mercado"],
            name="fk_movimentacoes_estornada_mercado",
        ),
        sa.CheckConstraint(
            "quantidade_movimentada > 0", name="ck_movimentacoes_quantidade_movimentada"
        ),
        sa.CheckConstraint(
            "quantidade_anterior >= 0", name="ck_movimentacoes_quantidade_anterior"
        ),
        sa.CheckConstraint(
            "quantidade_resultante >= 0", name="ck_movimentacoes_quantidade_resultante"
        ),
        sa.CheckConstraint(
            "(tipo_movimentacao = 'ajuste' AND sentido IS NOT NULL) OR "
            "(tipo_movimentacao != 'ajuste' AND sentido IS NULL)",
            name="ck_movimentacoes_sentido_ajuste",
        ),
        sa.CheckConstraint(
            "id_movimentacao_estornada IS NULL OR tipo_movimentacao = 'ajuste'",
            name="ck_movimentacoes_estornada_ajuste",
        ),
        sa.CheckConstraint(
            "origem != 'importacao_externa' OR referencia_externa IS NOT NULL",
            name="ck_movimentacoes_referencia_importacao",
        ),
    )
    op.create_index(
        "ix_movimentacoes_lote_data", "movimentacoes_estoque", ["id_lote", "data_hora"]
    )
    op.create_index(
        "ix_movimentacoes_mercado_data", "movimentacoes_estoque", ["id_mercado", "data_hora"]
    )
    op.create_index(
        "ix_movimentacoes_importacao", "movimentacoes_estoque", ["id_importacao"]
    )
    op.create_index(
        "ix_movimentacoes_idempotencia",
        "movimentacoes_estoque",
        ["id_mercado", "origem", "referencia_externa"],
        unique=True,
        postgresql_where=sa.text("referencia_externa IS NOT NULL"),
    )

    # --- itens_importacao ---
    op.create_table(
        "itens_importacao",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("id_importacao", sa.Integer, nullable=False),
        sa.Column("id_mercado", sa.Integer, sa.ForeignKey("mercados.id"), nullable=False),
        sa.Column("numero_linha", sa.Integer, nullable=False),
        sa.Column("referencia_externa", sa.String, nullable=False),
        sa.Column("id_produto", sa.Integer, sa.ForeignKey("produtos.id"), nullable=True),
        sa.Column("id_lote", sa.Integer, nullable=True),
        sa.Column("id_movimentacao", sa.Integer, nullable=True),
        sa.Column("status_processamento", status_processamento_item, nullable=False),
        sa.Column("mensagem_erro", sa.Text, nullable=True),
        sa.Column("dados_brutos", JSONB, nullable=False),
        sa.UniqueConstraint(
            "id_importacao", "numero_linha", name="uq_itens_importacao_linha"
        ),
        sa.UniqueConstraint(
            "id_mercado", "referencia_externa", name="uq_itens_importacao_referencia"
        ),
        sa.ForeignKeyConstraint(
            ["id_importacao", "id_mercado"],
            ["importacoes.id", "importacoes.id_mercado"],
            name="fk_itens_importacao_mercado",
        ),
        sa.ForeignKeyConstraint(
            ["id_movimentacao", "id_mercado"],
            ["movimentacoes_estoque.id", "movimentacoes_estoque.id_mercado"],
            name="fk_itens_movimentacao_mercado",
        ),
        sa.ForeignKeyConstraint(
            ["id_lote", "id_mercado"],
            ["lotes.id", "lotes.id_mercado"],
            name="fk_itens_lote_mercado",
        ),
    )
    op.create_index("ix_itens_importacao_importacao", "itens_importacao", ["id_importacao"])

    # --- historico_acoes: 3 colunas aditivas ---
    op.add_column(
        "historico_acoes", sa.Column("quantidade_anterior", sa.Numeric(14, 3), nullable=True)
    )
    op.add_column(
        "historico_acoes",
        sa.Column("quantidade_movimentada", sa.Numeric(14, 3), nullable=True),
    )
    op.add_column(
        "historico_acoes", sa.Column("quantidade_resultante", sa.Numeric(14, 3), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("historico_acoes", "quantidade_resultante")
    op.drop_column("historico_acoes", "quantidade_movimentada")
    op.drop_column("historico_acoes", "quantidade_anterior")

    op.drop_index("ix_itens_importacao_importacao", table_name="itens_importacao")
    op.drop_table("itens_importacao")

    op.drop_index("ix_movimentacoes_idempotencia", table_name="movimentacoes_estoque")
    op.drop_index("ix_movimentacoes_importacao", table_name="movimentacoes_estoque")
    op.drop_index("ix_movimentacoes_mercado_data", table_name="movimentacoes_estoque")
    op.drop_index("ix_movimentacoes_lote_data", table_name="movimentacoes_estoque")
    op.drop_table("movimentacoes_estoque")

    op.drop_constraint("uq_lotes_id_mercado", "lotes", type_="unique")

    op.drop_index("ix_importacoes_mercado_data_inicio", table_name="importacoes")
    op.drop_table("importacoes")

    bind = op.get_bind()
    status_processamento_item.drop(bind, checkfirst=True)
    origem_movimentacao.drop(bind, checkfirst=True)
    sentido_movimentacao.drop(bind, checkfirst=True)
    tipo_movimentacao.drop(bind, checkfirst=True)
    status_importacao.drop(bind, checkfirst=True)
