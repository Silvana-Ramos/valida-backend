# Checkpoint de validação — Migration 0005 (`0005_unique_telefone_usuarios`)

## 1. Objetivo

Registrar a validação técnica da Migration 0005 (adiciona `UNIQUE` em
`usuarios.telefone_whatsapp` — pré-requisito para a autenticação real via
webhook do WhatsApp, que precisa mapear deterministicamente um número de
telefone verificado para exatamente um usuário/mercado), antes de
qualquer execução no banco principal. Migration puramente aditiva de
constraint: nenhuma coluna, tabela ou tipo é criado/alterado/removido, e
nenhuma linha é tocada.

## 2. Origem dos ambientes de teste

Diferente das validações anteriores, aqui nenhum banco de teste existente
estava em `alembic_version = 0004` (o head anterior à 0005) no início
desta validação. Uma origem dedicada e reutilizável foi criada, sem tocar
no banco principal `valida` nem em nenhum banco de teste já existente:

1. `valida_m0005_origem_0004` criado via `CREATE DATABASE ... TEMPLATE`
   a partir de `valida_m0004_origem_0003` (banco de teste em estado
   `0003`, já existente e reutilizável desde a validação da Migration
   0004) — o template não é alterado por essa operação.
2. Upgrade `0003 → 0004` aplicado nessa cópia nova, usando a Migration
   0004 já validada em dois ciclos anteriormente — nenhum risco novo.
   Estrutura pós-upgrade conferida: `alembic_version = 0004`.

## 3. Cycle1 — concluído

- **Ambiente:** `valida_m0005_cycle1`, criado via `CREATE DATABASE ...
  TEMPLATE valida_m0005_origem_0004` (estado `0004`).
- **Upgrade (`0004 → 0005`):** executado com sucesso, com as verificações
  protegidas prévias (`current_database()`, `alembic_version` atual,
  `script_location`, SHA256 do arquivo de migration —
  `88651f1f80b7d9c3c9cf5a0a9248796871d59b10a689d12db819cacec9b3af89`).
  Estrutura pós-upgrade conferida: constraint `uq_usuarios_telefone_whatsapp`
  criada com `contype = 'u'` (UNIQUE) em `pg_constraint`.
- **Downgrade (`0005 → 0004`):** executado com sucesso, mesmas
  verificações protegidas (`alembic_version` esperado `0005`). Estrutura
  pós-downgrade conferida: constraint removida (`pg_constraint` não
  retorna mais nenhuma linha para `uq_usuarios_telefone_whatsapp`).
- **Não interferência:** `valida_m0005_origem_0004` (template) e `valida`
  (banco principal) confirmados inalterados após o processo.

## 4. Cycle2 (repetibilidade) — concluído

- **Ambiente:** `valida_m0005_cycle2`, criado de forma independente a
  partir do mesmo template `valida_m0005_origem_0004` — banco descartável
  distinto de `valida_m0005_cycle1` (já mutado pelo teste anterior),
  evitando reaproveitar um banco de teste já usado.
- **Upgrade (`0004 → 0005`):** executado com sucesso, sem nenhum erro,
  com as mesmas verificações protegidas. Resultado estrutural idêntico ao
  cycle1 — mesma constraint criada.
- **Downgrade (`0005 → 0004`):** executado com sucesso, resultado
  idêntico ao cycle1 — constraint removida.
- **Não interferência:** `valida_m0005_cycle1`, `valida_m0005_origem_0004`
  e `valida` confirmados inalterados após todo o processo do cycle2.

## 5. Confirmação de repetibilidade

Confirmada. O cycle2, com origem independente do cycle1 (banco
descartável distinto, mesmo template de origem), produziu resultado
estrutural idêntico — mesma constraint criada no upgrade, mesma remoção
limpa no downgrade.

## 6. Incidente durante a validação (ambiente, não a migration)

No meio desta validação, o serviço do PostgreSQL no Windows
(`postgresql-x64-18`) foi encontrado **parado**, causando timeouts em
sucessivas tentativas de conexão (inclusive em leituras simples contra o
banco principal, que normalmente respondem de imediato). Diagnosticado
por eliminação: `pg_stat_activity` não mostrava nenhuma sessão travada
nem lock pendente contra o banco de teste, o que descartou um problema de
concorrência/lock antes de se verificar o status do serviço em si.
Reiniciar o serviço exigiu privilégio administrativo, fora do alcance da
sessão automatizada — o usuário reiniciou manualmente. Nenhum dado foi
perdido ou corrompido: `alembic_version` de todos os bancos envolvidos
permaneceu consistente (`0003`/`0004`, conforme o estado antes do
incidente) durante toda a interrupção. Não é um problema da migration em
si, só um registro operacional para referência futura caso timeouts
semelhantes ocorram de novo.

## 7. Status geral

Migration 0005 validada em dois ciclos completos e independentes (upgrade
+ downgrade reversível cada), com repetibilidade confirmada entre eles.
**Tecnicamente apta para futura execução no banco principal (`valida`)**,
condicionada a:
- Execução isolada, como ação explicitamente autorizada em separado desta
  validação técnica (esta sessão não incluiu execução no banco
  principal).
- Um backup do banco `valida` imediatamente antes da execução, verificado
  (caminho, tamanho, SHA256, `pg_restore --list`), como praticado nas
  Migrations 0002-0004.
- Confirmação de `alembic_version = 0004` no banco principal antes de
  iniciar (já é o estado atual, confirmado nesta sessão).
- **Atenção adicional específica desta migration:** se já existir
  duplicidade real em `usuarios.telefone_whatsapp` no banco principal, o
  `ALTER TABLE ADD CONSTRAINT` falha de forma limpa (sem alterar nada) —
  mas isso só se confirma rodando de fato contra os dados reais de
  produção; não há como saber de antemão sem consultar `valida`
  diretamente antes da execução.

---

## 8. Execução em produção (2026-08-20)

A Migration 0005 foi **executada no banco principal `valida`**, com
autorização explícita e separada, comando a comando, seguindo o plano
protegido de `docs/revisao-prontidao-migration-0005.md` (seção 7).

- **Checagem de duplicidade** (pré-condição, seção 4, item 6): `0 linhas`
  — nenhuma duplicidade em `usuarios.telefone_whatsapp`.
- **Medição de volume** (seção 6): `usuarios` com 0 linhas / 16 kB —
  confirmado ao vivo, condizente com o registro do checkpoint da
  Migration 0003.
- **Backup pré-migration:** `valida_pre_migration_0005_20260820_161402.dump`,
  em `C:\Users\Silvana\Valida_Backups\`. Verificado antes do upgrade —
  45.138 bytes, SHA256
  `E764999CB3C90F1A81CBED2C0F64B19F75E1EB072366475562020568F252AB1B`,
  `pg_restore --list` confirmando `dbname: valida`, 122 TOC entries,
  formato CUSTOM.
- **Incidente durante a sessão de execução:** o serviço do PostgreSQL foi
  encontrado parado mais de uma vez durante a preparação (ver seção 6 do
  checkpoint). Na investigação mais detalhada desta execução, identificou-se
  a causa raiz real: o supervisor do serviço Windows (`pg_ctl.exe
  runservice`) havia se desconectado da árvore de processos do Postgres,
  deixando uma instância **órfã** (PID do `postmaster.pid` datado de
  01/08/2026) rodando sem supervisão — por isso tentativas de iniciar o
  serviço "paravam imediatamente" (o novo `pg_ctl` detectava o postmaster
  órfão ainda vivo e recusava iniciar uma segunda instância). Resolvido
  encerrando o processo órfão com `pg_ctl stop -m fast` (precisou de
  privilégio administrativo, fora do alcance da sessão automatizada — o
  usuário executou manualmente) e reiniciando o serviço do zero. Nenhum
  dado foi perdido ou corrompido durante o incidente.
- **Verificações protegidas pré-upgrade:** `current_database()` = `valida`,
  `alembic_version` atual = `0004` (confirmado por leitura antes do
  upgrade), `script_location` resolvido corretamente, SHA256 do arquivo
  de migration = `88651f1f80b7d9c3c9cf5a0a9248796871d59b10a689d12db819cacec9b3af89`
  (idêntico ao validado nos dois ciclos).
- **Upgrade `0004 → 0005`:** executado com sucesso.
- **Verificação pós-upgrade:** `alembic_version = 0005`; constraint
  `uq_usuarios_telefone_whatsapp` presente em `pg_constraint` com
  `contype = 'u'` (UNIQUE) — confirmado por duas vias independentes (a
  saída do próprio `command.upgrade` e uma leitura separada via `psql`).
  Nenhuma linha existente foi alterada (tabela já estava vazia).

**Migration 0005 em produção desde 2026-08-20.** `usuarios.telefone_whatsapp`
agora é `UNIQUE` — pré-requisito satisfeito para a futura resolução de
identidade via webhook do WhatsApp (ver revisão "o que falta para
autenticação real"), que segue como fase futura separada, ainda não
iniciada.
