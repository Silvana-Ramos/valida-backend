# Relatório Final de Validação — Migration 0002 (`0002_campos_operacionais`)

## 1. Objetivo da migration

Adicionar campos operacionais opcionais às tabelas `mercados`, `produtos` e `lotes`, sem alterar ou remover nenhum campo existente e sem criar novos tipos ENUM, preparando o schema para funcionalidades futuras (relatório diário automático, limites de atenção por mercado, rastreabilidade de origem de produto/código de barras, e controle operacional de disponibilidade de estoque por lote). A migration inclui também o backfill dos novos campos para os registros já existentes, de forma compatível com 0, 1 ou múltiplos mercados/produtos/lotes.

Campos adicionados:
- `mercados`: `timezone`, `horario_abertura`, `horario_relatorio_diario`, `relatorio_diario_ativo` (NOT NULL, default `false`), `limite_valor_atencao`, `limite_quantidade_atencao`.
- `produtos`: `status`, `codigo_sistema_origem`, `codigo_barras`.
- `lotes`: `status_operacional`, `quantidade_disponivel`, `quantidade_inicial`.
- 4 índices não únicos de suporte (`ix_lotes_produto_data_validade`, `ix_lotes_produto_status_operacional`, `ix_produtos_mercado_codigo_origem`, `ix_produtos_mercado_codigo_barras`).

`mercados.status` (criado na 0001) não é tocado por esta migration.

## 2. Alteração realizada no backfill de `status_operacional` e `quantidade_disponivel`

Na versão inicialmente testada da Migration 0002, o backfill dos lotes preenchia genericamente os registros existentes com `status_operacional = 'disponivel'` e `quantidade_disponivel = quantidade`.
Esse comportamento produzia resultado semanticamente incorreto para lotes cujo `status` já era `vendido` ou `descartado`, pois esses lotes não deveriam permanecer operacionalmente disponíveis nem manter quantidade disponível positiva.

A correção aprovada substituiu esse backfill genérico por uma instrução SQL set-based com `CASE status`, aplicada linha a linha:

- `confirmado` → `status_operacional = disponivel` e `quantidade_disponivel = quantidade`
- `pendente_confirmacao` → `status_operacional = disponivel` e `quantidade_disponivel = quantidade`
- `vendido` → `status_operacional = esgotado` e `quantidade_disponivel = 0`
- `descartado` → `status_operacional = descartado` e `quantidade_disponivel = 0`

`quantidade_inicial` permanece `NULL` para lotes históricos.

## 3. Regra final aprovada de mapeamento por status

| `status` (lote) | `status_operacional` | `quantidade_disponivel` |
|---|---|---|
| `confirmado` | `disponivel` | = `quantidade` |
| `pendente_confirmacao` | `disponivel` | = `quantidade` |
| `vendido` | `esgotado` | `0` |
| `descartado` | `descartado` | `0` |

- `quantidade_inicial`: permanece `NULL` para todos os lotes históricos já existentes; será preenchido apenas no cadastro de lotes futuros (fora do escopo desta migration).
- `produtos.status`: recebe `'ativo'` somente onde já não houvesse valor (`WHERE status IS NULL`).
- `mercados.relatorio_diario_ativo`: garantido como `false` onde estiver nulo.
- `mercados.status` (0001): não alterado por esta migration.

## 4. Resultado do cycle1 (`valida_m0002_multi_cycle1`)

- **Baseline 0001 validada**: banco restaurado a partir do backup representativo (`valida_m0002_representativo.dump`): 3 mercados, 4 produtos (incluindo 1 sem lote), 6 lotes com quantidades distintas e status variados, 8 registros de `historico_acoes`. Estrutura e `alembic_version = 0001` confirmados antes de qualquer alteração.
- **Upgrade inicial da 0002**: aplicado com verificações de segurança prévias (`settings.database_url`, `current_database()`, `alembic_version`, `script_location`), utilizando a versão então vigente do backfill (genérica).
- **Identificação do problema semântico no backfill**: a inspeção pós-upgrade revelou que lotes com `status = vendido` ou `status = descartado` haviam recebido `status_operacional = disponivel` e `quantidade_disponivel = quantidade`, resultado semanticamente incorreto (ver seção 2).
- **Correção da migration**: o backfill foi reescrito para a instrução SQL set-based com `CASE status`, implementando a regra aprovada na seção 3.
- **Downgrade controlado para 0001**: executado com as mesmas verificações de segurança prévias, restaurando a estrutura original antes da reaplicação.
- **Reaplicação da 0002 corrigida**: upgrade reexecutado, já com a versão corrigida do backfill, com as mesmas verificações de segurança prévias.
- **Validação completa do upgrade corrigido**: estrutura e dados conferidos linha a linha; cada lote recebeu `status_operacional`/`quantidade_disponivel` corretos conforme sua própria regra de status individual, sem exceções.

## 5. Resultado do cycle2 (`valida_m0002_multi_cycle2`)

- Segundo banco independente, restaurado a partir do mesmo backup representativo — baseline 0001 previamente validada e preservada sem alterações — utilizado para repetir de forma independente o teste completo, já com a versão corrigida da migration.
- Upgrade `0001 → 0002` executado com as mesmas verificações de segurança prévias (`settings.database_url`, `current_database()`, `alembic_version`, `script_location`).
- Estrutura e backfill conferidos, com o mesmo resultado do upgrade corrigido do cycle1 (mesma regra de mapeamento aplicada corretamente por linha).
- Downgrade `0002 → 0001` executado com as mesmas verificações de segurança prévias.

## 6. Resultado do downgrade (verificação final pós-downgrade, cycle2)

Verificação de leitura, comparando `valida_m0002_multi_cycle2` pós-downgrade contra a baseline 0001 previamente validada e preservada sem alterações (`valida_m0002_multi_clean_0001`):
- `current_database()` = `valida_m0002_multi_cycle2` ✓
- `alembic_version` = `0001` ✓
- `\d lotes`: 14 colunas originais, sem os 3 campos da 0002; apenas `lotes_pkey`; 3 FKs originais intactas ✓
- `\d produtos`: 6 colunas originais, sem os 3 campos da 0002; apenas `produtos_pkey`; FK original intacta ✓
- `\d mercados`: 6 colunas originais, sem os 6 campos da 0002; `mercados_pkey` + UNIQUE `telefone_whatsapp` originais; 4 referências de FK preservadas ✓
- Os 4 índices criados pela 0002 não existem mais ✓

## 7. Contagens finais

| Tabela | Contagem |
|---|---|
| mercados | 3 |
| usuarios | 0 |
| produtos | 4 |
| lotes | 6 |
| historico_acoes | 8 |
| faixas_risco | 5 |

Valores idênticos aos esperados e aos existentes antes do upgrade, confirmando que nenhuma linha foi perdida ou duplicada em todo o ciclo upgrade→downgrade.

## 8. Confirmação de repetibilidade

Confirmada. Os upgrades corrigidos aplicados no cycle1 (reaplicação pós-correção) e no cycle2 produziram resultados estruturais e de backfill idênticos entre si.

## 9. Confirmação de reversibilidade

O teste final completo de reversibilidade da versão corrigida foi encerrado no cycle2, com verificação detalhada pós-downgrade (seção 6) confirmando reversão estrutural total e preservação das contagens de linhas. No cycle1, o downgrade já havia sido validado estruturalmente durante a etapa de correção (downgrade controlado para 0001, antes da reaplicação da versão corrigida); a lógica de `downgrade()` em si não foi alterada pela correção do backfill, permanecendo a mesma testada em ambos os ciclos.

## 10. Riscos e pendências

10.1. **`quantidade_inicial` histórica permanece NULL.** Nenhum valor foi (ou deveria ser) atribuído retroativamente a `quantidade_inicial` para os lotes já existentes antes desta migration — o campo fica intencionalmente `NULL` para todo o histórico.

10.2. **Novos lotes ainda precisam preencher `quantidade_inicial` na aplicação.** A migration não implementa isso; é uma alteração de código pendente em `lote_service.criar_pendente()` (ou equivalente), a ser feita separadamente, para que lotes cadastrados a partir de agora preservem `quantidade_inicial` como valor histórico imutável.

10.3. **Os novos campos ainda não possuem consumidores na aplicação.** Confirmado por busca no código-fonte (`backend/app/`): nenhuma rota, serviço ou schema atualmente lê ou escreve `status_operacional`, `quantidade_disponivel`, `quantidade_inicial`, `produtos.status`, ou os 6 novos campos de `mercados`. Os campos existirão no schema do banco, mas ficarão inertes até que a lógica de negócio correspondente seja implementada em fase futura.

10.4. **Documentação ainda precisa ser atualizada.** `docs/regras-negocio.md` e `docs/modelo-dados.md` ainda não refletem os 12 novos campos nem a regra de mapeamento de `status_operacional`/`quantidade_disponivel` aprovada na seção 3. Essa atualização ainda não foi feita.

10.5. **`status_operacional` e `produtos.status` continuam `VARCHAR` sem `CHECK`/ENUM.** Não há constraint no banco validando os valores possíveis desses dois campos — são texto livre. Isso foi uma decisão consciente para esta fase (evitar criar tipos ENUM antes de definir o vocabulário definitivo), mas representa risco de inconsistência futura caso código de aplicação escreva valores fora do vocabulário esperado (`disponivel`/`esgotado`/`descartado` para `status_operacional`; `'ativo'` e o que mais vier a ser definido para `produtos.status`).

## 11. Recomendação final

A Migration `0002_campos_operacionais` está **tecnicamente apta para futura execução no banco principal (`valida`)**, condicionada a:
- Execução isolada, como ação explicitamente autorizada em separado desta revisão documental (esta sessão não deve incluir execução no banco principal).
- Um backup do banco `valida` imediatamente antes da execução, como já é praticado nas migrations anteriores.

Nenhum problema estrutural ou de integridade de dados foi encontrado nos upgrades corrigidos e independentes realizados no cycle1 e no cycle2. A repetibilidade foi confirmada entre esses dois upgrades, e a reversibilidade final da versão corrigida foi confirmada no cycle2, conforme detalhado nas seções 8 e 9. As cinco pendências listadas na seção 10 não bloqueiam a aplicação segura da migration — são itens de acompanhamento para as próximas fases de desenvolvimento, não defeitos da migration em si.

---

**Atualização posterior à aprovação deste relatório:** a Migration 0002
foi executada no banco principal `valida` (ver Etapa 4/5 da sessão de
execução), com backup pré-migration validado e verificação pós-upgrade
concluída. `criar_pendente` e `editar_pendente` já preenchem/sincronizam
`status_operacional`, `quantidade_disponivel` e `quantidade_inicial`.
Venda, descarte e FEFO continuam não implementados.
