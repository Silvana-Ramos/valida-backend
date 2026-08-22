from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import obter_id_mercado_atual
from app.schemas.produto import Produto
from app.services import produto_service

router = APIRouter(prefix="/produtos", tags=["produtos"])


@router.get("", response_model=list[Produto])
def listar_produtos(
    id_mercado: int = Depends(obter_id_mercado_atual), db: Session = Depends(get_db)
) -> list[Produto]:
    return produto_service.listar(db, id_mercado)
