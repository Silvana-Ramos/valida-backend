"""Catálogo de produtos persistido no PostgreSQL via SQLAlchemy.

Resolve produto_nome -> id_produto (get-or-create) para manter o modelo
oficial de `lotes.id_produto` intacto mesmo recebendo texto livre na
entrada (docs/modelo-dados.md).
"""

from decimal import Decimal

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.produto import ProdutoORM
from app.schemas.produto import CategoriaProduto, Produto, UnidadeMedida


def _normalizar(nome: str) -> str:
    return nome.strip().lower()


def obter_ou_criar(
    db: Session,
    id_mercado: int,
    nome: str,
    preco_venda: Decimal | None = None,
) -> tuple[Produto, bool]:
    """Retorna (produto, preco_venda_ignorado).

    Se o produto já existir no catálogo, preco_venda recebido aqui NUNCA
    sobrescreve o valor existente — atualização de preço de venda de um
    produto já cadastrado é um fluxo próprio, ainda não implementado.
    `preco_venda_ignorado` é True quando um preço foi passado mas não pôde
    ser aplicado por esse motivo. Custo de aquisição não é atributo do
    produto — pertence a cada lote (ver lote_service.py).
    """
    nome_normalizado = _normalizar(nome)
    produto_orm = (
        db.query(ProdutoORM)
        .filter(
            ProdutoORM.id_mercado == id_mercado,
            func.lower(func.trim(ProdutoORM.nome)) == nome_normalizado,
        )
        .first()
    )

    if produto_orm is not None:
        preco_venda_ignorado = preco_venda is not None
        return Produto.model_validate(produto_orm, from_attributes=True), preco_venda_ignorado

    produto_orm = ProdutoORM(
        id_mercado=id_mercado,
        nome=nome.strip(),
        # Valores provisórios de teste: sem categoria/unidade informadas pelo
        # cadastro por texto. Ajustáveis depois via um fluxo de catálogo.
        categoria=CategoriaProduto.OUTRO,
        unidade_medida=UnidadeMedida.UN,
        preco_venda=preco_venda,
    )
    db.add(produto_orm)
    db.commit()
    db.refresh(produto_orm)
    return Produto.model_validate(produto_orm, from_attributes=True), False


def listar(db: Session, id_mercado: int | None = None) -> list[Produto]:
    query = db.query(ProdutoORM)
    if id_mercado is not None:
        query = query.filter(ProdutoORM.id_mercado == id_mercado)
    return [Produto.model_validate(p, from_attributes=True) for p in query.all()]
