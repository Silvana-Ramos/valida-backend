from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.schemas.produto import Produto
from app.services import produto_service

router = APIRouter(prefix="/produtos", tags=["produtos"])


@router.get("", response_model=list[Produto])
def listar_produtos(id_mercado: int | None = None, db: Session = Depends(get_db)) -> list[Produto]:
    return produto_service.listar(db, id_mercado=id_mercado)
