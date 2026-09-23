from fastapi import FastAPI

from app.core.config import settings
from app.routers import health, importacoes, lotes, mercados, produtos, relatorios_acao_diaria, usuarios, whatsapp

app = FastAPI(title=settings.app_name)

app.include_router(health.router)
app.include_router(lotes.router)
app.include_router(mercados.router)
app.include_router(produtos.router)
app.include_router(importacoes.router)
app.include_router(usuarios.router)
app.include_router(whatsapp.router)
app.include_router(relatorios_acao_diaria.router)
