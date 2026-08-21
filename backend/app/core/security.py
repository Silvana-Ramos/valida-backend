"""Conversão de chave de API -> identidade confiável (solução mínima para
o piloto, sem tabela nova nem migration — ver Settings.mercado_api_keys /
Settings.admin_api_key).

O cliente nunca informa id_mercado diretamente; só a chave secreta do seu
mercado, no header abaixo. Uso futuro: `Depends(obter_id_mercado_atual)`
nos endpoints que hoje aceitam id_mercado vindo do cliente.
"""

from fastapi import Header, HTTPException, status

from app.core.config import settings

MERCADO_API_KEY_HEADER = "X-Mercado-Api-Key"
ADMIN_API_KEY_HEADER = "X-Admin-Api-Key"


def obter_id_mercado_atual(
    x_mercado_api_key: str | None = Header(default=None, alias=MERCADO_API_KEY_HEADER),
) -> int:
    id_mercado = settings.mercado_api_keys.get(x_mercado_api_key) if x_mercado_api_key else None
    if id_mercado is None:
        # Mesma mensagem para header ausente ou chave inválida — não revela
        # qual dos dois casos ocorreu.
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Chave de API do mercado ausente ou inválida.",
        )
    return id_mercado


def obter_admin_autenticado(
    x_admin_api_key: str | None = Header(default=None, alias=ADMIN_API_KEY_HEADER),
) -> None:
    """Autenticação para os endpoints admin-only de onboarding (RN05:
    criar mercado é a única ação que não pode passar pela chave de um
    mercado, já que o mercado ainda não existe).

    `not settings.admin_api_key` falha fechado quando a chave não está
    configurada no servidor — sem isso, `None != None` deixaria passar
    qualquer requisição sem header nenhum."""
    if not settings.admin_api_key or x_admin_api_key != settings.admin_api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Chave de administrador ausente ou inválida.",
        )
