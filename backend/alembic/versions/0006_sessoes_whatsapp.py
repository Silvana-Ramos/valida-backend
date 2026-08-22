"""Cria sessoes_whatsapp.

Fatia 2 do planejamento da integração com o WhatsApp para o piloto
(fluxo guiado por menu, sem NLU/LLM nesta fase — decisão aprovada
explicitamente pelo usuário). Guarda o estado de uma conversa em
andamento; ausência de linha significa "sem conversa ativa" (o bot
responde com o menu principal). Não há, ainda, nenhum webhook nem
cliente de envio de mensagens implementado — esta tabela só passa a ter
um consumidor real numa fase posterior, fora do escopo desta migration.

`estado` é texto livre, sem `CHECK`/`ENUM` associado — mesma decisão já
tomada para `lotes.status_operacional` (RN06): o vocabulário de estados
do fluxo de mensagens ainda está sendo desenhado e vai ser ajustado
enquanto o webhook é implementado, e um `ENUM` do Postgres exigiria uma
migration a cada valor novo/removido.

Deduplicação de `message id` (idempotência do webhook) foi explicitamente
adiada para uma fatia futura e separada — não faz parte desta migration.

Migration puramente aditiva: cria uma tabela nova, sem alterar nenhuma
tabela, coluna ou tipo existente. Nenhum dado é tocado.

Revision ID: 0006
Revises: 0005
Create Date: 2026-08-22
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "sessoes_whatsapp",
        sa.Column(
            "id_usuario",
            sa.Integer,
            sa.ForeignKey("usuarios.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("id_mercado", sa.Integer, sa.ForeignKey("mercados.id"), nullable=False),
        sa.Column("estado", sa.String, nullable=False),
        sa.Column(
            "dados_parciais",
            JSONB,
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("criado_em", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.Column("atualizado_em", sa.DateTime, nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_sessoes_whatsapp_mercado", "sessoes_whatsapp", ["id_mercado"])


def downgrade() -> None:
    op.drop_index("ix_sessoes_whatsapp_mercado", table_name="sessoes_whatsapp")
    op.drop_table("sessoes_whatsapp")
