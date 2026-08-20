from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import obter_id_mercado_atual
from app.schemas.importacao import Importacao, ItemImportacao
from app.services import importacao_service
from app.services.importacao_parser import ArquivoInvalido

router = APIRouter(prefix="/importacoes", tags=["importacoes"])


@router.post("", response_model=Importacao, status_code=201)
def importar_vendas(
    arquivo: UploadFile = File(...),
    id_mercado: int = Depends(obter_id_mercado_atual),
    db: Session = Depends(get_db),
) -> Importacao:
    conteudo = arquivo.file.read()
    try:
        importacao_orm = importacao_service.processar_arquivo_venda(
            db, id_mercado, arquivo.filename or "arquivo.csv", conteudo
        )
    except importacao_service.ArquivoJaProcessado as exc:
        raise HTTPException(
            status_code=409,
            detail=f"Arquivo já processado anteriormente (importação #{exc.args[0]}).",
        )
    except ArquivoInvalido as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    return Importacao.model_validate(importacao_orm, from_attributes=True)


@router.get("/{id_importacao}", response_model=Importacao)
def obter_importacao(
    id_importacao: int,
    id_mercado: int = Depends(obter_id_mercado_atual),
    db: Session = Depends(get_db),
) -> Importacao:
    try:
        importacao_orm = importacao_service.obter_importacao(db, id_mercado, id_importacao)
    except importacao_service.ImportacaoNaoEncontrada:
        raise HTTPException(status_code=404, detail="Importação não encontrada.")
    return Importacao.model_validate(importacao_orm, from_attributes=True)


@router.get("/{id_importacao}/itens", response_model=list[ItemImportacao])
def listar_itens_importacao(
    id_importacao: int,
    id_mercado: int = Depends(obter_id_mercado_atual),
    db: Session = Depends(get_db),
) -> list[ItemImportacao]:
    try:
        itens = importacao_service.listar_itens_importacao(db, id_mercado, id_importacao)
    except importacao_service.ImportacaoNaoEncontrada:
        raise HTTPException(status_code=404, detail="Importação não encontrada.")
    return [ItemImportacao.model_validate(item, from_attributes=True) for item in itens]
