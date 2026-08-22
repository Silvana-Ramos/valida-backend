"""Cliente de envio de mensagem de texto via WhatsApp Cloud API (Meta).

Wrapper fino sobre `POST /{PHONE_NUMBER_ID}/messages` da Graph API —
isolado do resto do fluxo (webhook, sessão de conversa, ainda não
implementados: fatias 5-7 do plano de integração). `telefone` é
recebido já resolvido e normalizado (`app/core/telefone.py`,
formato `55` + DDD + número, sem `+`) — a mesma convenção usada pelo
`wa_id` que a Meta envia/espera; esta função não normaliza nada.

`client` é sempre injetável e, nos testes, sempre um mock — nenhuma
chamada de rede real acontece na suíte de testes deste projeto.
"""

import httpx

from app.core.config import settings

GRAPH_API_VERSION = "v20.0"


class WhatsAppNaoConfigurado(Exception):
    pass


class EnvioWhatsAppFalhou(Exception):
    pass


def enviar_mensagem_texto(
    telefone: str, texto: str, client: httpx.Client | None = None
) -> None:
    if not settings.whatsapp_access_token or not settings.whatsapp_phone_number_id:
        raise WhatsAppNaoConfigurado(
            "WHATSAPP_ACCESS_TOKEN/WHATSAPP_PHONE_NUMBER_ID não configurados no servidor."
        )

    url = (
        f"https://graph.facebook.com/{GRAPH_API_VERSION}/"
        f"{settings.whatsapp_phone_number_id}/messages"
    )
    payload = {
        "messaging_product": "whatsapp",
        "to": telefone,
        "type": "text",
        "text": {"body": texto},
    }
    headers = {"Authorization": f"Bearer {settings.whatsapp_access_token}"}

    client_proprio = client is None
    if client is None:
        client = httpx.Client(timeout=10.0)
    try:
        resposta = client.post(url, json=payload, headers=headers)
        if resposta.status_code >= 400:
            raise EnvioWhatsAppFalhou(
                f"Envio falhou (status {resposta.status_code}): {resposta.text}"
            )
    finally:
        if client_proprio:
            client.close()
