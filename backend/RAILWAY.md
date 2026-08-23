# Deploy no Railway — notas operacionais

Este documento acompanha `railway.toml` e `.python-version`. Nenhum
deploy foi feito ainda — preparado apenas para quando a decisão de
hospedagem for confirmada e executada.

## O que os arquivos cobrem

- `railway.toml`: builder Nixpacks (detecta `requirements.txt`
  automaticamente) e comando de start do serviço web
  (`uvicorn app.main:app --host 0.0.0.0 --port $PORT` — `$PORT` é
  injetado pelo Railway).
- `.python-version`: fixa `3.14`, mesma versão usada localmente nesta
  sessão.

## O que precisa ser configurado manualmente no painel do Railway

Nem tudo é expressável em arquivo — o Railway configura alguns itens
por serviço, no painel:

1. **Root Directory do serviço = `backend`** — o repositório tem
   `docs/` e `backend/` como irmãos; sem isso, o Nixpacks não encontra
   `requirements.txt`.
2. **Plugin de PostgreSQL gerenciado do Railway**, adicionado ao mesmo
   projeto. Ele injeta `DATABASE_URL` automaticamente como
   `postgresql://...` (sem `+psycopg2`) — compatível sem nenhuma
   mudança de código, porque o SQLAlchemy já usa `psycopg2` como driver
   padrão para esse esquema (e `psycopg2-binary` já está em
   `requirements.txt`).
3. **Variáveis de ambiente do serviço web** (nenhuma tem valor
   default seguro em produção — ver `app/core/config.py`):
   - `MERCADO_API_KEYS` (JSON)
   - `ADMIN_API_KEY`
   - `WHATSAPP_VERIFY_TOKEN`
   - `WHATSAPP_APP_SECRET`
   - `WHATSAPP_ACCESS_TOKEN`
   - `WHATSAPP_PHONE_NUMBER_ID`
   - `APP_ENV=production`
4. **Serviço de cron separado, para RN03**, apontando para o mesmo
   repositório/Root Directory (`backend`), mas com:
   - **Start Command** sobrescrito para
     `python scripts/recalcular_risco_diario.py`
   - **Cron Schedule** definido no painel do serviço (ex.: `0 6 * * *`
     para rodar às 6h todo dia) — é uma configuração por serviço no
     Railway, não um campo do `railway.toml` compartilhado com o
     serviço web.
   - Mesmas variáveis de ambiente do item 3 (pelo menos `DATABASE_URL`,
     herdada do plugin do Postgres se estiver no mesmo projeto).

## Migrations — NUNCA automáticas no deploy

Deliberadamente **não** há nenhum `alembic upgrade head` no
`startCommand` nem em nenhum hook de deploy. Este projeto segue um
protocolo estrito para qualquer migration em produção — backup
verificado, checagens protegidas, execução comando a comando com
aprovação explícita (ver `docs/checkpoint-migration-0006.md` e
`docs/revisao-prontidao-migration-0006.md` como exemplo do processo).
Rodar migrations automaticamente a cada deploy quebraria esse
protocolo. Migrations continuam sendo aplicadas manualmente, à parte
do deploy do código.

## Nenhum deploy foi executado

Este documento e os dois arquivos de configuração foram preparados,
não aplicados. Criar o projeto no Railway, conectar o repositório
(ainda só local — precisa de um remoto git, ex. GitHub, antes de
qualquer deploy) e configurar os itens acima são passos que exigem
autorização explícita e separada, como qualquer ação que afete
infraestrutura real.
