# Revisão final de prontidão — Migration 0006 para o banco principal

Documento **somente leitura/documentação**, consolidado a partir de
`docs/checkpoint-migration-0006.md`. Nenhum comando foi executado para
produzir esta revisão: nenhuma conexão ao banco principal (`valida`),
nenhuma migration disparada, nenhuma alteração em `.env`, código ou
banco. **Esta revisão para antes de qualquer execução** — é uma etapa de
leitura/decisão, não de ação.

## 1. Estado atual validado

**Migrations 0001-0005:** já executadas no banco principal `valida`, que
está confirmado em `alembic_version = 0005` (lido ao vivo nesta mesma
sessão, durante os passos 9 e 15 da validação da Migration 0006).

**Migration 0006 (`0006_sessoes_whatsapp`):**
- **Não executada no banco principal.** Cria a tabela `sessoes_whatsapp`
  — fatia 2 do planejamento da integração com o WhatsApp para o piloto
  (fluxo guiado por menu, sem NLU/LLM nesta fase, decisão aprovada
  explicitamente pelo usuário). Guarda o estado de uma conversa em
  andamento; não tem, hoje, nenhum consumidor real no código (o
  webhook/cliente de envio ainda não foram implementados — fatias
  futuras e separadas).
- Validada em dois ciclos completos e independentes, em ambientes
  isolados:
  - **Cycle1** — `valida_m0006_cycle1`, derivado de
    `valida_m0006_origem_0005` (`0005`).
  - **Cycle2** — `valida_m0006_cycle2`, derivado de forma independente
    do mesmo template (banco descartável distinto do cycle1, já mutado
    pelo teste anterior).
  - Upgrade (`0005 → 0006`) e downgrade (`0006 → 0005`) executados com
    sucesso e **resultado estrutural idêntico** entre os dois ciclos
    (tabela, colunas, PK, 2 FKs e índice criados/removidos
    corretamente) — repetibilidade confirmada.
  - Nenhum banco de teste pré-existente foi alterado por engano em
    nenhuma etapa (`valida_m0006_origem_0005` e `valida` confirmados
    inalterados a cada verificação).
- Conclusão registrada em `docs/checkpoint-migration-0006.md`:
  **tecnicamente apta para futura execução no banco principal**,
  condicionada às pré-condições da seção 4 abaixo.

## 2. O que foi testado

- **Estrutura pós-upgrade**, nos dois ciclos: tabela `sessoes_whatsapp`
  com 6 colunas, PK `id_usuario`, FK `id_usuario → usuarios(id)` `ON
  DELETE CASCADE`, FK `id_mercado → mercados(id)`, índice
  `ix_sessoes_whatsapp_mercado`.
- **Estrutura pós-downgrade**, nos dois ciclos: tabela completamente
  removida — reversão exata ao estado `0005` de origem.
- **Verificações protegidas prévias**, antes de cada `upgrade`/`downgrade`
  em ambos os ciclos: nome do banco na URL de conexão, `current_database()`,
  `alembic_version` atual, `script_location`, e SHA256 do arquivo de
  migration (`0B3EFF1353810A47BEDA53B5D391D81E11E45B33E3543F018375E758224F4CC8`),
  cada checagem com `if` + `raise RuntimeError(...)`.
- **Repetibilidade**: os dois ciclos, com origens de dados independentes,
  produziram resultados idênticos.
- **Não interferência**: em nenhum momento um banco diferente do
  banco-alvo daquele ciclo foi conectado para escrita.

### O que **não** foi testado

- **Concorrência com a aplicação rodando.** Não há teste de concorrência
  com o backend FastAPI ativo — irrelevante aqui, já que não existe
  nenhum código de aplicação (model/service/router) que leia ou escreva
  em `sessoes_whatsapp` ainda. A tabela fica pronta para quando a fatia
  6/7 do plano de integração WhatsApp for implementada.
- **Comportamento sob volume real de dados.** Não se aplica: é uma
  tabela nova e vazia — não há duplicidade, volume ou dado legado para
  auditar (diferente da Migration 0005, que alterava uma tabela já
  populada). `CREATE TABLE`/`CREATE INDEX` sobre uma tabela inexistente
  é uma operação instantânea, independente do tamanho do banco.

## 3. Riscos residuais

1. **Nenhum risco de dado.** Diferente das Migrations 0003 e 0005, esta
   migration não depende do conteúdo de nenhuma tabela existente
   (nenhuma checagem de duplicidade ou de volume é necessária como
   pré-condição) e não popula nenhuma linha — nasce vazia.
2. **Downgrade nunca é destrutivo**, pela mesma razão: `downgrade()` só
   remove uma tabela vazia (ou, na pior hipótese futura, com dados de
   sessão de conversa em andamento — nunca dado de negócio permanente
   como um lote ou uma venda). Ainda assim, um eventual downgrade
   continua exigindo o protocolo padrão (comando exato mostrado,
   aprovação explícita e separada).
3. **Sem consumidor no código ainda.** Mesma categoria de risco já
   aceita nas Migrations 0002/0003: "estrutura pronta antes do
   comportamento". A tabela não tem efeito prático imediato até que o
   webhook seja implementado (fatia futura, não iniciada).
4. **Nomes de constraint gerados automaticamente pelo Postgres** (sem
   `name=` explícito nos `ForeignKey`, diferente do estilo da Migration
   0003). Não é um risco funcional — só uma observação de consistência
   de estilo entre migrations, sem impacto em upgrade/downgrade/produção.

## 4. Pré-condições para produção

Antes de qualquer execução real no banco principal (`valida`):

1. **Autorização explícita e separada** desta revisão documental — esta
   sessão não deve incluir execução no banco principal.
2. **Backup do banco `valida` imediatamente antes da execução**, salvo em
   local durável fora do projeto e do scratchpad
   (`C:\Users\Silvana\Valida_Backups\`), com verificação de caminho,
   tamanho, SHA256 e `pg_restore --list`.
3. **Confirmar `alembic_version` atual do banco principal = `0005`**
   antes de iniciar (checagem protegida, não apenas suposição — já
   confirmado ao vivo nesta sessão, mas deve ser reconfirmado no momento
   real da execução, que pode ser uma sessão futura).
4. **Confirmar SHA256 do arquivo de migration** contra o valor já
   verificado nos dois ciclos
   (`0B3EFF1353810A47BEDA53B5D391D81E11E45B33E3543F018375E758224F4CC8`).
5. **Nenhuma checagem de duplicidade nem medição de volume é necessária**
   — ver seção 3, item 1.
6. **Nenhuma execução automática/CI** — cada comando mostrado como texto
   e aprovado individualmente.

## 5. Regra de rollback pós-produção (Migration 0006)

Mais simples que a regra formal da Migration 0003, e da mesma categoria
da Migration 0005: `downgrade()` só remove uma tabela — sem nenhum
cenário de perda de dado de negócio, já que nada no código escreve
nela ainda. Ainda assim, um eventual downgrade continua sendo uma ação
de banco que exige o mesmo protocolo padrão já em vigor: comando exato
mostrado como texto, aprovação explícita e separada antes de executar.
Não é necessário backup dedicado adicional além do backup pré-upgrade
já exigido na seção 4.

## 6. Plano protegido passo a passo para futura aplicação no principal

Este plano **não deve ser iniciado nesta sessão** — cada etapa abaixo,
quando autorizada, deve ser conduzida com cada comando mostrado como
texto e aprovado individualmente antes da execução.

1. **Sessão dedicada**, explicitamente autorizada para execução real no
   banco principal.
2. **Backup timestampado** do banco `valida` para
   `C:\Users\Silvana\Valida_Backups\`.
3. **Verificação do backup**: caminho, tamanho, SHA256, e
   `pg_restore --list`.
4. **Verificações protegidas pré-upgrade no banco principal**: nome do
   banco na URL de conexão = `valida`, `current_database()` = `valida`,
   `alembic_version` atual = `0005`, `script_location` resolvido
   corretamente (com o diretório de trabalho em `backend/` — ver
   incidente 1 do checkpoint), SHA256 do arquivo de migration conferido.
5. **Mostrar o comando exato de upgrade** (`alembic upgrade 0005 → 0006`
   no banco principal) e aguardar aprovação explícita antes de executar.
6. **Executar o upgrade** somente após aprovação.
7. **Verificação pós-upgrade** no banco principal: `alembic_version =
   0006` e tabela `sessoes_whatsapp` presente com a estrutura esperada
   (colunas, PK, 2 FKs, índice) — sem alterar nenhum dado existente nas
   demais tabelas.
8. **Registrar a execução** em atualização de
   `docs/checkpoint-migration-0006.md` (mesmo formato usado para a
   seção 8 do checkpoint da Migration 0005), incluindo data/hora e
   confirmação de que nenhuma linha existente em outras tabelas foi
   alterada.

## 7. Recomendação final

**APTO**, condicionado ao checklist operacional da seção 4 (autorização
explícita e separada, backup imediatamente antes da execução, checagem
de `alembic_version`, checagem de SHA256) — esses itens continuam sendo
passos a executar **no momento real da aplicação em produção**, não algo
a antecipar nesta revisão. Esta é a migration de menor risco residual
desde a 0001: nenhuma dependência de dado existente, nenhuma
possibilidade de perda de dado no downgrade, e nenhum consumidor de
código ainda ativo. Nenhum risco residual não mitigado bloqueia a
decisão de agendar a execução; a execução em si segue exigindo o plano
protegido passo a passo da seção 6, comando a comando.

---

**Esta revisão para aqui.** Nenhuma conexão ao banco principal foi feita
para produzi-la, nenhuma migration foi executada, e nenhum arquivo além
desta revisão foi alterado.
