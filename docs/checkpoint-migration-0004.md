# Checkpoint de validação — Migration 0004 (`0004_expande_tipo_acao`)

## 1. Objetivo

Registrar a validação técnica da Migration 0004 (expande o ENUM
`tipo_acao` com os 6 valores exigidos pela RN04/RN07 —
`entrada`, `venda`, `retirada_vencimento`, `ajuste`, `correcao`,
`importacao` — sem criar, alterar ou remover nenhuma tabela, coluna,
índice ou constraint), antes de qualquer execução no banco principal.

Pré-requisito técnico para a implementação futura do código de serviço
de estoque (RN07): sem esses 6 valores, nenhum registro de
`historico_acoes` pode ser gravado com `tipo_acao` igual a um deles.

## 2. Origem dos ambientes de teste

Como nenhum banco de teste existente estava em `alembic_version = 0003`
no início desta validação (todos permaneciam em `0001`/`0002`, deixados
assim pelas validações anteriores), uma origem `0003` dedicada e
reutilizável foi criada, sem tocar no banco principal `valida` nem em
nenhum banco de teste já existente:

1. `valida_m0004_origem_0003` criado via `CREATE DATABASE ... TEMPLATE`
   a partir de `valida_m0003_cycle1` (banco de teste ocioso, validado,
   em `0002`) — o template não é alterado por essa operação.
2. Upgrade `0002 → 0003` aplicado nessa cópia nova (migration já validada
   duas vezes nas Migrations 0002/0003 anteriores — nenhum risco novo).
3. `pg_dump` dessa cópia agora em `0003`, salvo como
   `valida_m0004_origem_0003_20260817_175606.dump` em
   `C:\Users\Silvana\Valida_Backups\` — snapshot `0003` reutilizável para
   os dois ciclos abaixo, sem depender de nenhum banco vivo.

## 3. Cycle1 — concluído (com correção de bug no processo)

- **Ambiente:** `valida_m0004_cycle1`, restaurado a partir do dump
  `valida_m0004_origem_0003_20260817_175606.dump` (estado `0003`, mesmo
  dataset representativo: 3 mercados, 4 produtos, 6 lotes, 8
  `historico_acoes`).
- **Upgrade (`0003 → 0004`):** executado com sucesso, com as
  verificações protegidas prévias (`current_database()`,
  `alembic_version`, `script_location`, SHA256 do arquivo de migration).
  Estrutura pós-upgrade conferida: ENUM `tipo_acao` com 19 valores (13
  originais + 6 novos, nesta ordem), nenhuma linha alterada.
- **Downgrade (`0004 → 0003`) — primeira tentativa falhou:** a consulta
  de proteção do `downgrade()` (`WHERE tipo_acao = ANY(:valores)`) falhou
  com `psycopg2.errors.UndefinedFunction: operador não existe: tipo_acao
  = text` — o `psycopg2` envia a lista Python como array `text[]`, e o
  Postgres não compara `tipo_acao = text` sem cast explícito. A
  transação foi revertida automaticamente pelo Alembic antes de qualquer
  `DDL` ser executado (confirmado por leitura: `alembic_version`
  permaneceu `0004`, e só existia 1 tipo `tipo_acao` no banco — nenhum
  `tipo_acao_old` órfão). Nenhum dano.
- **Correção aplicada:** `tipo_acao = ANY(:valores)` →
  `tipo_acao::text = ANY(:valores)` em
  `backend/alembic/versions/0004_expande_tipo_acao.py`. SHA256 do
  arquivo após a correção:
  `fb8faedf77cfd943696e1828a29dca6f3cbbd4f4f389fdae495e880fe617ae35`.
- **Downgrade (`0004 → 0003`) — reexecutado com sucesso** após a
  correção. Estrutura pós-downgrade conferida: ENUM `tipo_acao` revertido
  aos 13 valores originais, `tipo_acao_old` corretamente removido,
  contagens de linhas preservadas (3 mercados, 4 produtos, 6 lotes, 8
  `historico_acoes`).
- **Não interferência:** `valida_m0003_cycle1` (template original) e
  `valida` (banco principal) confirmados inalterados após todo o
  processo.

## 4. Cycle2 — concluído (repetibilidade)

- **Ambiente:** `valida_m0004_cycle2`, restaurado de forma independente
  do mesmo dump `valida_m0004_origem_0003_20260817_175606.dump` — banco
  descartável distinto de `valida_m0004_cycle1` (já mutado pelo teste
  anterior), evitando reaproveitar um banco de teste já usado.
- **Upgrade (`0003 → 0004`):** executado com sucesso, sem nenhum erro,
  com as mesmas verificações protegidas. Estrutura pós-upgrade idêntica
  ao cycle1 — ENUM com os mesmos 19 valores, mesma ordem, nenhuma linha
  alterada.
- **Downgrade (`0004 → 0003`):** executado com sucesso já com a correção
  aplicada — sem repetir o erro do cycle1. Estrutura pós-downgrade
  idêntica ao cycle1 — ENUM revertido aos 13 valores originais,
  `tipo_acao_old` removido, contagens de linhas preservadas.
- **Não interferência:** `valida_m0004_cycle1`, `valida_m0004_origem_0003`,
  `valida_m0003_cycle1` e `valida` confirmados inalterados após todo o
  processo.

## 5. Confirmação de repetibilidade

Confirmada. O cycle2, com origem independente do cycle1 (banco
descartável distinto, mesmo dump de origem), produziu resultado
estrutural idêntico — mesmos 19 valores pós-upgrade, mesmos 13 valores
pós-downgrade, mesmas contagens de linha preservadas — já com a correção
do bug de proteção aplicada e validada nos dois ciclos.

## 6. Bug encontrado e corrigido durante a validação

| Item | Detalhe |
|---|---|
| Sintoma | `psycopg2.errors.UndefinedFunction: operador não existe: tipo_acao = text` ao rodar o `downgrade()` |
| Causa | `sa.text("... WHERE tipo_acao = ANY(:valores)")` com `:valores` vinculado a uma lista Python — o driver envia como `text[]`, sem cast implícito para comparar com a coluna ENUM |
| Correção | `tipo_acao::text = ANY(:valores)` |
| Onde foi detectado | Cycle1, na primeira tentativa de downgrade — nenhum dano ao banco (transação revertida automaticamente antes de qualquer `DDL`) |
| Validação da correção | Reexecutado com sucesso no cycle1 (reexecução) e no cycle2 (primeira tentativa, sem erro) |

## 7. Status geral

Migration 0004 validada em dois ciclos completos e independentes (upgrade
+ downgrade reversível cada), com repetibilidade confirmada entre eles, e
com o único bug encontrado (na consulta de proteção do downgrade, não no
upgrade) corrigido e revalidado. **Tecnicamente apta para futura execução
no banco principal (`valida`)**, condicionada a:
- Execução isolada, como ação explicitamente autorizada em separado desta
  validação técnica (esta sessão não incluiu execução no banco
  principal).
- Um backup do banco `valida` imediatamente antes da execução, verificado
  (caminho, tamanho, SHA256, `pg_restore --list`), como praticado nas
  Migrations 0002 e 0003.
- Confirmação de `alembic_version = 0003` no banco principal antes de
  iniciar (já é o estado atual, conforme registrado em
  `docs/checkpoint-migration-0003.md`, seção 8).

---

## 8. Execução em produção (2026-08-18)

A Migration 0004 foi **executada no banco principal `valida`**, com
autorização explícita e separada, comando a comando, seguindo a mesma
disciplina usada na execução da Migration 0003.

- **Confirmação pré-execução:** `alembic_version` de produção lido ao vivo
  (via `psql`, fora de qualquer script de aplicação) = `0003`, confirmando
  o estado registrado na seção 7 e no checkpoint da Migration 0003.
- **Backup pré-migration:** `valida_pre_migration_0004_20260818_085642.dump`,
  em `C:\Users\Silvana\Valida_Backups\`. Verificado antes do upgrade —
  45.035 bytes, SHA256
  `1C8D157298B051FE737F69FA51EEB2428E2797AF376826F1F7380DDD8A5393CA`,
  `pg_restore --list` confirmando `dbname: valida`, 122 TOC entries,
  formato CUSTOM.
- **Bug de ambiente encontrado e corrigido (fora dos arquivos versionados
  do projeto):** a primeira tentativa de execução falhou com um
  `UnicodeDecodeError` (`'utf-8' codec can't decode byte 0xe7 ... invalid
  continuation byte`) dentro de `psycopg2.connect()`, chamado por
  `backend/alembic/env.py`. Causa raiz: `Settings.Config.env_file = ".env"`
  em `backend/app/core/config.py` é um caminho **relativo**, resolvido pelo
  `pydantic-settings` contra o diretório de trabalho (CWD) do processo, não
  contra a localização de `config.py`. O script auxiliar de execução rodou
  com CWD na raiz do projeto (onde não existe `.env`), então
  `settings.database_url` caiu no valor padrão hardcoded da classe
  (`postgresql+psycopg2://valida:valida@localhost:5432/valida` — credencial
  fictícia), e o PostgreSQL rejeitou essa autenticação com uma mensagem de
  erro em português (contendo `ç`, `0xe7` em Latin-1/CP1252) que o
  `psycopg2` não conseguiu decodificar como UTF-8 — mascarando o erro real
  de autenticação atrás de um `UnicodeDecodeError`. Uma tentativa
  intermediária de corrigir um suposto erro de interpolação do
  `ConfigParser` (escapar `%` como `%%` na URL) foi inofensiva mas
  irrelevante, já que `backend/alembic/env.py` sempre sobrescreve a URL
  usando `settings.database_url` diretamente. **Correção efetiva:** o
  script auxiliar de execução passou a fixar o CWD para `backend/` (via
  `os.chdir`) antes de chamar `command.upgrade`, garantindo que
  `Settings()` encontre o `.env` real. Nenhum arquivo versionado do
  projeto (`env.py`, `config.py`, a migration em si) foi alterado — a
  correção ficou inteira no script auxiliar de execução, fora do
  repositório.
- **Verificações protegidas pré-upgrade** (no script auxiliar, antes de
  qualquer DDL): nome do banco na própria `DATABASE_URL`, `current_database()
  = valida`, `alembic_version` atual `= 0003`, `script_location` resolvido
  para caminho absoluto existente, SHA256 do arquivo de migration
  `0004_expande_tipo_acao.py` = `fb8faedf77cfd943696e1828a29dca6f3cbbd4f4f389fdae495e880fe617ae35`
  (idêntico ao validado nos dois ciclos da seção 3–4).
- **Upgrade `0003 → 0004`:** executado com sucesso.
- **Verificação pós-upgrade:** `alembic_version = 0004`, confirmado por
  duas vias independentes — a saída do próprio `command.upgrade` e uma
  leitura separada via `psql` (`SELECT version_num FROM alembic_version`).

**Migration 0004 em produção desde 2026-08-18.**
