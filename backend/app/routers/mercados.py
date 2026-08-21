from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import obter_admin_autenticado
from app.schemas.mercado import Mercado, MercadoCreateRequest, MercadoUpdateRequest
from app.schemas.usuario import Usuario, UsuarioCreateRequest
from app.services import mercado_service, usuario_service
from app.services.mercado_service import MercadoNaoEncontrado, TelefoneJaCadastrado

router = APIRouter(
    prefix="/mercados", tags=["mercados"], dependencies=[Depends(obter_admin_autenticado)]
)


@router.post("", response_model=Mercado, status_code=201)
def criar_mercado(request: MercadoCreateRequest, db: Session = Depends(get_db)) -> Mercado:
    try:
        return mercado_service.criar(db, request)
    except TelefoneJaCadastrado:
        raise HTTPException(
            status_code=409, detail="Já existe um mercado com esse telefone_whatsapp."
        )


@router.get("", response_model=list[Mercado])
def listar_mercados(db: Session = Depends(get_db)) -> list[Mercado]:
    return mercado_service.listar(db)


@router.get("/{id_mercado}", response_model=Mercado)
def obter_mercado(id_mercado: int, db: Session = Depends(get_db)) -> Mercado:
    try:
        return mercado_service.obter(db, id_mercado)
    except MercadoNaoEncontrado:
        raise HTTPException(status_code=404, detail="Mercado não encontrado.")


@router.patch("/{id_mercado}", response_model=Mercado)
def atualizar_mercado(
    id_mercado: int, request: MercadoUpdateRequest, db: Session = Depends(get_db)
) -> Mercado:
    try:
        return mercado_service.atualizar(db, id_mercado, request)
    except MercadoNaoEncontrado:
        raise HTTPException(status_code=404, detail="Mercado não encontrado.")
    except TelefoneJaCadastrado:
        raise HTTPException(
            status_code=409, detail="Já existe um mercado com esse telefone_whatsapp."
        )


@router.post("/{id_mercado}/usuarios", response_model=Usuario, status_code=201)
def bootstrap_usuario_do_mercado(
    id_mercado: int, request: UsuarioCreateRequest, db: Session = Depends(get_db)
) -> Usuario:
    """Cria o primeiro usuário de um mercado novo (bootstrap), admin-only —
    o próprio mercado ainda não tem uma chave de API própria nesse ponto do
    onboarding, então não dá pra usar o cadastro self-service de
    `POST /usuarios` (que depende de `obter_id_mercado_atual`)."""
    try:
        mercado_service.obter(db, id_mercado)
    except MercadoNaoEncontrado:
        raise HTTPException(status_code=404, detail="Mercado não encontrado.")

    try:
        return usuario_service.criar(db, id_mercado, request)
    except usuario_service.TelefoneJaCadastrado:
        raise HTTPException(
            status_code=409, detail="Já existe um usuário com esse telefone_whatsapp."
        )
