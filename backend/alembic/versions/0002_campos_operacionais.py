"""Adiciona campos operacionais opcionais a mercados, produtos e lotes.

Não altera nem remove nenhum campo existente. `mercados.status` (criado na
0001) é preservado exatamente como está — não é tocado por esta migration.
Não cria nenhum tipo ENUM novo (`produtos.status` é texto livre).

Preenchimentos são feitos de forma set-based, por linha, sem suposição
sobre a quantidade de registros existentes (funciona com 0, 1 ou muitos
mercados/produtos/lotes):
`quantidade_inicial` permanece NULL para os lotes já existentes (a serem
preenchidos no cadastro de lotes futuros, fora do escopo desta migration);
`status_operacional` e `quantidade_disponivel` são preenchidos conforme o
`status` de cada lote:
  status='confirmado'           -> status_operacional='disponivel',   quantidade_disponivel=quantidade
  status='pendente_confirmacao' -> status_operacional='disponivel',   quantidade_disponivel=quantidade
  status='vendido'              -> status_operacional='esgotado',     quantidade_disponivel=0
  status='descartado'           -> status_operacional='descartado',   quantidade_disponivel=0
`produtos.status` recebe 'ativo' somente onde estiver NULL;
`mercados.relatorio_diario_ativo` é garantido como false.

Revision ID: 0002
Revises: 0001
Create Date: 2026-08-10
"""

from alembic import op
import sqlalchemy as sa

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()

    # --- Estrutura: mercados ---
    op.add_column("mercados", sa.Column("timezone", sa.String(length=64), nullable=True))
    op.add_column("mercados", sa.Column("horario_abertura", sa.Time(), nullable=True))
    op.add_column(
        "mercados", sa.Column("horario_relatorio_diario", sa.Time(), nullable=True)
    )
    op.add_column(
        "mercados",
        sa.Column(
            "relatorio_diario_ativo",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.add_column(
        "mercados",
        sa.Column("limite_valor_atencao", sa.Numeric(precision=14, scale=2), nullable=True),
    )
    op.add_column(
        "mercados",
        sa.Column(
            "limite_quantidade_atencao", sa.Numeric(precision=14, scale=3), nullable=True
        ),
    )

    # --- Estrutura: produtos ---
    op.add_column(
        "produtos", sa.Column("status", sa.String(length=20), nullable=True)
    )
    op.add_column(
        "produtos", sa.Column("codigo_sistema_origem", sa.String(length=100), nullable=True)
    )
    op.add_column("produtos", sa.Column("codigo_barras", sa.String(length=64), nullable=True))

    # --- Estrutura: lotes ---
    op.add_column(
        "lotes", sa.Column("status_operacional", sa.String(length=20), nullable=True)
    )
    op.add_column(
        "lotes",
        sa.Column("quantidade_disponivel", sa.Numeric(precision=14, scale=3), nullable=True),
    )
    op.add_column(
        "lotes",
        sa.Column("quantidade_inicial", sa.Numeric(precision=14, scale=3), nullable=True),
    )

    # --- Índices (não únicos) ---
    op.create_index(
        "ix_lotes_produto_data_validade", "lotes", ["id_produto", "data_validade"]
    )
    op.create_index(
        "ix_lotes_produto_status_operacional",
        "lotes",
        ["id_produto", "status_operacional"],
    )
    op.create_index(
        "ix_produtos_mercado_codigo_origem",
        "produtos",
        ["id_mercado", "codigo_sistema_origem"],
    )
    op.create_index(
        "ix_produtos_mercado_codigo_barras",
        "produtos",
        ["id_mercado", "codigo_barras"],
    )

    # --- Preenchimentos (set-based, por linha, condicionais ao status) ---
    # quantidade_inicial permanece NULL — nenhum preenchimento aqui.
    bind.execute(
        sa.text(
            "UPDATE lotes SET "
            "status_operacional = CASE status "
            "  WHEN 'confirmado' THEN 'disponivel' "
            "  WHEN 'pendente_confirmacao' THEN 'disponivel' "
            "  WHEN 'vendido' THEN 'esgotado' "
            "  WHEN 'descartado' THEN 'descartado' "
            "END, "
            "quantidade_disponivel = CASE status "
            "  WHEN 'confirmado' THEN quantidade "
            "  WHEN 'pendente_confirmacao' THEN quantidade "
            "  WHEN 'vendido' THEN 0 "
            "  WHEN 'descartado' THEN 0 "
            "END "
            "WHERE status_operacional IS NULL OR quantidade_disponivel IS NULL"
        )
    )
    bind.execute(
        sa.text("UPDATE produtos SET status = 'ativo' WHERE status IS NULL")
    )
    bind.execute(
        sa.text(
            "UPDATE mercados SET relatorio_diario_ativo = false "
            "WHERE relatorio_diario_ativo IS NULL"
        )
    )
    # mercados.status não é tocado.


def downgrade() -> None:
    op.drop_index("ix_produtos_mercado_codigo_barras", table_name="produtos")
    op.drop_index("ix_produtos_mercado_codigo_origem", table_name="produtos")
    op.drop_index("ix_lotes_produto_status_operacional", table_name="lotes")
    op.drop_index("ix_lotes_produto_data_validade", table_name="lotes")

    op.drop_column("lotes", "quantidade_inicial")
    op.drop_column("lotes", "quantidade_disponivel")
    op.drop_column("lotes", "status_operacional")

    op.drop_column("produtos", "codigo_barras")
    op.drop_column("produtos", "codigo_sistema_origem")
    op.drop_column("produtos", "status")

    op.drop_column("mercados", "limite_quantidade_atencao")
    op.drop_column("mercados", "limite_valor_atencao")
    op.drop_column("mercados", "relatorio_diario_ativo")
    op.drop_column("mercados", "horario_relatorio_diario")
    op.drop_column("mercados", "horario_abertura")
    op.drop_column("mercados", "timezone")
