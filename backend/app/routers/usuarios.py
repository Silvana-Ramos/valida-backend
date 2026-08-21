from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import obter_id_mercado_atual
from app.schemas.usuario import Usuario, UsuarioCreateRequest, UsuarioUpdateRequest
from app.services import usuario_service
from app.services.usuario_service import TelefoneJaCadastrado, UsuarioNaoEncontrado

router = APIRouter(prefix="/usuarios", tags=["usuarios"])


@router.post("", response_model=Usuario, status_code=201)
def criar_usuario(
    request: UsuarioCreateRequest,
    id_mercado: int = Depends(obter_id_mercado_atual),
    db: Session = Depends(get_db),
) -> Usuario:
    try:
        return usuario_service.criar(db, id_mercado, request)
    except TelefoneJaCadastrado:
        raise HTTPException(
            status_code=409, detail="Já existe um usuário com esse telefone_whatsapp."
        )


@router.get("", response_model=list[Usuario])
def listar_usuarios(
    id_mercado: int = Depends(obter_id_mercado_atual), db: Session = Depends(get_db)
) -> list[Usuario]:
    return usuario_service.listar(db, id_mercado)


@router.get("/{id_usuario}", response_model=Usuario)
def obter_usuario(
    id_usuario: int,
    id_mercado: int = Depends(obter_id_mercado_atual),
    db: Session = Depends(get_db),
) -> Usuario:
    try:
        return usuario_service.obter(db, id_mercado, id_usuario)
    except UsuarioNaoEncontrado:
        raise HTTPException(status_code=404, detail="Usuário não encontrado.")


@router.patch("/{id_usuario}", response_model=Usuario)
def atualizar_usuario(
    id_usuario: int,
    request: UsuarioUpdateRequest,
    id_mercado: int = Depends(obter_id_mercado_atual),
    db: Session = Depends(get_db),
) -> Usuario:
    try:
        return usuario_service.atualizar(db, id_mercado, id_usuario, request)
    except UsuarioNaoEncontrado:
        raise HTTPException(status_code=404, detail="Usuário não encontrado.")
    except TelefoneJaCadastrado:
        raise HTTPException(
            status_code=409, detail="Já existe um usuário com esse telefone_whatsapp."
        )
