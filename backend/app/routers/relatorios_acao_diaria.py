from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import obter_id_mercado_atual
from app.schemas.acao_preventiva import (
    AcaoPreventiva,
    AcaoPreventivaCreateRequest,
    AcaoPreventivaEditRequest,
)
from app.schemas.item_relatorio_diario import ItemRelatorioDiario
from app.schemas.relatorio_acao_diaria import RelatorioAcaoDiario
from app.services import acao_preventiva_service, relatorio_acao_diaria_service
from app.services.acao_preventiva_service import (
    AcaoPreventivaNaoEncontrada,
    ItemRelatorioNaoEncontrado,
    StatusAcaoPreventivaInvalido,
)
from app.services.relatorio_acao_diaria_service import RelatorioNaoEncontrado
from app.services.usuario_service import UsuarioNaoEncontrado

router = APIRouter(prefix="/relatorios-acao-diaria", tags=["gestao-preventiva"])


@router.post("", response_model=RelatorioAcaoDiario)
def gerar_ou_obter_relatorio(
    id_mercado: int = Depends(obter_id_mercado_atual),
    db: Session = Depends(get_db),
) -> RelatorioAcaoDiario:
    return relatorio_acao_diaria_service.gerar_ou_obter(db, id_mercado)


@router.get("/{id_relatorio}/itens", response_model=list[ItemRelatorioDiario])
def listar_itens_relatorio(
    id_relatorio: int,
    id_mercado: int = Depends(obter_id_mercado_atual),
    db: Session = Depends(get_db),
) -> list[ItemRelatorioDiario]:
    try:
        return relatorio_acao_diaria_service.listar_itens(db, id_mercado, id_relatorio)
    except RelatorioNaoEncontrado:
        raise HTTPException(status_code=404, detail="Relatório não encontrado.")


@router.post("/itens/{id_item_relatorio}/acoes", response_model=AcaoPreventiva, status_code=201)
def registrar_acao_preventiva(
    id_item_relatorio: int,
    request: AcaoPreventivaCreateRequest,
    id_mercado: int = Depends(obter_id_mercado_atual),
    db: Session = Depends(get_db),
) -> AcaoPreventiva:
    try:
        return acao_preventiva_service.registrar(db, id_mercado, id_item_relatorio, request)
    except ItemRelatorioNaoEncontrado:
        raise HTTPException(status_code=404, detail="Item do relatório não encontrado.")
    except UsuarioNaoEncontrado:
        raise HTTPException(status_code=404, detail="Usuário responsável não encontrado.")


@router.patch("/acoes/{id_acao_preventiva}", response_model=AcaoPreventiva)
def atualizar_acao_preventiva(
    id_acao_preventiva: int,
    request: AcaoPreventivaEditRequest,
    id_mercado: int = Depends(obter_id_mercado_atual),
    db: Session = Depends(get_db),
) -> AcaoPreventiva:
    try:
        return acao_preventiva_service.atualizar(db, id_mercado, id_acao_preventiva, request)
    except AcaoPreventivaNaoEncontrada:
        raise HTTPException(status_code=404, detail="Ação preventiva não encontrada.")
    except StatusAcaoPreventivaInvalido as exc:
        raise HTTPException(status_code=422, detail=f"Status inválido: {exc}.")
