"""Cria mercados, usuarios, produtos, lotes, historico_acoes, faixas_risco
e popula faixas_risco conforme a RN01.

Revision ID: 0001
Revises:
Create Date: 2026-08-08
"""

from alembic import op
import sqlalchemy as sa

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


segmento_mercado = sa.Enum(
    "padaria",
    "acougue",
    "hortifruti",
    "farmacia",
    "mercearia",
    "conveniencia",
    "outro",
    name="segmento_mercado",
)
status_mercado = sa.Enum("ativo", "inativo", name="status_mercado")
papel_usuario = sa.Enum("dono", "funcionario", name="papel_usuario")
categoria_produto = sa.Enum(
    "laticinio",
    "padaria",
    "hortifruti",
    "carne",
    "mercearia",
    "farmacia",
    "outro",
    name="categoria_produto",
)
unidade_medida = sa.Enum("un", "kg", "litro", "pacote", name="unidade_medida")
origem_cadastro = sa.Enum("texto", "foto", "nota_fiscal", name="origem_cadastro")
status_lote = sa.Enum(
    "pendente_confirmacao", "confirmado", "vendido", "descartado", name="status_lote"
)
nivel_risco = sa.Enum("normal", "atencao", "risco", "urgente", "vencido", name="nivel_risco")
tipo_acao = sa.Enum(
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
    name="tipo_acao",
)
origem_acao = sa.Enum("sistema", "usuario", name="origem_acao")


def upgrade() -> None:
    op.create_table(
        "mercados",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("nome", sa.String, nullable=False),
        sa.Column("telefone_whatsapp", sa.String, nullable=False, unique=True),
        sa.Column("segmento", segmento_mercado, nullable=False),
        sa.Column("status", status_mercado, nullable=False, server_default="ativo"),
        sa.Column("data_cadastro", sa.DateTime, nullable=False, server_default=sa.func.now()),
    )

    op.create_table(
        "usuarios",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("id_mercado", sa.Integer, sa.ForeignKey("mercados.id"), nullable=False),
        sa.Column("telefone_whatsapp", sa.String, nullable=False),
        sa.Column("nome", sa.String, nullable=False),
        sa.Column("papel", papel_usuario, nullable=False),
    )

    op.create_table(
        "produtos",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("id_mercado", sa.Integer, sa.ForeignKey("mercados.id"), nullable=False),
        sa.Column("nome", sa.String, nullable=False),
        sa.Column("categoria", categoria_produto, nullable=False),
        sa.Column("unidade_medida", unidade_medida, nullable=False),
        sa.Column("preco_venda", sa.Numeric(10, 2), nullable=True),
    )

    op.create_table(
        "lotes",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("id_mercado", sa.Integer, sa.ForeignKey("mercados.id"), nullable=False),
        sa.Column("id_produto", sa.Integer, sa.ForeignKey("produtos.id"), nullable=False),
        sa.Column("quantidade", sa.Numeric(10, 3), nullable=False),
        sa.Column("numero_lote", sa.String, nullable=True),
        sa.Column("data_validade", sa.Date, nullable=False),
        sa.Column("data_entrada", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.Column("origem_cadastro", origem_cadastro, nullable=False),
        sa.Column(
            "status", status_lote, nullable=False, server_default="pendente_confirmacao"
        ),
        sa.Column("nivel_risco", nivel_risco, nullable=False),
        sa.Column("dias_restantes", sa.Integer, nullable=False),
        sa.Column(
            "data_ultima_atualizacao",
            sa.DateTime,
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("criado_por", sa.Integer, sa.ForeignKey("usuarios.id"), nullable=True),
        sa.Column("preco_custo", sa.Numeric(10, 2), nullable=True),
    )

    op.create_table(
        "historico_acoes",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("id_mercado", sa.Integer, sa.ForeignKey("mercados.id"), nullable=False),
        # Sem ForeignKey proposital: precisa sobreviver a lotes cancelados (RN02).
        sa.Column("id_lote", sa.Integer, nullable=True),
        sa.Column("tipo_acao", tipo_acao, nullable=False),
        sa.Column("descricao", sa.Text, nullable=False),
        sa.Column("origem", origem_acao, nullable=False),
        sa.Column("data_hora", sa.DateTime, nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_historico_acoes_id_lote", "historico_acoes", ["id_lote"])

    op.create_table(
        "faixas_risco",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("nivel_risco", nivel_risco, nullable=False, unique=True),
        sa.Column("dias_min", sa.Integer, nullable=True),
        sa.Column("dias_max", sa.Integer, nullable=True),
    )

    faixas_risco_table = sa.table(
        "faixas_risco",
        sa.column("nivel_risco", nivel_risco),
        sa.column("dias_min", sa.Integer),
        sa.column("dias_max", sa.Integer),
    )
    op.bulk_insert(
        faixas_risco_table,
        [
            {"nivel_risco": "vencido", "dias_min": None, "dias_max": -1},
            {"nivel_risco": "urgente", "dias_min": 0, "dias_max": 3},
            {"nivel_risco": "risco", "dias_min": 4, "dias_max": 7},
            {"nivel_risco": "atencao", "dias_min": 8, "dias_max": 15},
            {"nivel_risco": "normal", "dias_min": 16, "dias_max": None},
        ],
    )


def downgrade() -> None:
    op.drop_table("faixas_risco")
    op.drop_index("ix_historico_acoes_id_lote", table_name="historico_acoes")
    op.drop_table("historico_acoes")
    op.drop_table("lotes")
    op.drop_table("produtos")
    op.drop_table("usuarios")
    op.drop_table("mercados")

    bind = op.get_bind()
    nivel_risco.drop(bind, checkfirst=True)
    tipo_acao.drop(bind, checkfirst=True)
    status_lote.drop(bind, checkfirst=True)
    origem_cadastro.drop(bind, checkfirst=True)
    unidade_medida.drop(bind, checkfirst=True)
    categoria_produto.drop(bind, checkfirst=True)
    papel_usuario.drop(bind, checkfirst=True)
    status_mercado.drop(bind, checkfirst=True)
    segmento_mercado.drop(bind, checkfirst=True)
