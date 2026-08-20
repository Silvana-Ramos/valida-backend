"""Conversão de chave de API por mercado -> id_mercado (solução mínima para
o piloto, sem tabela nova nem migration — ver Settings.mercado_api_keys).

O cliente nunca informa id_mercado diretamente; só a chave secreta do seu
mercado, no header abaixo. Uso futuro: `Depends(obter_id_mercado_atual)`
nos endpoints que hoje aceitam id_mercado vindo do cliente.
"""

from fastapi import Header, HTTPException, status

from app.core.config import settings

MERCADO_API_KEY_HEADER = "X-Mercado-Api-Key"


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
