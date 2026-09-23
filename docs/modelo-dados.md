# Modelo de dados do Valida

Este documento descreve as entidades do sistema em nível conceitual. Não
representa schema SQL nem migrations — é a referência descritiva a partir
da qual a implementação será feita em uma fase posterior, mediante
confirmação do usuário.

Todas as regras que governam o comportamento destas tabelas estão em
[`regras-negocio.md`](regras-negocio.md).

Os campos abaixo marcados como "(Migration 0002)" foram adicionados pela
Migration 0002, já executada no banco principal. `status_operacional`,
`quantidade_disponivel` e `quantidade_inicial` já são preenchidos e
sincronizados pelo cadastro e pela edição de lote
(`criar_pendente`/`editar_pendente`); venda, descarte e FEFO ainda não
têm nenhum consumidor no código. Ver [`regras-negocio.md`](regras-negocio.md#rn06--status-operacional-do-lote-e-quantidade-disponível)
(RN06) e [`validacao-migration-0002.md`](validacao-migration-0002.md)
para detalhes.

As tabelas `movimentacoes_estoque`, `importacoes` e `itens_importacao`, e
as 3 colunas aditivas em `historico_acoes` (`quantidade_anterior`,
`quantidade_movimentada`, `quantidade_resultante`), foram criadas pela
Migration 0003, já executada no banco principal em 2026-08-17. Ver
[`checkpoint-migration-0003.md`](checkpoint-migration-0003.md) e
[`revisao-prontidao-migration-0003.md`](revisao-prontidao-migration-0003.md)
para detalhes, incluindo a regra formal de rollback pós-produção.

O serviço de estoque (RN07) está **completo no código para os quatro
tipos de movimentação — `entrada`, `venda`, `retirada` e `ajuste`**
(`app/services/movimentacao_service.py`, `POST /lotes/{id_lote}/entrada`,
`POST /lotes/{id_lote}/venda`, `POST /lotes/{id_lote}/retirada` e
`POST /lotes/{id_lote}/ajuste`) — ver
[`checkpoint-rn07-venda.md`](checkpoint-rn07-venda.md),
[`checkpoint-rn07-retirada.md`](checkpoint-rn07-retirada.md) e
[`checkpoint-rn07-ajuste.md`](checkpoint-rn07-ajuste.md) para o
fechamento detalhado de cada etapa (item 5 da "Ordem de implementação"
abaixo).

A tabela `sessoes_whatsapp` (ver seção própria abaixo) corresponde à
**Migration 0006, preparada mas ainda não aplicada** ao banco principal —
faz parte do planejamento da integração com o WhatsApp para o piloto
(fluxo guiado por menu, sem NLU/LLM nesta fase, decisão aprovada
explicitamente pelo usuário). Hoje o sistema não tem nenhum webhook nem
cliente de envio de mensagens implementado; esta tabela só passa a ter
um consumidor real numa fase posterior, fora do escopo desta migration.

A **pipeline de importação também está implementada, como MVP** —
`app/services/importacao_service.py`, `POST /importacoes`,
`GET /importacoes/{id}` e `GET /importacoes/{id}/itens` — cobrindo só
importação de **vendas** via **CSV** (Excel, PDF, FEFO multi-lote e
importação de entrada/retirada/ajuste ficam fora deste MVP; ver
[`checkpoint-rn07-importacao.md`](checkpoint-rn07-importacao.md) para o
desenho completo, as limitações assumidas e os riscos residuais). Isso
conclui o item 6, e com ele **toda a "Ordem de implementação" abaixo está
concluída** (itens 1 a 4 pelo schema da Migration 0003; item 5 pelos
quatro serviços de movimentação; item 6 por este MVP de importação).

As tabelas `relatorios_acao_diaria`, `itens_relatorio_diario` e
`acoes_preventivas` foram criadas pela Migration 0007 (Gestão Preventiva
de Perdas — Fase 1), já executada no banco principal. Cobrem a geração
de um relatório diário por mercado com uma fotografia dos lotes em risco
(`app/services/relatorio_acao_diaria_service.py`,
`POST /relatorios-acao-diaria`,
`GET /relatorios-acao-diaria/{id_relatorio}/itens`) e o registro/
atualização de ações preventivas sobre os itens desse relatório
(`app/services/acao_preventiva_service.py`,
`POST /relatorios-acao-diaria/itens/{id_item_relatorio}/acoes`,
`PATCH /relatorios-acao-diaria/acoes/{id_acao_preventiva}`). A execução
diária automática, o consumo de `mercados.relatorio_diario_ativo`/
`horario_relatorio_diario`, e a Fase 2 (`acao_movimentacoes`,
`episodios_risco` e cálculo automático de perda evitada) — todos
mencionados no docstring da migration ou já existentes como colunas sem
uso — **não fazem parte desta implementação** (ver
[`regras-negocio.md`](regras-negocio.md#rn08--gestão-preventiva-de-perdas-fase-1)).

## Nota sobre "lote"

O termo **lote** é usado neste projeto para o registro de estoque em si
(produto + quantidade + validade cadastrados em um momento), que é a
entidade central do sistema. O **número de lote** impresso na embalagem
ou nota fiscal é apenas um campo opcional dentro desse registro, já que
nem todo produto ou nota fiscal traz esse código.

## `mercados`

Cada comércio cliente do Valida (tenant).

| Campo | Tipo | Observação |
|---|---|---|
| id | PK | ID do mercado |
| nome | texto | |
| telefone_whatsapp | texto, único | número principal de contato |
| segmento | enum | padaria, açougue, hortifruti, farmácia, mercearia, conveniência, outro |
| status | enum | ativo, inativo |
| data_cadastro | timestamp | |
| timezone | texto, opcional | (Migration 0002) fuso horário do mercado (fuso IANA, ex. `America/Sao_Paulo`), usado para agendamento de relatórios/alertas e, desde 2026-08-26, para o cálculo de `dias_restantes`/`nivel_risco` (RN01) — `NULL` ou valor inválido usa o fallback `America/Sao_Paulo` |
| horario_abertura | hora, opcional | (Migration 0002) horário de abertura do comércio |
| horario_relatorio_diario | hora, opcional | (Migration 0002) horário configurado para envio do relatório diário |
| relatorio_diario_ativo | boolean, not null, default false | (Migration 0002) liga/desliga o envio do relatório diário para este mercado |
| limite_valor_atencao | decimal, opcional | (Migration 0002) limite de valor (R$) em risco que dispara atenção especial |
| limite_quantidade_atencao | decimal, opcional | (Migration 0002) limite de quantidade em risco que dispara atenção especial |

## `usuarios`

Pessoas que interagem pelo WhatsApp em nome de um mercado (dono ou
funcionário).

| Campo | Tipo | Observação |
|---|---|---|
| id | PK | |
| id_mercado | FK → mercados | |
| telefone_whatsapp | texto | |
| nome | texto | |
| papel | enum | dono, funcionario |

## `sessoes_whatsapp`

**Migration 0006, preparada mas ainda não aplicada ao banco principal**
(ver nota no topo deste documento). Estado de uma conversa guiada por
menu em andamento pelo WhatsApp (piloto, sem NLU/LLM). Existe uma linha
só enquanto o usuário está no meio de um fluxo com várias perguntas
(ex.: cadastro de produto: nome → quantidade → validade → confirmação);
ausência de linha significa "sem conversa ativa" — nesse caso o bot
responde com o menu principal, sem precisar de um valor de `estado`
específico para isso.

| Campo | Tipo | Observação |
|---|---|---|
| id_usuario | PK, FK → usuarios | uma sessão ativa por usuário; `ON DELETE CASCADE` |
| id_mercado | FK → mercados, not null | denormalizado — mesmo padrão de isolamento (RN05) já usado em `lotes`/`movimentacoes_estoque`/`historico_acoes` |
| estado | texto, not null | passo atual do fluxo guiado (ex.: `aguardando_produto`, `aguardando_quantidade`, `aguardando_validade`, `aguardando_confirmacao_cadastro`, `aguardando_escolha_confirmar_pendente`, `aguardando_escolha_cancelar_pendente`) — convenção de negócio, sem `CHECK`/`ENUM` associado (mesma decisão já tomada para `lotes.status_operacional`, RN06), para não exigir uma migration a cada ajuste no desenho do fluxo de mensagens enquanto ele ainda está sendo construído |
| dados_parciais | jsonb, not null, default `{}` | campos já coletados no meio do fluxo (ex.: `{"produto_nome": "Pão Francês", "quantidade": 10}`) |
| criado_em | timestamp, not null, default `now()` | |
| atualizado_em | timestamp, not null, default `now()` | atualizado a cada passo do fluxo; também serve de base para uma limpeza futura de sessões abandonadas |

Constraints: PK `id_usuario`; FK `id_usuario → usuarios(id)` `ON DELETE
CASCADE`; FK `id_mercado → mercados(id)`. Índice não único em
`id_mercado`.

**Deduplicação de mensagem (idempotência do webhook):** decisão
explicitamente adiada para uma fatia futura, separada desta tabela — não
faz parte da Migration 0006.

## `produtos`

Catálogo de produtos por mercado, evitando repetir nome/categoria a cada
cadastro de lote.

| Campo | Tipo | Observação |
|---|---|---|
| id | PK | |
| id_mercado | FK → mercados | |
| nome | texto | |
| categoria | enum | laticínio, padaria, hortifruti, carne, mercearia, farmácia, outro |
| unidade_medida | enum | un, kg, litro, pacote |
| preco_venda | decimal, opcional | preço de venda atual do produto, compartilhado por todos os seus lotes. Nesta fase, só para armazenamento — sem cálculo de margem ou desconto automático ainda |
| status | texto, opcional | (Migration 0002) VARCHAR livre, sem CHECK/ENUM; registros existentes com status NULL recebem 'ativo' durante o backfill da Migration 0002 |
| codigo_sistema_origem | texto, opcional | (Migration 0002) código do produto em sistema externo de origem (ex.: ERP do comerciante) |
| codigo_barras | texto, opcional | (Migration 0002) código de barras do produto |

Nesta fase, `preco_venda` só é gravado no cadastro inicial do produto
(quando ele é criado automaticamente a partir do primeiro lote que o
referencia). Se o produto já existir no catálogo, um preço de venda
informado em um novo cadastro de lote **não sobrescreve** o valor
existente — a atualização de preço de venda de um produto já cadastrado
terá um fluxo específico em fase futura, não uma sobrescrita automática.

Custo de aquisição **não** é um atributo do produto — cada lote tem o seu
próprio `preco_custo` (ver tabela `lotes` abaixo), já que o mesmo produto
pode ser reabastecido por custos diferentes a cada entrada.

## `lotes`

Núcleo do sistema: cada registro de estoque com validade, sobre o qual
são calculados risco e alertas.

| Campo | Tipo | Observação |
|---|---|---|
| id | PK | |
| id_mercado | FK → mercados | isolamento entre comércios (RN05) |
| id_produto | FK → produtos | |
| quantidade | numérico | |
| numero_lote | texto, opcional | código de lote da embalagem/nota fiscal, se existir |
| data_validade | data | |
| data_entrada | timestamp | quando o item chegou/foi cadastrado |
| origem_cadastro | enum | texto, foto, nota_fiscal |
| status | enum | pendente_confirmacao, confirmado, vendido, descartado |
| nivel_risco | enum | normal, atencao, risco, urgente, vencido — calculado (RN01), não editável manualmente. Enquanto `pendente_confirmacao`, é apenas uma prévia recalculada a cada consulta; torna-se oficial na confirmação (RN02) |
| dias_restantes | inteiro | snapshot do último cálculo oficial, para histórico/relatório. Idem observação acima quanto a prévia x oficial |
| data_ultima_atualizacao | timestamp | atualizado a cada mudança de quantidade, status ou nível de risco |
| criado_por | FK → usuarios | |
| preco_custo | decimal, opcional | custo de aquisição **deste lote específico**. Lotes diferentes do mesmo `id_produto` podem ter custos diferentes (ex.: reposições em datas distintas); nunca compartilhado ou herdado entre lotes |
| status_operacional | texto, opcional | (Migration 0002) VARCHAR livre, sem CHECK/ENUM; ver mapeamento em RN06 |
| quantidade_disponivel | numérico, opcional | (Migration 0002) ver mapeamento em RN06 |
| quantidade_inicial | numérico, opcional | (Migration 0002) mutável enquanto o lote está `pendente_confirmacao`; consolidado e imutável a partir da confirmação — nunca alterado por venda, retirada ou ajuste; `NULL` para lotes anteriores à Migration 0002 sem valor confiável; ver RN06 |

Cancelar um lote ainda `pendente_confirmacao` remove o registro desta
tabela (RN02) — não existe status "cancelado". A ação fica preservada em
`historico_acoes`, referenciando o `id_lote` mesmo após a remoção.

### Índices adicionados pela Migration 0002

Índices não únicos, de suporte a consultas operacionais:

| Índice | Tabela | Colunas |
|---|---|---|
| ix_lotes_produto_data_validade | lotes | id_produto, data_validade |
| ix_lotes_produto_status_operacional | lotes | id_produto, status_operacional |
| ix_produtos_mercado_codigo_origem | produtos | id_mercado, codigo_sistema_origem |
| ix_produtos_mercado_codigo_barras | produtos | id_mercado, codigo_barras |

Os quatro índices são não únicos, são criados no upgrade para 0002 e
removidos no downgrade para 0001.

## `movimentacoes_estoque`

Ledger especializado de movimentações reais de estoque por lote — fonte
numérica autoritativa para reconciliação de saldo. Só existe para lotes
com `status = confirmado` (RN07).

| Campo | Tipo | Observação |
|---|---|---|
| id | PK | |
| id_mercado | FK → mercados | isolamento entre comércios (RN05); parte das FKs compostas com `id_lote`, `id_importacao` e `id_movimentacao_estornada` |
| id_lote | FK → lotes | parte da FK composta com `id_mercado` |
| id_importacao | FK → importacoes, opcional | parte da FK composta com `id_mercado`; preenchido quando a movimentação se origina de uma importação |
| tipo_movimentacao | enum | entrada, venda, retirada, ajuste |
| sentido | enum, opcional | entrada, saida — só preenchido quando `tipo_movimentacao = ajuste` |
| quantidade_movimentada | numérico | sempre positivo; magnitude do movimento |
| quantidade_anterior | numérico | saldo do lote antes deste movimento |
| quantidade_resultante | numérico | saldo do lote depois deste movimento |
| origem | enum | usuario, sistema, importacao_externa |
| referencia_externa | texto, opcional | identificador do evento no sistema de origem; rastreabilidade secundária (a deduplicação primária ocorre em `itens_importacao`) |
| id_movimentacao_estornada | FK → movimentacoes_estoque, opcional | parte da FK composta com `id_mercado` (autorreferenciada); só preenchido quando `tipo_movimentacao = ajuste`; aponta para a movimentação original sendo corrigida |
| criado_por | FK → usuarios, opcional | |
| data_hora | timestamp | |

Constraints: `UNIQUE (id, id_mercado)` em `movimentacoes_estoque` (nova —
alvo da FK composta autorreferenciada abaixo e da FK composta já existente
de `itens_importacao.id_movimentacao`); `UNIQUE (id, id_mercado)` em
`lotes` (alvo da FK composta com `id_lote`); FK composta
`(id_importacao, id_mercado) → importacoes(id, id_mercado)`; FK composta
`(id_movimentacao_estornada, id_mercado) → movimentacoes_estoque(id, id_mercado)`
(autorreferenciada); `CHECK (quantidade_movimentada > 0)`;
`CHECK (quantidade_anterior >= 0)`; `CHECK (quantidade_resultante >= 0)`;
`sentido` só não-nulo quando `tipo_movimentacao = ajuste`;
`id_movimentacao_estornada` só não-nulo quando `tipo_movimentacao = ajuste`;
`referencia_externa` obrigatória quando `origem = importacao_externa`;
índice único parcial `(id_mercado, origem, referencia_externa) WHERE referencia_externa IS NOT NULL`.

Índices: PK `id`; `(id_lote, data_hora)`; `(id_mercado, data_hora)`; `id_importacao`.

Nenhuma linha desta tabela é alterada ou apagada após criada — correções
são sempre novas linhas (`tipo_movimentacao = ajuste`). Ver RN07 para as
regras completas de venda, retirada, ajuste, concorrência e origem do
saldo inicial.

## `importacoes`

Controle de cada arquivo de importação processado por mercado — impede
reprocessar o mesmo arquivo.

| Campo | Tipo | Observação |
|---|---|---|
| id | PK | |
| id_mercado | FK → mercados | |
| nome_arquivo | texto | |
| hash_arquivo | texto | ex.: SHA256 do conteúdo; base da UNIQUE com `id_mercado` |
| status | enum | pendente, processando, concluida, concluida_com_erros, falhou |
| total_linhas | inteiro, opcional | preenchido ao iniciar o processamento |
| total_processadas | inteiro, not null, default 0 | |
| total_duplicadas | inteiro, not null, default 0 | |
| total_com_erro | inteiro, not null, default 0 | |
| criado_por | FK → usuarios, opcional | `NULL` para disparo automático |
| data_hora_inicio | timestamp, not null, default now() | |
| data_hora_fim | timestamp, opcional | preenchido ao concluir |

Constraints: `UNIQUE (id_mercado, hash_arquivo)` (idempotência primária de
arquivo); `UNIQUE (id, id_mercado)` (alvo de FK composta de
`itens_importacao`); `CHECK`s de totais `>= 0`.

Índices: PK `id`; `(id_mercado, data_hora_inicio)`.

## `itens_importacao`

Cada linha de um arquivo de importação — idempotência primária por linha,
entre arquivos diferentes do mesmo mercado.

| Campo | Tipo | Observação |
|---|---|---|
| id | PK | |
| id_importacao | FK → importacoes | parte da FK composta com `id_mercado` |
| id_mercado | FK → mercados | denormalizado, necessário para a UNIQUE entre arquivos; parte das FKs compostas com `id_importacao`, `id_movimentacao` e `id_lote` |
| numero_linha | inteiro | |
| referencia_externa | texto | identificador do evento no sistema de origem |
| id_produto | FK → produtos, opcional | nulo se não resolvido |
| id_lote | FK → lotes, opcional | parte da FK composta com `id_mercado`; nulo se não resolvido/ambíguo |
| id_movimentacao | FK → movimentacoes_estoque, opcional | parte da FK composta com `id_mercado`; preenchido quando a linha gerar uma movimentação |
| status_processamento | enum | pendente, processada, duplicada, erro |
| mensagem_erro | texto, opcional | |
| dados_brutos | jsonb | linha original do arquivo, para auditoria |

Constraints: `UNIQUE (id_importacao, numero_linha)`; `UNIQUE (id_mercado, referencia_externa)`
(idempotência primária real); FK composta `(id_importacao, id_mercado) → importacoes(id, id_mercado)`;
FK composta `(id_movimentacao, id_mercado) → movimentacoes_estoque(id, id_mercado)`; FK composta
`(id_lote, id_mercado) → lotes(id, id_mercado)`.

Índices: PK `id`; `id_importacao`; as duas `UNIQUE` acima.

### Ordem de implementação

`movimentacoes_estoque`, `importacoes` e `itens_importacao` (e a alteração
aditiva de `historico_acoes`) devem ser implementadas nesta ordem, por
dependência de FK:

1. `importacoes`
2. `movimentacoes_estoque` (inclui `UNIQUE (id, id_mercado)` em `lotes`, alvo das FKs compostas)
3. `itens_importacao`
4. Alteração aditiva em `historico_acoes`
5. Código de serviço de estoque (entrada, venda, retirada, ajuste)
6. Pipeline de importação

## `historico_acoes`

Auditoria completa de eventos sobre lotes e sobre o mercado (RN04).

| Campo | Tipo | Observação |
|---|---|---|
| id | PK | |
| id_mercado | FK → mercados | |
| id_lote | inteiro, opcional, indexado | **sem FK rígida** (decisão já aprovada, preservada nesta atualização): nulo para ações gerais (ex.: relatório semanal); pode referenciar um lote já removido (ex.: cancelamento) ou alterado depois — o registro histórico continua consultável independente do estado atual do lote |
| tipo_acao | enum | ver vocabulário abaixo |
| descricao | texto | detalhe legível da ação |
| origem | enum | conversa, foto, etiqueta, nota_fiscal, arquivo, automacao |
| data_hora | timestamp | |
| quantidade_anterior | numérico, opcional | (RN07) preenchido somente quando a ação altera efetivamente o estoque |
| quantidade_movimentada | numérico, opcional | (RN07) idem |
| quantidade_resultante | numérico, opcional | (RN07) idem |

Constraints e índices: PK `id`; FK `id_mercado → mercados`; índice
`ix_historico_acoes_id_lote (id_lote)`, **propositalmente sem
`FOREIGN KEY`**; nenhuma `UNIQUE`/`CHECK` nova associada às 3 colunas
adicionadas.

**Observação sobre `origem`:** o vocabulário documental aprovado para
`historico_acoes.origem` é `conversa`, `foto`, `etiqueta`, `nota_fiscal`,
`arquivo`, `automacao`. O código atualmente implementado (`OrigemAcao`)
ainda usa um vocabulário diferente (`sistema`, `usuario`). Essa
divergência entre documentação e código é conhecida e deverá ser tratada
em uma alteração de código/migration futura, separada — o código não é
alterado nesta atualização.

Vocabulário de `tipo_acao` (reconciliado com o Documento Mestre V1.2):

- Mantidos: `cadastro`, `edicao`, `confirmacao`, `cancelamento`.
- Adicionados (Documento Mestre): `entrada`, `venda`, `retirada_vencimento`, `ajuste`, `correcao`, `importacao`.
- Definidos, não utilizados atualmente, candidatos a limpeza futura: `status_alterado`, `alerta_enviado`, `sugestao_gerada`, `desconto_aplicado`, `combo_sugerido`, `destaque_sugerido`, `reorganizacao_sugerida`, `marcado_vendido`, `marcado_descartado`.

Mapeamento com `movimentacoes_estoque.tipo_movimentacao` (RN07):

| `historico_acoes.tipo_acao` | `movimentacoes_estoque.tipo_movimentacao` |
|---|---|
| entrada | entrada |
| venda | venda |
| retirada_vencimento | retirada |
| ajuste | ajuste |
| correcao | (nenhum — retificação de informação, não de quantidade) |
| cadastro, confirmacao, edicao, cancelamento, importacao | (nenhum — não representam movimentação de estoque) |

## `faixas_risco`

Configuração das faixas de risco oficiais (RN01), mantida em tabela para
permitir ajuste futuro sem alterar código — não editável pelo usuário
final via WhatsApp, apenas por administração do sistema.

| Campo | Tipo | Observação |
|---|---|---|
| id | PK | |
| nivel_risco | enum | normal, atencao, risco, urgente, vencido |
| dias_min | inteiro, opcional | limite inferior da faixa (inclusive) |
| dias_max | inteiro, opcional | limite superior da faixa (inclusive) |

Valores iniciais (globais, conforme RN01):

| nivel_risco | dias_min | dias_max |
|---|---|---|
| vencido | null (−∞) | −1 |
| urgente | 0 | 3 |
| risco | 4 | 7 |
| atencao | 8 | 15 |
| normal | 16 | null (+∞) |

## `relatorios_acao_diaria`

Um relatório por mercado/dia, com a fotografia agregada dos lotes em
risco (RN08).

| Campo | Tipo | Observação |
|---|---|---|
| id | PK | |
| id_mercado | FK → mercados | isolamento entre comércios (RN05) |
| data_referencia | data | dia a que o relatório se refere, no fuso do mercado (RN01) |
| gerado_em | timestamp, not null, default now() | |
| status | texto, not null, default `gerado` | VARCHAR(20) livre, sem CHECK/ENUM; único valor usado hoje |
| qtd_vencidos | inteiro, not null, default 0 | |
| qtd_vence_hoje | inteiro, not null, default 0 | itens com `dias_restantes == 0` — subconjunto de `qtd_urgentes`, não uma faixa própria de RN01 |
| qtd_urgentes | inteiro, not null, default 0 | |
| qtd_risco | inteiro, not null, default 0 | |
| qtd_atencao | inteiro, not null, default 0 | |
| valor_em_risco | decimal(14,2), not null, default 0 | soma do `valor_em_risco` dos itens não nulos |
| total_acoes_recomendadas | inteiro, not null, default 0 | definido só na geração do relatório; nunca alterado por registrar/atualizar uma ação |
| total_acoes_realizadas | inteiro, not null, default 0 | recalculado (contagem completa) quando o status de alguma ação vinculada muda — ver RN08 |

Constraints: `UNIQUE (id_mercado, data_referencia)`
(`uq_relatorio_diario_mercado_data`) — base da idempotência de geração
(RN08). Índice `(id_mercado, data_referencia)`.

**Estado atual de implementação:** geração idempotente via
`relatorio_acao_diaria_service.gerar_ou_obter` — chamada repetida no
mesmo dia devolve o relatório já existente, sem regenerar nem duplicar
itens. Exposto via `POST /relatorios-acao-diaria` (200). **Não há
execução automática/agendada** — a geração só acontece quando este
endpoint é chamado explicitamente; `mercados.relatorio_diario_ativo` e
`mercados.horario_relatorio_diario` (Migration 0002) não são lidos por
nenhum código.

## `itens_relatorio_diario`

Fotografia de cada lote acionável (RN08) incluído em um relatório —
gravada uma única vez na geração, nunca recalculada depois.

| Campo | Tipo | Observação |
|---|---|---|
| id | PK | |
| id_relatorio | FK → relatorios_acao_diaria | |
| id_produto | FK → produtos | |
| id_lote | FK → lotes | FK simples — diferente do padrão de FK composta com `id_mercado` usado em `movimentacoes_estoque`/`itens_importacao` |
| data_validade | data | snapshot do lote no momento da geração |
| quantidade_disponivel | numérico(14,3), not null | snapshot |
| preco_custo | decimal(10,2), opcional | snapshot |
| dias_restantes | inteiro, not null | snapshot (RN01) |
| classificacao_validade | texto, not null | VARCHAR(20) livre, sem CHECK/ENUM; espelha os valores de `nivel_risco` |
| prioridade | texto, not null | VARCHAR(20) livre, sem CHECK/ENUM; valores usados hoje: `CRITICA`, `ALTA`, `MEDIA`, `BAIXA` (RN08) |
| valor_em_risco | decimal(14,2), opcional | `preco_custo × quantidade_disponivel`; `NULL` quando `preco_custo` é nulo |
| acao_recomendada | texto, not null | texto fixo por nível de risco (RN08) |

Constraints: `UNIQUE (id_relatorio, id_lote)` (`uq_item_relatorio_lote`).
Índices em `id_relatorio` e `id_lote`.

**Sem coluna `id_mercado`**: o isolamento por mercado (RN05) é garantido
via JOIN até `relatorios_acao_diaria.id_mercado` na camada de serviço,
não por uma coluna própria nesta tabela.

**Estado atual de implementação:** gerada por
`relatorio_acao_diaria_service.gerar_ou_obter`; listada via
`GET /relatorios-acao-diaria/{id_relatorio}/itens`
(`relatorio_acao_diaria_service.listar_itens`, leitura pura — não
recalcula nada). Não existe hoje nenhuma tabela `acao_movimentacoes`
nem `episodios_risco` (Fase 2) que consuma esta fotografia.

## `acoes_preventivas`

Ação preventiva registrada sobre um item do relatório diário (RN08).

| Campo | Tipo | Observação |
|---|---|---|
| id | PK | |
| id_item_relatorio | FK → itens_relatorio_diario | |
| id_usuario_responsavel | FK → usuarios, opcional | |
| acao_recomendada | texto, not null | sempre copiada do item; nunca aceita do cliente |
| acao_realizada | texto, opcional | |
| status | texto, not null, default `recomendada` | VARCHAR(20) livre, sem CHECK/ENUM; vocabulário aprovado (RN08): `recomendada`, `em_andamento`, `concluida`, `cancelada` |
| data_inicio | timestamp, opcional | |
| data_fim | timestamp, opcional | |
| resultado_operacional | texto, opcional | |
| observacao | texto, opcional | |
| criada_em | timestamp, not null, default now() | |
| atualizada_em | timestamp, not null, default now() | sem `onupdate` no banco — atualizado manualmente pela aplicação a cada mudança |

Constraints: **sem `UNIQUE`** em `id_item_relatorio` — o banco permite
múltiplas ações por item; a regra de "uma ação por item" na Fase 1 é
garantida só na camada de aplicação (RN08), não por constraint. Índices
em `id_item_relatorio` e `id_usuario_responsavel`.

**Sem coluna `id_mercado`**: isolamento (RN05) via duplo JOIN
(`id_item_relatorio → itens_relatorio_diario.id_relatorio →
relatorios_acao_diaria.id_mercado`).

**Estado atual de implementação:** `acao_preventiva_service.registrar`
(idempotente por item — devolve a ação existente em vez de criar outra)
e `acao_preventiva_service.atualizar`, expostos via
`POST /relatorios-acao-diaria/itens/{id_item_relatorio}/acoes` e
`PATCH /relatorios-acao-diaria/acoes/{id_acao_preventiva}`. Nenhum
cálculo automático de "perda evitada" existe ainda — isso depende da
Fase 2 (`acao_movimentacoes`/`episodios_risco`), não implementada.
