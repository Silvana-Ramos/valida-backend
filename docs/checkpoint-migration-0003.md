# Checkpoint de validação — Migration 0003 (`0003_movimentacoes_importacoes`)

## 1. Objetivo

Registrar o estado atual da validação técnica da Migration 0003 (cria
`importacoes`, `movimentacoes_estoque`, `itens_importacao`; adiciona 3
colunas aditivas em `historico_acoes`; adiciona `UNIQUE (id, id_mercado)`
em `lotes`), antes de qualquer execução no banco principal.

## 2. Cycle1 — concluído

- **Ambiente:** `valida_m0003_cycle1`, cópia isolada derivada de
  `valida_m0002_multi_cycle1` (em `0002`, com o mesmo dataset
  representativo já usado na validação da Migration 0002).
- **Upgrade (`0002 → 0003`):** executado com sucesso, com verificações
  protegidas prévias (`current_database()`, `alembic_version`,
  `settings.database_url`, `script_location`, SHA256 do arquivo de
  migration). Estrutura pós-upgrade conferida: as 3 tabelas novas
  criadas corretamente (incluindo `dados_brutos` como `jsonb`), as 3
  colunas novas em `historico_acoes`, e a `UNIQUE (id, id_mercado)` em
  `lotes` — tudo conforme `docs/modelo-dados.md`.
- **Downgrade (`0003 → 0002`):** executado com sucesso, com as mesmas
  verificações protegidas. Estrutura pós-downgrade conferida: as 3
  tabelas novas removidas, as 3 colunas novas removidas, a `UNIQUE`
  removida — banco revertido exatamente ao estado `0002` original,
  contagens de linhas preservadas.
- **`valida_m0002_multi_cycle1`** (origem): confirmado inalterado em
  todas as verificações, antes e depois do teste.

## 3. Cycle2 (repetibilidade) — concluído

Um segundo ciclo independente (upgrade + downgrade, em uma nova cópia
isolada) foi executado para confirmar repetibilidade, seguindo o mesmo
padrão usado para a Migration 0002 (`cycle1`/`cycle2`). Resultado
detalhado na seção 5.

## 4. Plano do cycle2 (definido, não executado)

- **Origem definida (revisada 2×):** inicialmente planejado usar
  `valida_m0002_multi_cycle2` como banco "0002 limpo", mas a verificação
  em execução revelou que esse banco está em `alembic_version = 0001`,
  não `0002` — conforme `docs/validacao-migration-0002.md` (seção 6), seu
  estado final documentado é justamente o resultado do downgrade
  `0002 → 0001` do cycle2 daquela migration, não um estado `0002`. A
  alternativa cogitada em seguida (`valida_m0002_representativo.dump`)
  também não existe com esse nome em `C:\Users\Silvana\Valida_Backups\` —
  os únicos dumps presentes lá são `valida_pre_migration_0002_*.dump`
  (backup do banco principal antes da 0002 em produção, não é o dataset
  de teste) e `valida_m0002_multi_cycle1_para_0003_20260814_151522.dump`.
  **Origem final:** restaurar
  `valida_m0002_multi_cycle1_para_0003_20260814_151522.dump` — dump de
  `valida_m0002_multi_cycle1` em estado `0002`, tirado especificamente
  para alimentar o teste da Migration 0003 (mesma origem usada para criar
  `valida_m0003_cycle1`) — em um banco novo dedicado
  `valida_m0003_cycle2`, sem tocar em nenhum banco de teste já existente.

Passos planejados:

1. Criar `valida_m0003_cycle2` restaurando
   `valida_m0002_multi_cycle1_para_0003_20260814_151522.dump`
   (`pg_restore` em banco novo, criado vazio via `createdb`).
2. Verificações protegidas pré-upgrade em `valida_m0003_cycle2`:
   `settings.database_url`, `current_database()`, `alembic_version`
   (esperado `0002`), `script_location`, SHA256 do arquivo de migration
   `0003`.
3. Upgrade `0002 → 0003` e conferência da estrutura pós-upgrade (3
   tabelas novas incl. `dados_brutos` como `jsonb`, 3 colunas novas em
   `historico_acoes`, `UNIQUE (id, id_mercado)` em `lotes`) — comparada
   linha a linha com o resultado do cycle1.
4. Verificações protegidas pré-downgrade, agora com `alembic_version`
   esperado `0003`.
5. Downgrade `0003 → 0002` e conferência de que a estrutura volta
   exatamente ao estado `0002` de origem, com contagens de linhas
   preservadas.
6. Verificação de não interferência: confirmar que nenhum banco de teste
   já existente (`valida_m0002_multi_cycle1`, `valida_m0002_multi_cycle2`,
   `valida_m0003_cycle1`) foi tocado durante o processo — a origem agora
   é um arquivo de dump, não um banco vivo.
7. Comparação cycle1 × cycle2: confrontar resultados estruturais e de
   dados para declarar repetibilidade confirmada (ou não).
8. Atualização da documentação: se tudo confirmar, atualizar este
   checkpoint e/ou consolidar em `docs/validacao-migration-0003.md`, no
   mesmo formato usado para a 0002.

**Este plano foi executado integralmente nesta sessão**, passo a passo,
com aprovação individual de cada comando que tocou o banco (protocolo já
estabelecido para o projeto). Resultado na seção 5.

## 5. Resultado do cycle2 (`valida_m0003_cycle2`)

- **Ambiente:** `valida_m0003_cycle2`, criado via `pg_restore` do dump
  `valida_m0002_multi_cycle1_para_0003_20260814_151522.dump` (estado
  `0002`, mesmo dataset representativo do cycle1: 3 mercados, 4 produtos,
  6 lotes, 8 registros de `historico_acoes`). Nenhum banco de teste já
  existente foi usado como origem — apenas o arquivo de dump.
- **Upgrade (`0002 → 0003`):** executado com sucesso via script Python
  dedicado (fora do projeto, em diretório de scratch), com as 5
  verificações protegidas prévias (nome do banco na URL de conexão,
  `current_database()`, `alembic_version` atual, `script_location`
  resolvido para caminho absoluto, SHA256 do arquivo de migration —
  `e558a5277df477d1cce4cb3e495dcfb14ea655a7fbaa5db533e803c4812cc028`),
  cada verificação com `if` + `raise RuntimeError(...)`. Estrutura
  pós-upgrade conferida e idêntica ao cycle1: as 3 tabelas novas
  corretas (incluindo `dados_brutos` como `jsonb`), as 3 colunas novas
  em `historico_acoes`, `uq_lotes_id_mercado` em `lotes`, todas as FKs
  compostas e `CHECK` constraints presentes.
- **Downgrade (`0003 → 0002`):** executado com sucesso, com as mesmas
  verificações protegidas. Estrutura pós-downgrade conferida e idêntica
  ao cycle1: as 3 tabelas novas removidas, as 3 colunas novas removidas,
  `uq_lotes_id_mercado` removida — banco revertido exatamente ao estado
  `0002` de origem. Contagens de linhas preservadas (3 mercados, 4
  produtos, 6 lotes, 8 `historico_acoes`), idênticas às de antes do
  upgrade.
- **Não interferência confirmada:** `valida_m0002_multi_cycle1`
  permanece em `0002`, `valida_m0002_multi_cycle2` permanece em `0001`,
  e `valida_m0003_cycle1` permanece em `0002` — nenhum desses bancos foi
  tocado durante o processo do cycle2.

### Nota de correção do script auxiliar

Na primeira tentativa de upgrade, o script auxiliar falhou
(`CommandError: Path doesn't exist: alembic`) porque `script_location =
alembic` no `alembic.ini` é relativo e o Alembic o resolve em relação ao
diretório de trabalho do processo, não ao diretório do `.ini`. Nenhuma
alteração havia sido feita no banco até esse ponto (a falha ocorreu antes
da chamada real da migration). Corrigido fixando `script_location` como
caminho absoluto (já validado pela checagem) antes de `command.upgrade`;
o comando foi reapresentado para aprovação e reexecutado com sucesso.

## 6. Confirmação de repetibilidade

Confirmada. O upgrade e o downgrade do cycle2 produziram resultados
estruturais e de contagem de linhas idênticos aos do cycle1 (seção 2),
usando uma origem independente (dump `0002` restaurado em banco novo, não
um banco de teste já mutado por sessões anteriores).

## 7. Status geral

Migration 0003 validada em dois ciclos completos e independentes (upgrade
+ downgrade reversível cada), com repetibilidade confirmada entre eles.
**Tecnicamente apta para futura execução no banco principal (`valida`)**,
condicionada a:
- Execução isolada, como ação explicitamente autorizada em separado desta
  validação técnica (esta sessão não incluiu execução no banco
  principal).
- Um backup do banco `valida` imediatamente antes da execução, verificado
  (caminho, tamanho, SHA256, `pg_restore --list`), como praticado na
  execução da Migration 0002.

---

## 8. Execução em produção (2026-08-17)

A Migration 0003 foi **executada no banco principal `valida`**, com
autorização explícita e separada, comando a comando, seguindo o plano
protegido de `docs/revisao-prontidao-migration-0003.md` (seção 7):

- **Backup pré-migration:** `valida_pre_migration_0003_20260817_160650.dump`,
  em `C:\Users\Silvana\Valida_Backups\`. Verificado antes do upgrade —
  24107 bytes, SHA256
  `1D44047F27FBB18285C33CD4C54AFA1A124CCF9F80F18BCF3DCB39A3D0339E93`,
  `pg_restore --list` confirmando `dbname: valida`, 72 TOC entries,
  formato CUSTOM.
- **Verificações protegidas pré-upgrade:** `current_database()` = `valida`,
  `alembic_version` atual = `0002` (confirmado por leitura antes do
  upgrade), `script_location` resolvido corretamente, SHA256 do arquivo
  de migration = `e558a5277df477d1cce4cb3e495dcfb14ea655a7fbaa5db533e803c4812cc028`
  (idêntico ao validado nos cycles 1 e 2 — mesmo arquivo, byte a byte).
- **Upgrade `0002 → 0003`:** executado com sucesso.
- **Verificação pós-upgrade:** `alembic_version` = `0003`; as 3 tabelas
  novas (`importacoes`, `movimentacoes_estoque`, `itens_importacao`,
  incluindo `dados_brutos` como `jsonb`) criadas com todas as FKs
  compostas, `CHECK` constraints e índices corretos; as 3 colunas novas
  em `historico_acoes`; `uq_lotes_id_mercado` em `lotes` — estrutura
  idêntica à validada nos cycles 1 e 2. Contagens de linhas pré-existentes
  preservadas (1 mercado, 1 produto, 1 lote, 3 `historico_acoes`, 0
  usuários) — nenhum dado alterado pela migration.
- **Medição de volume prévia** (seção 6 de
  `docs/revisao-prontidao-migration-0003.md`): `lotes` com 1 linha / 64 kB
  no momento da execução — volume trivial, sem impacto de lock relevante.

**Migration 0003 em produção desde 2026-08-17.** Nenhum consumidor de
código ainda escreve nas tabelas novas (RN07 e o pipeline de importação
seguem como fases futuras separadas, conforme "Ordem de implementação" em
`docs/modelo-dados.md`) — a regra formal de rollback da seção 5 de
`docs/revisao-prontidao-migration-0003.md` passa a valer a partir de
agora para qualquer downgrade futuro.
