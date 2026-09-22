"""gestao preventiva fase 1

Revision ID: 0007
Revises: 0006
Create Date: 2026-09-22

Cria as estruturas da Gestão Preventiva de Perdas — Fase 1:
- relatorios_acao_diaria
- itens_relatorio_diario
- acoes_preventivas

Esta migration é aditiva. Não altera tabelas existentes.
A Fase 2 (acao_movimentacoes, episodios_risco e perda evitada
automática) não faz parte desta migration.
"""

from alembic import op
import sqlalchemy as sa


revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ---------------------------------------------------------
    # 1. Relatório diário por mercado
    # ---------------------------------------------------------
    op.create_table(
        "relatorios_acao_diaria",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column(
            "id_mercado",
            sa.Integer,
            sa.ForeignKey("mercados.id"),
            nullable=False,
        ),
        sa.Column("data_referencia", sa.Date, nullable=False),
        sa.Column(
            "gerado_em",
            sa.DateTime,
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "status",
            sa.String(length=20),
            nullable=False,
            server_default="gerado",
        ),
        sa.Column(
            "qtd_vencidos",
            sa.Integer,
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "qtd_vence_hoje",
            sa.Integer,
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "qtd_urgentes",
            sa.Integer,
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "qtd_risco",
            sa.Integer,
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "qtd_atencao",
            sa.Integer,
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "valor_em_risco",
            sa.Numeric(precision=14, scale=2),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "total_acoes_recomendadas",
            sa.Integer,
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "total_acoes_realizadas",
            sa.Integer,
            nullable=False,
            server_default="0",
        ),
        sa.UniqueConstraint(
            "id_mercado",
            "data_referencia",
            name="uq_relatorio_diario_mercado_data",
        ),
    )

    op.create_index(
        "ix_relatorios_acao_diaria_mercado_data",
        "relatorios_acao_diaria",
        ["id_mercado", "data_referencia"],
    )

    # ---------------------------------------------------------
    # 2. Fotografia diária dos lotes
    # ---------------------------------------------------------
    op.create_table(
        "itens_relatorio_diario",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column(
            "id_relatorio",
            sa.Integer,
            sa.ForeignKey("relatorios_acao_diaria.id"),
            nullable=False,
        ),
        sa.Column(
            "id_produto",
            sa.Integer,
            sa.ForeignKey("produtos.id"),
            nullable=False,
        ),
        sa.Column(
            "id_lote",
            sa.Integer,
            sa.ForeignKey("lotes.id"),
            nullable=False,
        ),
        sa.Column("data_validade", sa.Date, nullable=False),
        sa.Column(
            "quantidade_disponivel",
            sa.Numeric(precision=14, scale=3),
            nullable=False,
        ),
        sa.Column(
            "preco_custo",
            sa.Numeric(precision=10, scale=2),
            nullable=True,
        ),
        sa.Column("dias_restantes", sa.Integer, nullable=False),
        sa.Column(
            "classificacao_validade",
            sa.String(length=20),
            nullable=False,
        ),
        sa.Column(
            "prioridade",
            sa.String(length=20),
            nullable=False,
        ),
        sa.Column(
            "valor_em_risco",
            sa.Numeric(precision=14, scale=2),
            nullable=True,
        ),
        sa.Column(
            "acao_recomendada",
            sa.Text,
            nullable=False,
        ),
        sa.UniqueConstraint(
            "id_relatorio",
            "id_lote",
            name="uq_item_relatorio_lote",
        ),
    )

    op.create_index(
        "ix_itens_relatorio_diario_relatorio",
        "itens_relatorio_diario",
        ["id_relatorio"],
    )

    op.create_index(
        "ix_itens_relatorio_diario_lote",
        "itens_relatorio_diario",
        ["id_lote"],
    )

    # ---------------------------------------------------------
    # 3. Ações preventivas
    # ---------------------------------------------------------
    op.create_table(
        "acoes_preventivas",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column(
            "id_item_relatorio",
            sa.Integer,
            sa.ForeignKey("itens_relatorio_diario.id"),
            nullable=False,
        ),
        sa.Column(
            "id_usuario_responsavel",
            sa.Integer,
            sa.ForeignKey("usuarios.id"),
            nullable=True,
        ),
        sa.Column(
            "acao_recomendada",
            sa.Text,
            nullable=False,
        ),
        sa.Column(
            "acao_realizada",
            sa.Text,
            nullable=True,
        ),
        sa.Column(
            "status",
            sa.String(length=20),
            nullable=False,
            server_default="recomendada",
        ),
        sa.Column("data_inicio", sa.DateTime, nullable=True),
        sa.Column("data_fim", sa.DateTime, nullable=True),
        sa.Column(
            "resultado_operacional",
            sa.Text,
            nullable=True,
        ),
        sa.Column(
            "observacao",
            sa.Text,
            nullable=True,
        ),
        sa.Column(
            "criada_em",
            sa.DateTime,
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "atualizada_em",
            sa.DateTime,
            nullable=False,
            server_default=sa.func.now(),
        ),
    )

    op.create_index(
        "ix_acoes_preventivas_item",
        "acoes_preventivas",
        ["id_item_relatorio"],
    )

    op.create_index(
        "ix_acoes_preventivas_responsavel",
        "acoes_preventivas",
        ["id_usuario_responsavel"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_acoes_preventivas_responsavel",
        table_name="acoes_preventivas",
    )
    op.drop_index(
        "ix_acoes_preventivas_item",
        table_name="acoes_preventivas",
    )
    op.drop_table("acoes_preventivas")

    op.drop_index(
        "ix_itens_relatorio_diario_lote",
        table_name="itens_relatorio_diario",
    )
    op.drop_index(
        "ix_itens_relatorio_diario_relatorio",
        table_name="itens_relatorio_diario",
    )
    op.drop_table("itens_relatorio_diario")

    op.drop_index(
        "ix_relatorios_acao_diaria_mercado_data",
        table_name="relatorios_acao_diaria",
    )
    op.drop_table("relatorios_acao_diaria")