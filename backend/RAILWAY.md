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
5. **Serviço de cron separado, para a geração automática do relatório
   diário da Gestão Preventiva (RN08)**, nome sugerido
   `cron-relatorio-diario-preventivo`, apontando para o mesmo
   repositório/Root Directory (`backend`), mas com:
   - **Start Command** sobrescrito para
     `python scripts/gerar_relatorios_diarios.py`
   - **Cron Schedule** definido no painel do serviço — recomendado
     `*/30 * * * *`, ou seja, **uma tentativa de execução a cada 30
     minutos**, todos os dias. O Railway interpreta esse agendamento em
     **UTC**, não no fuso de nenhum mercado nem do servidor — mas isso
     não afeta a correção do resultado: o horário efetivo de cada
     mercado é decidido pela própria aplicação, usando o fuso **local**
     de cada mercado (`agora_do_mercado`, RN01), independente da hora
     UTC em que o Railway de fato disparou a execução. Rodar a cada 30
     minutos serve só para não deixar passar muito tempo entre o
     horário configurado e a geração de fato, e para recuperar
     automaticamente uma execução perdida ainda dentro do mesmo dia.
   - Se uma execução anterior ainda estiver em andamento quando a
     próxima estiver agendada para começar, o Railway pode pular essa
     próxima execução (comportamento padrão de cron jobs da plataforma)
     — inofensivo aqui, porque a próxima tentativa (30 minutos depois)
     cobre o mesmo trabalho sem duplicar nada.
   - O processo sempre termina sozinho depois de rodar: `main()` do
     script é síncrono, sem thread nem processo em segundo plano — ele
     roda `gerar_para_mercados_ativos` uma vez, fecha a `Session` no
     `finally` e encerra (com código 0 ou 1, conforme o resultado).
   - Ao contrário do item 4 (RN03), **só `DATABASE_URL` é realmente
     necessária** aqui — este script não usa `MERCADO_API_KEYS`,
     `ADMIN_API_KEY` nem nenhuma variável do WhatsApp (não abre nenhum
     endpoint HTTP, não autentica nada). É a mesma `DATABASE_URL`
     herdada do plugin de Postgres já usado pelo serviço web — não um
     banco separado.
   - Geração duplicada do mesmo relatório no mesmo dia não é um risco:
     `relatorio_acao_diaria_service.gerar_ou_obter` já é idempotente por
     `(id_mercado, data_referencia)` — rodar o script várias vezes no
     mesmo dia nunca cria um segundo relatório para o mesmo mercado.
   - Mercado com `relatorio_diario_ativo=True` mas sem
     `horario_relatorio_diario` configurado é ignorado nessa execução
     (sem gerar, sem horário padrão, sem desativar o mercado) e aparece
     listado no resumo impresso pelo script, para chamar atenção do
     time operacional.
   - Erro num mercado individual não impede os demais — é isolado,
     aparece no resumo, e faz o script sair com código 1 ao final (para
     o Railway registrar a execução como falha, ainda que os outros
     mercados tenham sido processados normalmente).
   - Uma falha geral (ex.: banco indisponível) propaga como exceção não
     tratada — a sessão ainda é fechada corretamente antes disso, e a
     próxima execução do cron (até 30 minutos depois) tenta de novo.
   - Este serviço **nunca inicia o FastAPI/uvicorn** — o Start Command
     sobrescrito substitui inteiramente o `startCommand` do
     `railway.toml` só para este serviço específico; ele roda o script
     avulso e termina, exatamente como já acontece com o serviço de cron
     da RN03 (item 4 acima).

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
