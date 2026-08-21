"""Adiciona UNIQUE em usuarios.telefone_whatsapp.

Pré-requisito para a autenticação real via webhook do WhatsApp: o número
de telefone verificado que a Meta envia em cada evento precisa mapear
deterministicamente para exatamente um usuário/mercado. Hoje
`usuarios.telefone_whatsapp` não tem nenhuma constraint de unicidade
(diferente de `mercados.telefone_whatsapp`, que já é único desde a
Migration 0001) — nada impede dois registros de `usuarios` com o mesmo
número, o que tornaria essa busca ambígua.

Migration puramente aditiva de constraint: nenhuma coluna, tabela ou
tipo é criado/alterado/removido, e nenhuma linha é tocada. Se já existir
alguma duplicidade de `telefone_whatsapp` em `usuarios` no banco em que
isso for aplicado, o próprio `ALTER TABLE ... ADD CONSTRAINT` do Postgres
falha de forma clara (duplicate key value violates unique constraint)
antes de alterar qualquer coisa — não é preciso checagem adicional aqui.
Se isso ocorrer, as duplicidades precisam ser resolvidas manualmente
antes de reexecutar esta migration.

O downgrade só remove a constraint — não há perda de dado possível
(diferente da Migration 0004, cujo downgrade recriava um tipo ENUM).

Revision ID: 0005
Revises: 0004
Create Date: 2026-08-19
"""

from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_unique_constraint(
        "uq_usuarios_telefone_whatsapp", "usuarios", ["telefone_whatsapp"]
    )


def downgrade() -> None:
    op.drop_constraint("uq_usuarios_telefone_whatsapp", "usuarios", type_="unique")
