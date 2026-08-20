# Valida — backend

Esqueleto inicial do backend (Fase 1). Ainda sem banco de dados, WhatsApp,
Meta ou provedor de IA conectados — ver `../CLAUDE.md` e `../docs/` para o
plano completo e as regras de negócio.

## Como rodar localmente

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
uvicorn app.main:app --reload
```

Depois de subir, verifique em `http://127.0.0.1:8000/health`.
