from decimal import Decimal
from typing import Optional

from sqlalchemy import Enum, ForeignKey, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.schemas.produto import CategoriaProduto, UnidadeMedida


class ProdutoORM(Base):
    __tablename__ = "produtos"

    id: Mapped[int] = mapped_column(primary_key=True)
    id_mercado: Mapped[int] = mapped_column(ForeignKey("mercados.id"), nullable=False)
    nome: Mapped[str] = mapped_column(String, nullable=False)
    categoria: Mapped[CategoriaProduto] = mapped_column(
        Enum(
            CategoriaProduto,
            name="categoria_produto",
            values_callable=lambda enum_cls: [e.value for e in enum_cls],
        ),
        nullable=False,
    )
    unidade_medida: Mapped[UnidadeMedida] = mapped_column(
        Enum(
            UnidadeMedida,
            name="unidade_medida",
            values_callable=lambda enum_cls: [e.value for e in enum_cls],
        ),
        nullable=False,
    )
    # Compartilhado entre lotes do mesmo produto; não sobrescrito
    # automaticamente ao cadastrar um novo lote (ver docs/regras-negocio.md).
    preco_venda: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 2), nullable=True)

    # Campos aditivos da Migration 0002 — usados pela pipeline de
    # importação (RN07) para resolver produto por código externo/de barras.
    codigo_sistema_origem: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    codigo_barras: Mapped[Optional[str]] = mapped_column(String, nullable=True)
