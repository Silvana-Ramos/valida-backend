from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import Date, DateTime, Enum, ForeignKey, Integer, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models._shared import nivel_risco_enum
from app.schemas.enums import OrigemCadastro, StatusLote


class LoteORM(Base):
    __tablename__ = "lotes"

    id: Mapped[int] = mapped_column(primary_key=True)
    id_mercado: Mapped[int] = mapped_column(ForeignKey("mercados.id"), nullable=False)
    id_produto: Mapped[int] = mapped_column(ForeignKey("produtos.id"), nullable=False)
    quantidade: Mapped[Decimal] = mapped_column(Numeric(10, 3), nullable=False)
    numero_lote: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    data_validade: Mapped[date] = mapped_column(Date, nullable=False)
    data_entrada: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )
    origem_cadastro: Mapped[OrigemCadastro] = mapped_column(
        Enum(
            OrigemCadastro,
            name="origem_cadastro",
            values_callable=lambda enum_cls: [e.value for e in enum_cls],
        ),
        nullable=False,
    )
    status: Mapped[StatusLote] = mapped_column(
        Enum(
            StatusLote,
            name="status_lote",
            values_callable=lambda enum_cls: [e.value for e in enum_cls],
        ),
        nullable=False,
        default=StatusLote.PENDENTE_CONFIRMACAO,
    )
    # Enquanto pendente_confirmacao, é apenas uma prévia (recalculada pela
    # camada de serviço a cada leitura); torna-se oficial na confirmação.
    nivel_risco: Mapped[str] = mapped_column(nivel_risco_enum, nullable=False)
    dias_restantes: Mapped[int] = mapped_column(Integer, nullable=False)
    data_ultima_atualizacao: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )
    # Opcional: ainda não há autenticação real de usuário via WhatsApp.
    criado_por: Mapped[Optional[int]] = mapped_column(ForeignKey("usuarios.id"), nullable=True)
    # Custo de aquisição DESTE lote — nunca compartilhado com outros lotes
    # do mesmo produto (ver docs/modelo-dados.md).
    preco_custo: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 2), nullable=True)

    # Campos adicionados pela Migration 0002 (RN06) — ainda sem uso na
    # camada de serviço.
    status_operacional: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    quantidade_disponivel: Mapped[Optional[Decimal]] = mapped_column(Numeric(14, 3), nullable=True)
    quantidade_inicial: Mapped[Optional[Decimal]] = mapped_column(Numeric(14, 3), nullable=True)
