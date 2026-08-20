# Revisão final de prontidão — Migration 0003 para o banco principal

Documento **somente leitura/documentação**, consolidado a partir de
`docs/validacao-migration-0002.md` e `docs/checkpoint-migration-0003.md`.
Nenhum comando foi executado para produzir esta revisão: nenhuma conexão
ao banco principal (`valida`), nenhuma migration disparada, nenhuma
alteração em `.env`, código ou banco. **Esta revisão para antes de
qualquer execução** — é uma etapa de leitura/decisão, não de ação.

## 1. Estado atual validado

**Migration 0002 (`0002_campos_operacionais`):**
- Já **executada no banco principal `valida`**, com backup pré-migration
  validado e verificação pós-upgrade concluída (nota final de
  `docs/validacao-migration-0002.md`).
- `criar_pendente` e `editar_pendente` já preenchem/sincronizam
  `status_operacional`, `quantidade_disponivel` e `quantidade_inicial`.
  Venda, descarte e FEFO continuam sem implementação de código.

**Migration 0003 (`0003_movimentacoes_importacoes`):**
- **Não executada no banco principal.** Validada em dois ciclos completos
  e independentes, em ambientes isolados:
  - **Cycle1** — `valida_m0003_cycle1`, derivado de
    `valida_m0002_multi_cycle1` (`0002`).
  - **Cycle2** — `valida_m0003_cycle2`, derivado de forma independente do
    dump `valida_m0002_multi_cycle1_para_0003_20260814_151522.dump`
    (também `0002`, sem reutilizar nenhum banco de teste já mutado).
  - Upgrade (`0002 → 0003`) e downgrade (`0003 → 0002`) executados com
    sucesso e **estrutura idêntica** entre os dois ciclos — repetibilidade
    confirmada.
  - Nenhum banco de teste pré-existente foi alterado por engano em
    nenhuma etapa (`valida_m0002_multi_cycle1`, `valida_m0002_multi_cycle2`,
    `valida_m0003_cycle1` permaneceram nos respectivos estados originais).
- Conclusão registrada em `docs/checkpoint-migration-0003.md`:
  **tecnicamente apta para futura execução no banco principal**,
  condicionada às pré-condições da seção 4 abaixo. As duas condições
  residuais identificadas na classificação de riscos (regra de rollback
  e medição de volume) foram resolvidas em 2026-08-17 — ver seção 8,
  recomendação final: **APTO**.

## 2. O que foi testado

- **Estrutura pós-upgrade**, nos dois ciclos: as 3 tabelas novas
  (`importacoes`, `movimentacoes_estoque`, `itens_importacao`, incluindo
  `dados_brutos` como `jsonb`), as 3 colunas aditivas em
  `historico_acoes` (`quantidade_anterior`, `quantidade_movimentada`,
  `quantidade_resultante`), e `UNIQUE (id, id_mercado)` em `lotes` — tudo
  conferido campo a campo contra `docs/modelo-dados.md`, incluindo FKs
  compostas, `CHECK` constraints e índices (inclusive o índice único
  parcial de idempotência de `movimentacoes_estoque`).
- **Estrutura pós-downgrade**, nos dois ciclos: reversão exata ao estado
  `0002` de origem — tabelas novas removidas, colunas novas removidas,
  `UNIQUE` removida, tipos `ENUM` novos removidos, contagens de linhas
  das tabelas pré-existentes preservadas (3 mercados, 4 produtos, 6
  lotes, 8 `historico_acoes` em ambos os ciclos).
- **Verificações protegidas prévias**, antes de cada `upgrade`/`downgrade`
  em ambos os ciclos: nome do banco na URL de conexão, `current_database()`,
  `alembic_version` atual, `script_location`, e SHA256 do arquivo de
  migration (`e558a5277df477d1cce4cb3e495dcfb14ea655a7fbaa5db533e803c4812cc028`
  — idêntico nos dois ciclos, confirmando que o arquivo não foi alterado
  entre eles), cada checagem com `if` + `raise RuntimeError(...)`.
- **Repetibilidade**: os dois ciclos, com origens de dados independentes,
  produziram resultados estruturais e de contagem de linhas idênticos.
- **Não interferência**: em nenhum momento um banco de teste diferente do
  banco-alvo daquele ciclo foi conectado para escrita.

### O que **não** foi testado

- **Volume real de produção.** O dataset de teste é pequeno e
  representativo (3 mercados, 4 produtos, 6 lotes, 8 `historico_acoes`),
  não o volume real do banco `valida`. Tempo de execução da migration em
  escala de produção não foi medido.
- **Aplicação rodando durante a migration.** Não houve teste de
  concorrência com o backend FastAPI ativo gravando no banco enquanto a
  migration corre.
- **Consumo de dados pelas tabelas novas.** Uma busca no código-fonte
  (`backend/app/`) não encontrou nenhuma rota, serviço ou schema que leia
  ou escreva em `movimentacoes_estoque`, `importacoes`, `itens_importacao`
  ou nas 3 novas colunas de `historico_acoes` — as tabelas nascem e
  permanecem vazias nos testes porque não há, ainda, código de aplicação
  que grave nelas (RN07, seção "Ordem de implementação" de
  `docs/modelo-dados.md`, itens 5–6, ainda pendentes).
- **Downgrade com dados reais nas tabelas novas.** Como as tabelas novas
  nascem vazias e nenhum código grava nelas ainda, o downgrade testado é
  puramente estrutural — não valida o comportamento (perda de dados) de
  um downgrade após a tabela já conter movimentações reais.

## 3. Riscos residuais

1. **Tabelas/colunas ficarão inertes até a implementação do código de
   serviço.** Mesma situação já observada e aceita na Migration 0002
   (seção 10.3 de `docs/validacao-migration-0002.md`): a migration cria
   estrutura, não comportamento. `movimentacoes_estoque`, `importacoes`,
   `itens_importacao` e as 3 colunas novas de `historico_acoes` só terão
   uso quando o código de serviço de estoque (RN07) e o pipeline de
   importação forem implementados — fases futuras separadas.
2. **Downgrade se torna destrutivo assim que houver dados reais.** Se a
   migration for aplicada em produção e, posteriormente, código de
   serviço passar a gravar em `movimentacoes_estoque`/`importacoes`/
   `itens_importacao`, um eventual `downgrade` para `0002` **apagará**
   essas tabelas (e as linhas nelas) — comportamento correto e esperado
   de uma migration reversível, mas que deixa de ser "sem custo" a partir
   do momento em que há gravação real. Isso não foi exercitado nos testes
   porque as tabelas permaneceram vazias em todos os ciclos. **Regra
   formal de rollback definida na seção 5.**
3. **Volume/tempo de execução em produção desconhecido.** Sem teste em
   escala real, o tempo de bloqueio de `lotes` durante a criação da
   `UNIQUE (id, id_mercado)` (que exige verificação de unicidade sobre
   todas as linhas existentes) não foi medido em um volume comparável ao
   de produção. **Procedimento formal de medição definido na seção 6.**
4. **Divergência de vocabulário `historico_acoes.origem`**, já conhecida
   e documentada (`docs/modelo-dados.md`, seção `historico_acoes`): o
   código (`OrigemAcao`) usa `sistema`/`usuario`, enquanto o vocabulário
   documental aprovado é `conversa`/`foto`/`etiqueta`/`nota_fiscal`/
   `arquivo`/`automacao`. Não é alterado por esta migration, mas é uma
   pendência relacionada que segue em aberto.
5. **Expansão futura do ENUM `tipo_acao`** (`entrada`, `venda`,
   `retirada_vencimento`, `ajuste`, `correcao`, `importacao`) foi
   deliberadamente deixada fora do escopo da Migration 0003 — é uma
   migration futura e isolada, a aplicar somente quando o código de
   serviço estiver pronto para gravar esses valores. Não bloqueia a 0003,
   mas é uma dependência a lembrar antes de implementar RN07.
6. **Ordem de dependência de FK entre as tabelas novas** (`importacoes` →
   `movimentacoes_estoque` → `itens_importacao` → colunas de
   `historico_acoes`) é respeitada pela própria migration; nenhum risco
   adicional identificado aqui, citado apenas para registro.

## 4. Pré-condições para produção

Antes de qualquer execução real no banco principal (`valida`):

1. **Autorização explícita e separada** desta revisão documental — esta
   sessão não deve incluir execução no banco principal (conforme
   instrução recebida).
2. **Backup do banco `valida` imediatamente antes da execução**, salvo em
   local durável fora do projeto e do scratchpad
   (`C:\Users\Silvana\Valida_Backups\`), com verificação de caminho,
   tamanho, SHA256 e `pg_restore --list` — mesmo padrão já praticado na
   execução da Migration 0002.
3. **Confirmar `alembic_version` atual do banco principal = `0002`**
   antes de iniciar (checagem protegida, não apenas suposição).
4. **Confirmar SHA256 do arquivo de migration** contra o valor já
   verificado nos dois ciclos
   (`e558a5277df477d1cce4cb3e495dcfb14ea655a7fbaa5db533e803c4812cc028`),
   garantindo que o arquivo aplicado em produção é byte-a-byte o mesmo
   testado.
5. **Medição de volume de `lotes` concluída e janela de manutenção
   dimensionada com base nela** — **satisfeita em 2026-08-17**: `lotes`
   tem 1 linha / 64 kB no banco principal, faixa "até ~100 mil linhas"
   (seção 6), janela de manutenção curta já prevista é suficiente.
6. **Nenhuma execução automática/CI** — cada comando mostrado como texto
   e aprovado individualmente, conforme protocolo já estabelecido para
   este projeto.

## 5. Regra formal de rollback pós-produção (Migration 0003)

Regra vinculante, formalizada nesta revisão, para qualquer downgrade de
`0003` para `0002` que venha a ser cogitado **depois** que a Migration
0003 estiver em produção:

1. **Verificação de dados reais.** Antes de cogitar um downgrade,
   verificar se `importacoes`, `movimentacoes_estoque` ou
   `itens_importacao` contêm qualquer linha (`SELECT count(*) FROM ...`
   nas três tabelas). Se todas estiverem vazias, o downgrade segue como
   puramente estrutural (mesmo comportamento já validado nos cycles 1 e
   2). Se qualquer uma contiver dados, as regras 2 a 4 abaixo se aplicam
   obrigatoriamente.
2. **Backup dedicado obrigatório.** Nenhum downgrade `0003 → 0002` pode
   ser executado, com dados reais presentes em qualquer uma das três
   tabelas, sem antes tirar um backup dedicado dessas três tabelas (dump
   específico dessas tabelas, ou backup completo do banco principal),
   salvo em local durável fora do projeto e do scratchpad
   (`C:\Users\Silvana\Valida_Backups\`).
3. **Backup verificado antes do downgrade.** O backup do passo 2 deve ser
   verificado — caminho, tamanho, SHA256 e `pg_restore --list` — antes de
   qualquer comando de downgrade ser executado, seguindo o mesmo padrão
   já praticado para backups pré-migration.
4. **Downgrade permanece ação excepcional e explicitamente autorizada.**
   Mesmo com o backup verificado, o downgrade de `0003 → 0002` após
   dados reais existirem não é uma ação de rotina — deve ser tratado
   como exceção, exigindo autorização explícita e separada do usuário,
   com o comando exato mostrado como texto e aprovado individualmente
   antes da execução (mesmo protocolo já em vigor para qualquer comando
   que toque o banco).

Esta regra vale **além** e **independente** de qualquer downgrade
realizado durante a fase de validação em ambiente isolado
(cycle1/cycle2), que já ocorreu sobre tabelas vazias e não é afetado por
ela.

## 6. Regra formal de medição de volume antes do agendamento (Migration 0003)

Regra vinculante, formalizada nesta revisão, para mitigar o risco 3
(seção 3) antes de agendar a execução real da Migration 0003 no banco
principal. A medição em si **não foi realizada nesta revisão**
(instrução explícita: nenhuma conexão ao banco principal) — o que segue
é o procedimento e os critérios que devem ser aplicados em uma sessão
futura, dedicada e explicitamente autorizada para leitura no banco
principal.

1. **Medição obrigatória, somente leitura, antes do agendamento.**
   Antes de definir a janela de manutenção, executar no banco principal
   (comandos somente leitura, cada um mostrado como texto e aprovado
   individualmente, conforme protocolo já em vigor):
   ```sql
   SELECT count(*) FROM lotes;
   SELECT pg_size_pretty(pg_total_relation_size('lotes'));
   ```
   O segundo comando inclui o tamanho de todos os índices já existentes
   em `lotes`, não só das linhas.
2. **Critérios de decisão sobre a janela de manutenção**, com base no
   resultado da medição:
   - **Até ~100 mil linhas:** lock esperado da ordem de segundos;
     a janela de manutenção curta já prevista na seção 4 é suficiente,
     sem necessidade de ajuste adicional.
   - **Entre ~100 mil e poucos milhões de linhas:** lock pode chegar a
     dezenas de segundos ou poucos minutos; agendar em horário de
     tráfego mínimo e comunicar previamente a indisponibilidade breve de
     escrita em `lotes` durante a execução.
   - **Muitos milhões de linhas:** antes de aplicar a migration como
     está, avaliar tecnicamente (em revisão separada, sem alterar a
     migration nesta etapa) se a criação de `UNIQUE (id, id_mercado)`
     deve ser feita por outra estratégia (ex.: índice construído
     `CONCURRENTLY` fora da transação da migration) — o que exigiria
     reescrever esse trecho da migration e revalidar em cycle1/cycle2
     antes de aplicar em produção.
3. **Resultado da medição deve ser registrado por escrito** (nesta
   revisão ou em documento específico) antes da aplicação, junto com a
   faixa de volume identificada e a janela de manutenção decidida.
4. **Enquanto a medição não for realizada**, a pré-condição 5 da seção 4
   permanece formalmente definida (este procedimento) mas **não
   satisfeita na prática** — não é possível agendar a execução em
   produção só com base nesta formalização documental.

### Resultado da medição (2026-08-17)

Medição executada no banco principal `valida`, somente leitura, com os
dois `SELECT`s do item 1 acima:

| Métrica | Resultado |
|---|---|
| `SELECT count(*) FROM lotes;` | **1 linha** |
| `SELECT pg_size_pretty(pg_total_relation_size('lotes'));` | **64 kB** |

**Faixa de volume identificada:** até ~100 mil linhas (item 2, primeira
faixa) — volume atual do banco principal é trivial.

**Conclusão:** lock esperado durante a criação de
`UNIQUE (id, id_mercado)` é da ordem de milissegundos/segundos. A janela
de manutenção curta já prevista na seção 4 é suficiente, sem necessidade
de ajuste adicional. **Condição satisfeita na prática** — a pré-condição
5 da seção 4 está cumprida.

## 7. Plano protegido passo a passo para futura aplicação no principal

Este plano **não deve ser iniciado nesta sessão** — cada etapa abaixo,
quando autorizada, deve ser conduzida em uma sessão dedicada, com cada
comando mostrado como texto e aprovado individualmente antes da execução.

1. **Sessão dedicada**, explicitamente autorizada para execução real no
   banco principal (não leitura/documentação).
2. **Medição de volume de `lotes`** (leitura), seguindo o procedimento e
   os critérios de decisão da seção 6, para dimensionar a janela de
   manutenção antes de prosseguir. Pode ser feita nesta mesma sessão
   dedicada (etapa somente leitura) ou em sessão de leitura anterior.
3. **Backup timestampado** do banco `valida` para
   `C:\Users\Silvana\Valida_Backups\` (fora do projeto e do scratchpad).
4. **Verificação do backup**: caminho, tamanho, SHA256, e
   `pg_restore --list` para confirmar integridade e conteúdo antes de
   prosseguir.
5. **Verificações protegidas pré-upgrade no banco principal** (mesmo
   padrão dos scripts usados nos cycles, com `if` + `raise RuntimeError`,
   nunca `assert`): nome do banco na URL de conexão = `valida`,
   `current_database()` = `valida`, `alembic_version` atual = `0002`,
   `script_location` resolvido corretamente, SHA256 do arquivo de
   migration conferido contra o valor já validado.
6. **Mostrar o comando exato de upgrade** (`alembic upgrade 0002 → 0003`
   no banco principal) e aguardar aprovação explícita antes de executar.
7. **Executar o upgrade** somente após aprovação.
8. **Verificação pós-upgrade** no banco principal: mesma checklist
   estrutural usada nos dois ciclos (3 tabelas novas, 3 colunas novas em
   `historico_acoes`, `UNIQUE (id, id_mercado)` em `lotes`, FKs
   compostas, `CHECK`s, índices) — sem alterar nenhum dado existente.
9. **Registrar a execução** em um relatório final consolidado (análogo à
   "Atualização posterior à aprovação" de
   `docs/validacao-migration-0002.md`), incluindo data/hora, resultado da
   verificação pós-upgrade, e confirmação de que nenhuma linha existente
   foi alterada.
10. **Plano de rollback preparado antes da execução** (não apenas
    reativo): seguir a regra formal de rollback da seção 5 — verificar se
    há dados reais em `importacoes`, `movimentacoes_estoque` ou
    `itens_importacao`; se houver, backup dedicado verificado é
    obrigatório antes de qualquer `alembic downgrade 0003 → 0002`, e a
    ação permanece excepcional e explicitamente autorizada; caso o
    downgrade não seja suficiente ou seguro, restaurar o backup do passo
    3 (backup pré-migration).
11. **Somente após a aplicação bem-sucedida**, iniciar — como fase
    separada e futura, mediante nova confirmação explícita — a
    implementação do código de serviço de estoque (RN07) e do pipeline de
    importação, conforme a "Ordem de implementação" de
    `docs/modelo-dados.md` (itens 5–6).

## 8. Recomendação final

**APTO.**

As duas condições residuais identificadas na classificação de riscos
desta migration foram resolvidas:

- **Regra de rollback pós-produção** (risco 2, seção 3): formalizada como
  regra vinculante na seção 5 — backup dedicado obrigatório e verificado
  antes de qualquer downgrade após dados reais existirem, com o downgrade
  permanecendo ação excepcional e explicitamente autorizada.
- **Volume de `lotes` no banco principal** (risco 3, seção 3): medido em
  2026-08-17, somente leitura — 1 linha / 64 kB, muito abaixo do limiar
  de atenção. A janela de manutenção curta já prevista é suficiente.

Isso não elimina os demais itens da seção 3 (riscos residuais de baixa
severidade, aceitos por design — ex.: tabelas inertes até o código de
serviço existir) nem substitui o **checklist operacional da seção 4**
(autorização explícita e separada, backup imediatamente antes da
execução, checagem de `alembic_version`, checagem de SHA256, ausência de
CI automático) — esses itens continuam sendo passos a executar **no
momento real da aplicação em produção**, não algo a antecipar nesta
revisão. A recomendação **APTO** significa que não há nenhum risco
residual não mitigado bloqueando a decisão de agendar a execução; a
execução em si segue exigindo o plano protegido passo a passo da seção 7,
com autorização explícita e separada, comando a comando.

---

**Esta revisão para aqui.** Nenhuma conexão ao banco principal foi feita
além da medição de volume somente leitura registrada na seção 6 (com
aprovação explícita prévia), nenhuma migration foi executada, e nenhum
arquivo além desta revisão e do `docs/checkpoint-migration-0003.md` já
atualizado anteriormente foi alterado.
