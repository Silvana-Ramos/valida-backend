"""Webhook da Cloud API da Meta (WhatsApp) — fatia 7, última do plano
de integração. `POST /whatsapp/webhook` é o primeiro endpoint `async
def` do projeto (todo o resto é síncrono sobre `Session` do
SQLAlchemy): precisa dos bytes brutos exatos do corpo da requisição
para validar a assinatura HMAC (`app/core/security.py`), e isso só é
possível via `await request.body()`. O processamento em si
(`processar_webhook`) continua síncrono/bloqueante — chamado direto
daqui, sem despachar para um threadpool; aceitável no volume esperado
do piloto, mas registrado como simplificação deliberada, não descuido."""

import json

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import PlainTextResponse
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.core.security import WHATSAPP_SIGNATURE_HEADER, validar_assinatura_whatsapp
from app.services.whatsapp_webhook_service import processar_webhook

router = APIRouter(prefix="/whatsapp", tags=["whatsapp"])


@router.get("/webhook", response_class=PlainTextResponse)
def verificar_webhook(
    hub_mode: str = Query(alias="hub.mode"),
    hub_verify_token: str = Query(alias="hub.verify_token"),
    hub_challenge: str = Query(alias="hub.challenge"),
) -> str:
    if (
        hub_mode != "subscribe"
        or not settings.whatsapp_verify_token
        or hub_verify_token != settings.whatsapp_verify_token
    ):
        raise HTTPException(status_code=403, detail="Token de verificação inválido.")
    return hub_challenge


@router.post("/webhook")
async def receber_webhook(request: Request, db: Session = Depends(get_db)) -> dict:
    corpo = await request.body()
    assinatura = request.headers.get(WHATSAPP_SIGNATURE_HEADER)
    if not validar_assinatura_whatsapp(corpo, assinatura):
        raise HTTPException(status_code=403, detail="Assinatura inválida.")

    try:
        payload = json.loads(corpo)
    except ValueError:
        # Corpo não é JSON válido — nada a reprocessar reenviando;
        # responde 200 para a Meta não tentar de novo.
        return {"status": "ignorado"}

    processar_webhook(db, payload)
    return {"status": "ok"}
