from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import obter_id_mercado_atual
from app.schemas.enums import StatusLote
from app.schemas.historico_acao import HistoricoAcao
from app.schemas.lote import Lote, LoteCreateRequest, LoteEditRequest
from app.schemas.movimentacao_estoque import (
    AjusteEstoqueRequest,
    EntradaEstoqueRequest,
    MovimentacaoEstoque,
    RetiradaEstoqueRequest,
    VendaEstoqueRequest,
)
from app.services import lote_service, movimentacao_service
from app.services.lote_service import AcaoInvalidaParaStatus, LoteNaoEncontrado
from app.services.movimentacao_service import (
    LoteDescartadoNaoAceitaEntrada,
    LoteNaoVencidoNaoAceitaRetirada,
    LoteVencidoNaoAceitaVenda,
    MovimentacaoEstornadaNaoEncontrada,
    MovimentacaoJaEstornada,
    SaldoInsuficienteParaAjuste,
    SaldoInsuficienteParaRetirada,
    SaldoInsuficienteParaVenda,
)

router = APIRouter(prefix="/lotes", tags=["lotes"])


@router.post("", response_model=Lote, status_code=201)
def criar_lote(
    request: LoteCreateRequest,
    id_mercado: int = Depends(obter_id_mercado_atual),
    db: Session = Depends(get_db),
) -> Lote:
    return lote_service.criar_pendente(db, id_mercado, request)


@router.get("", response_model=list[Lote])
def listar_lotes(
    status: StatusLote | None = None,
    id_mercado: int = Depends(obter_id_mercado_atual),
    db: Session = Depends(get_db),
) -> list[Lote]:
    return lote_service.listar(db, id_mercado, status=status)


@router.get("/{id_lote}", response_model=Lote)
def obter_lote(
    id_lote: int,
    id_mercado: int = Depends(obter_id_mercado_atual),
    db: Session = Depends(get_db),
) -> Lote:
    try:
        return lote_service.obter(db, id_mercado, id_lote)
    except LoteNaoEncontrado:
        raise HTTPException(status_code=404, detail="Lote não encontrado.")


@router.patch("/{id_lote}", response_model=Lote)
def editar_lote(
    id_lote: int,
    request: LoteEditRequest,
    id_mercado: int = Depends(obter_id_mercado_atual),
    db: Session = Depends(get_db),
) -> Lote:
    try:
        return lote_service.editar_pendente(db, id_mercado, id_lote, request)
    except LoteNaoEncontrado:
        raise HTTPException(status_code=404, detail="Lote não encontrado.")
    except AcaoInvalidaParaStatus:
        raise HTTPException(
            status_code=409,
            detail="Só é possível editar um lote com status pendente_confirmacao.",
        )


@router.post("/{id_lote}/confirmar", response_model=Lote)
def confirmar_lote(
    id_lote: int,
    id_mercado: int = Depends(obter_id_mercado_atual),
    db: Session = Depends(get_db),
) -> Lote:
    try:
        return lote_service.confirmar(db, id_mercado, id_lote)
    except LoteNaoEncontrado:
        raise HTTPException(status_code=404, detail="Lote não encontrado.")
    except AcaoInvalidaParaStatus:
        raise HTTPException(
            status_code=409,
            detail="Só é possível confirmar um lote com status pendente_confirmacao.",
        )


@router.post("/{id_lote}/cancelar", status_code=204)
def cancelar_lote(
    id_lote: int,
    id_mercado: int = Depends(obter_id_mercado_atual),
    db: Session = Depends(get_db),
) -> None:
    try:
        lote_service.cancelar(db, id_mercado, id_lote)
    except LoteNaoEncontrado:
        raise HTTPException(status_code=404, detail="Lote não encontrado.")
    except AcaoInvalidaParaStatus:
        raise HTTPException(
            status_code=409,
            detail="Só é possível cancelar um lote com status pendente_confirmacao.",
        )


@router.post("/{id_lote}/entrada", response_model=MovimentacaoEstoque, status_code=201)
def registrar_entrada_lote(
    id_lote: int,
    request: EntradaEstoqueRequest,
    id_mercado: int = Depends(obter_id_mercado_atual),
    db: Session = Depends(get_db),
) -> MovimentacaoEstoque:
    try:
        return movimentacao_service.registrar_entrada(db, id_mercado, id_lote, request)
    except LoteNaoEncontrado:
        raise HTTPException(status_code=404, detail="Lote não encontrado.")
    except AcaoInvalidaParaStatus:
        raise HTTPException(
            status_code=409,
            detail="Só é possível registrar entrada em um lote com status confirmado.",
        )
    except LoteDescartadoNaoAceitaEntrada:
        raise HTTPException(status_code=409, detail="Lote descartado não aceita nova entrada.")


@router.post("/{id_lote}/venda", response_model=MovimentacaoEstoque, status_code=201)
def registrar_venda_lote(
    id_lote: int,
    request: VendaEstoqueRequest,
    id_mercado: int = Depends(obter_id_mercado_atual),
    db: Session = Depends(get_db),
) -> MovimentacaoEstoque:
    try:
        return movimentacao_service.registrar_venda(db, id_mercado, id_lote, request)
    except LoteNaoEncontrado:
        raise HTTPException(status_code=404, detail="Lote não encontrado.")
    except AcaoInvalidaParaStatus:
        raise HTTPException(
            status_code=409,
            detail="Só é possível registrar venda em um lote com status confirmado.",
        )
    except LoteVencidoNaoAceitaVenda:
        raise HTTPException(
            status_code=409,
            detail="Lote vencido não pode ser vendido; registre uma retirada por vencimento.",
        )
    except SaldoInsuficienteParaVenda:
        raise HTTPException(status_code=409, detail="Saldo insuficiente para essa venda.")


@router.post("/{id_lote}/retirada", response_model=MovimentacaoEstoque, status_code=201)
def registrar_retirada_lote(
    id_lote: int,
    request: RetiradaEstoqueRequest,
    id_mercado: int = Depends(obter_id_mercado_atual),
    db: Session = Depends(get_db),
) -> MovimentacaoEstoque:
    try:
        return movimentacao_service.registrar_retirada(db, id_mercado, id_lote, request)
    except LoteNaoEncontrado:
        raise HTTPException(status_code=404, detail="Lote não encontrado.")
    except AcaoInvalidaParaStatus:
        raise HTTPException(
            status_code=409,
            detail="Só é possível registrar retirada em um lote com status confirmado.",
        )
    except LoteNaoVencidoNaoAceitaRetirada:
        raise HTTPException(
            status_code=409, detail="Só é possível retirar por vencimento um lote já vencido."
        )
    except SaldoInsuficienteParaRetirada:
        raise HTTPException(status_code=409, detail="Saldo insuficiente para essa retirada.")


@router.post("/{id_lote}/ajuste", response_model=MovimentacaoEstoque, status_code=201)
def registrar_ajuste_lote(
    id_lote: int,
    request: AjusteEstoqueRequest,
    id_mercado: int = Depends(obter_id_mercado_atual),
    db: Session = Depends(get_db),
) -> MovimentacaoEstoque:
    try:
        return movimentacao_service.registrar_ajuste(db, id_mercado, id_lote, request)
    except LoteNaoEncontrado:
        raise HTTPException(status_code=404, detail="Lote não encontrado.")
    except AcaoInvalidaParaStatus:
        raise HTTPException(
            status_code=409,
            detail="Só é possível registrar ajuste em um lote com status confirmado.",
        )
    except MovimentacaoEstornadaNaoEncontrada:
        raise HTTPException(
            status_code=404, detail="Movimentação a estornar não encontrada nesse lote."
        )
    except MovimentacaoJaEstornada:
        raise HTTPException(
            status_code=409, detail="Essa movimentação já foi estornada por outro ajuste."
        )
    except LoteDescartadoNaoAceitaEntrada:
        raise HTTPException(
            status_code=409, detail="Lote descartado não aceita ajuste de entrada."
        )
    except SaldoInsuficienteParaAjuste:
        raise HTTPException(status_code=409, detail="Saldo insuficiente para esse ajuste.")


@router.get("/{id_lote}/historico", response_model=list[HistoricoAcao])
def historico_do_lote(
    id_lote: int,
    id_mercado: int = Depends(obter_id_mercado_atual),
    db: Session = Depends(get_db),
) -> list[HistoricoAcao]:
    try:
        return lote_service.historico_do_lote(db, id_mercado, id_lote)
    except LoteNaoEncontrado:
        raise HTTPException(status_code=404, detail="Lote não encontrado.")
