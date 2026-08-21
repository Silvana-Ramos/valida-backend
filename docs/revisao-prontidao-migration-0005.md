# Revisão final de prontidão — Migration 0005 para o banco principal

Documento **somente leitura/documentação**, consolidado a partir de
`docs/checkpoint-migration-0005.md`. Nenhum comando foi executado para
produzir esta revisão: nenhuma conexão ao banco principal (`valida`),
nenhuma migration disparada, nenhuma alteração em `.env`, código ou
banco. **Esta revisão para antes de qualquer execução** — é uma etapa de
leitura/decisão, não de ação.

## 1. Estado atual validado

**Migrations 0001-0004:** já executadas no banco principal `valida`, que
está confirmado em `alembic_version = 0004` (lido ao vivo durante a
validação desta migration).

**Migration 0005 (`0005_unique_telefone_usuarios`):**
- **Não executada no banco principal.** Adiciona `UNIQUE` em
  `usuarios.telefone_whatsapp` — pré-requisito para a autenticação real
  via webhook do WhatsApp (mapear um número verificado para exatamente um
  usuário/mercado).
- Validada em dois ciclos completos e independentes, em ambientes
  isolados:
  - **Cycle1** — `valida_m0005_cycle1`, derivado de
    `valida_m0005_origem_0004` (`0004`).
  - **Cycle2** — `valida_m0005_cycle2`, derivado de forma independente do
    mesmo template (banco descartável distinto do cycle1, já mutado pelo
    teste anterior).
  - Upgrade (`0004 → 0005`) e downgrade (`0005 → 0004`) executados com
    sucesso e **resultado estrutural idêntico** entre os dois ciclos
    (constraint `uq_usuarios_telefone_whatsapp` criada/removida
    corretamente) — repetibilidade confirmada.
  - Nenhum banco de teste pré-existente foi alterado por engano em
    nenhuma etapa (`valida_m0005_origem_0004`, `valida_m0005_cycle1` e
    `valida` confirmados inalterados a cada verificação).
- Conclusão registrada em `docs/checkpoint-migration-0005.md`:
  **tecnicamente apta para futura execução no banco principal**,
  condicionada às pré-condições da seção 4 abaixo.

## 2. O que foi testado

- **Estrutura pós-upgrade**, nos dois ciclos: constraint
  `uq_usuarios_telefone_whatsapp` presente em `pg_constraint` com
  `contype = 'u'` (UNIQUE), sobre `usuarios.telefone_whatsapp`.
- **Estrutura pós-downgrade**, nos dois ciclos: constraint removida —
  reversão exata ao estado `0004` de origem.
- **Verificações protegidas prévias**, antes de cada `upgrade`/`downgrade`
  em ambos os ciclos: nome do banco na URL de conexão, `current_database()`,
  `alembic_version` atual, `script_location`, e SHA256 do arquivo de
  migration (`88651f1f80b7d9c3c9cf5a0a9248796871d59b10a689d12db819cacec9b3af89`),
  cada checagem com `if` + `raise RuntimeError(...)`.
- **Repetibilidade**: os dois ciclos, com origens de dados independentes,
  produziram resultados idênticos.
- **Não interferência**: em nenhum momento um banco diferente do
  banco-alvo daquele ciclo foi conectado para escrita.

### O que **não** foi testado

- **Duplicidade real em `usuarios.telefone_whatsapp` no banco principal.**
  Os dados de teste (dataset representativo, pequeno) não têm duplicidade
  por construção. Não há como saber se o banco principal tem alguma
  duplicidade real sem consultá-lo diretamente — **checagem obrigatória
  antes da execução, seção 4**.
- **Volume real de `usuarios` em produção e tempo de execução em escala.**
  Não medido nesta revisão (instrução explícita: nenhuma conexão ao banco
  principal). Ver seção 6 para o procedimento formal a aplicar antes do
  agendamento.
- **Aplicação rodando durante a migration.** Não houve teste de
  concorrência com o backend FastAPI ativo gravando em `usuarios`
  enquanto a migration corre — hoje isso é um risco baixo, já que não
  existe nenhum endpoint de escrita em `usuarios` no código (`routers/`
  não tem `mercados.py` nem `usuarios.py` — ver revisão geral de
  prontidão do piloto).

## 3. Riscos residuais

1. **Se já existir duplicidade real, o upgrade falha (de forma limpa) na
   hora da execução, não antes.** O `ALTER TABLE ADD CONSTRAINT` do
   Postgres rejeita a operação sem alterar nada — mas isso só se confirma
   rodando de fato, gastando parte da janela de manutenção à toa se não
   for checado antes. **Checagem prévia formalizada como pré-condição
   obrigatória (seção 4, item 6).**
2. **Volume/tempo de execução em produção desconhecido** — mesma
   categoria de risco já tratada na Migration 0003 (lá para `lotes`, aqui
   para `usuarios`). **Procedimento formal de medição definido na seção
   6**, com uma observação relevante: o checkpoint da Migration 0003
   (seção 8) registrou `usuarios` com **0 linhas** em produção em
   2026-08-17 — se isso continuar valendo, o risco é praticamente nulo,
   mas precisa ser **reconfirmado ao vivo** no momento da execução, não
   presumido a partir de um registro antigo.
3. **Downgrade nunca é destrutivo nesta migration** — diferente da
   Migration 0003, que tinha uma regra formal de rollback por criar
   tabelas que passariam a ter dados reais. Aqui, `downgrade()` só remove
   a constraint; não há cenário em que isso cause perda de dado,
   independente de quanto tempo a Migration 0005 estiver em produção ou
   quantos usuários existam. Não é necessária uma "regra formal de
   rollback" no mesmo formato da Migration 0003 — só o protocolo padrão
   (autorização explícita e separada para qualquer comando que toque o
   banco, incluindo um downgrade).
4. **Sem CRUD de `usuarios`/`mercados` no código ainda** — mesmo depois
   desta migration, nada no backend hoje escreve em `usuarios`. A
   constraint fica pronta para quando o webhook/autenticação real for
   implementado, mas não tem efeito prático imediato (mesma categoria de
   "estrutura pronta antes do comportamento" já aceita nas Migrations
   0002/0003).

## 4. Pré-condições para produção

Antes de qualquer execução real no banco principal (`valida`):

1. **Autorização explícita e separada** desta revisão documental — esta
   sessão não deve incluir execução no banco principal.
2. **Backup do banco `valida` imediatamente antes da execução**, salvo em
   local durável fora do projeto e do scratchpad
   (`C:\Users\Silvana\Valida_Backups\`), com verificação de caminho,
   tamanho, SHA256 e `pg_restore --list`.
3. **Confirmar `alembic_version` atual do banco principal = `0004`**
   antes de iniciar (checagem protegida, não apenas suposição — já
   confirmado ao vivo nesta sessão, mas deve ser reconfirmado no momento
   real da execução, que pode ser uma sessão futura).
4. **Confirmar SHA256 do arquivo de migration** contra o valor já
   verificado nos dois ciclos
   (`88651f1f80b7d9c3c9cf5a0a9248796871d59b10a689d12db819cacec9b3af89`).
5. **Medição de volume de `usuarios` concluída** — seção 6, para
   dimensionar (ou descartar a necessidade de) uma janela de manutenção.
6. **Checagem de duplicidade em `usuarios.telefone_whatsapp` concluída**
   (leitura, nova exigência específica desta migration):
   ```sql
   SELECT telefone_whatsapp, count(*)
   FROM usuarios
   GROUP BY telefone_whatsapp
   HAVING count(*) > 1;
   ```
   Se retornar alguma linha, a execução **não deve prosseguir** até as
   duplicidades serem resolvidas manualmente (decisão de negócio sobre
   qual registro é o correto — fora do escopo de uma migration).
7. **Nenhuma execução automática/CI** — cada comando mostrado como texto
   e aprovado individualmente.

## 5. Regra de rollback pós-produção (Migration 0005)

Mais simples que a regra formal da Migration 0003, porque esta migration
nunca é destrutiva: `downgrade()` só remove uma constraint `UNIQUE`, sem
apagar nenhuma linha, independente de quantos dados existirem em
`usuarios` no momento. Ainda assim, um eventual downgrade continua sendo
uma ação de banco que exige o mesmo protocolo padrão já em vigor: comando
exato mostrado como texto, aprovação explícita e separada antes de
executar. Não é necessário backup dedicado adicional além do backup
pré-upgrade já exigido na seção 4 (que já cobre qualquer necessidade de
reversão completa, se algum dia for preciso).

## 6. Procedimento de medição de volume antes do agendamento (Migration 0005)

Regra vinculante, análoga à da Migration 0003 (lá para `lotes`, aqui para
`usuarios`), aplicada em conjunto com a checagem de duplicidade da seção
4.

1. **Medição obrigatória, somente leitura, antes do agendamento:**
   ```sql
   SELECT count(*) FROM usuarios;
   SELECT pg_size_pretty(pg_total_relation_size('usuarios'));
   ```
2. **Critérios de decisão sobre a janela de manutenção**, com base no
   resultado:
   - **0 ou poucas linhas** (cenário esperado, conforme o registro de
     `docs/checkpoint-migration-0003.md`, seção 8): lock instantâneo,
     nenhuma janela de manutenção especial necessária além do cuidado
     padrão já usado nas execuções anteriores.
   - **Até ~100 mil linhas:** lock esperado da ordem de segundos; janela
     de manutenção curta é suficiente.
   - **Volume maior:** reavaliar estratégia (ex.: índice `CONCURRENTLY`
     fora da transação da migration) antes de aplicar como está —
     exigiria revalidar em cycle1/cycle2.
3. **Resultado da medição deve ser registrado por escrito** (nesta
   revisão ou em atualização dela) antes da aplicação.

### Resultado da medição e da checagem de duplicidade (2026-08-20)

Executadas no banco principal `valida`, somente leitura, dentro da sessão
dedicada de execução da Migration 0005:

| Verificação | Resultado |
|---|---|
| Duplicidade em `usuarios.telefone_whatsapp` (seção 4, item 6) | **0 linhas** — nenhuma duplicidade |
| `SELECT count(*) FROM usuarios;` | **0 linhas** |
| `SELECT pg_size_pretty(pg_total_relation_size('usuarios'));` | **16 kB** (só overhead de tabela vazia) |

**Conclusão:** confirma ao vivo o que o checkpoint da Migration 0003
(seção 8) já registrava — `usuarios` segue vazia em produção. Lock da
criação da `UNIQUE` será instantâneo; nenhuma janela de manutenção
especial é necessária. **Pré-condições 5 e 6 da seção 4 satisfeitas.**

## 7. Plano protegido passo a passo para futura aplicação no principal

Este plano **não deve ser iniciado nesta sessão** — cada etapa abaixo,
quando autorizada, deve ser conduzida com cada comando mostrado como
texto e aprovado individualmente antes da execução.

1. **Sessão dedicada**, explicitamente autorizada para execução real no
   banco principal.
2. **Checagem de duplicidade em `usuarios.telefone_whatsapp`** (leitura,
   seção 4, item 6). Se houver duplicidade, parar e resolver antes de
   prosseguir.
3. **Medição de volume de `usuarios`** (leitura, seção 6).
4. **Backup timestampado** do banco `valida` para
   `C:\Users\Silvana\Valida_Backups\`.
5. **Verificação do backup**: caminho, tamanho, SHA256, e
   `pg_restore --list`.
6. **Verificações protegidas pré-upgrade no banco principal**: nome do
   banco na URL de conexão = `valida`, `current_database()` = `valida`,
   `alembic_version` atual = `0004`, `script_location` resolvido
   corretamente, SHA256 do arquivo de migration conferido.
7. **Mostrar o comando exato de upgrade** (`alembic upgrade 0004 → 0005`
   no banco principal) e aguardar aprovação explícita antes de executar.
8. **Executar o upgrade** somente após aprovação.
9. **Verificação pós-upgrade** no banco principal: `alembic_version =
   0005` e constraint `uq_usuarios_telefone_whatsapp` presente em
   `pg_constraint` com `contype = 'u'` — sem alterar nenhum dado
   existente.
10. **Registrar a execução** em atualização de
    `docs/checkpoint-migration-0005.md` (mesmo formato usado para a
    seção 8 do checkpoint da Migration 0003/0004), incluindo data/hora e
    confirmação de que nenhuma linha existente foi alterada.

## 8. Recomendação final

**APTO**, condicionado ao checklist operacional da seção 4 (autorização
explícita e separada, backup imediatamente antes da execução, checagem
de `alembic_version`, checagem de SHA256, medição de volume, **e a
checagem de duplicidade específica desta migration**) — esses itens
continuam sendo passos a executar **no momento real da aplicação em
produção**, não algo a antecipar nesta revisão. Nenhum risco residual não
mitigado bloqueia a decisão de agendar a execução; a execução em si segue
exigindo o plano protegido passo a passo da seção 7, comando a comando.

---

**Esta revisão para aqui.** Nenhuma conexão ao banco principal foi feita
para produzi-la, nenhuma migration foi executada, e nenhum arquivo além
desta revisão foi alterado.
