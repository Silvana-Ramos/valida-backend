"""Conversão de chave de API -> identidade confiável (solução mínima para
o piloto, sem tabela nova nem migration — ver Settings.mercado_api_keys /
Settings.admin_api_key).

O cliente nunca informa id_mercado diretamente; só a chave secreta do seu
mercado, no header abaixo. Uso futuro: `Depends(obter_id_mercado_atual)`
nos endpoints que hoje aceitam id_mercado vindo do cliente.
"""

import hashlib
import hmac

from fastapi import Header, HTTPException, status

from app.core.config import settings

MERCADO_API_KEY_HEADER = "X-Mercado-Api-Key"
ADMIN_API_KEY_HEADER = "X-Admin-Api-Key"
WHATSAPP_SIGNATURE_HEADER = "X-Hub-Signature-256"


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


def validar_assinatura_whatsapp(corpo: bytes, assinatura_recebida: str | None) -> bool:
    """Valida a assinatura `X-Hub-Signature-256` que a Meta envia em toda
    chamada `POST /whatsapp/webhook` (ainda não implementado — fatia 7).

    Diferente de `obter_id_mercado_atual`/`obter_admin_autenticado`, não é
    uma dependency do FastAPI: o HMAC precisa dos bytes brutos exatos do
    corpo, como a Meta os assinou — não do JSON já desserializado pelo
    Pydantic, que poderia ter espaçamento/ordem de chaves diferente e
    invalidar a assinatura silenciosamente. Pegar o corpo bruto em FastAPI
    exige `await request.body()` (contexto assíncrono); por isso esta
    função é pura e chamada manualmente pelo router, que resolve o corpo e
    o header antes de chamá-la.

    Retorna `bool` em vez de levantar `HTTPException` — quem decide o que
    fazer com `False` (responder 403, não processar nada) é o router,
    porque esta função não sabe nada sobre HTTP, só sobre criptografia.
    `not settings.whatsapp_app_secret` falha fechado, mesmo critério já
    usado em `obter_admin_autenticado`: sem segredo configurado no
    servidor, nenhuma assinatura é aceita como válida."""
    if not settings.whatsapp_app_secret or not assinatura_recebida:
        return False
    esperado = "sha256=" + hmac.new(
        settings.whatsapp_app_secret.encode(), corpo, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(esperado, assinatura_recebida)
