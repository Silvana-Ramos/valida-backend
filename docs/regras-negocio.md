# Regras de negócio do Valida

Estas são as regras oficiais consolidadas na Fase 0 do projeto. Elas são a
fonte de verdade para qualquer implementação futura (schema, backend,
lógica de alertas). Alterações nestas regras devem ser combinadas com o
usuário antes de refletidas no código.

## RN01 — Classificação de risco

O nível de risco de um lote é calculado a partir de:

```
dias_restantes = data_validade − data_atual
```

| Nível | Faixa |
|---|---|
| Normal | mais de 15 dias |
| Atenção | 8 a 15 dias |
| Risco | 4 a 7 dias |
| Urgente | 0 a 3 dias (inclui o dia do vencimento) |
| Vencido | dias_restantes < 0 |

O nível de risco é sempre **calculado**, nunca definido manualmente pelo
usuário.

## RN02 — Confirmação obrigatória antes de gravar

Todo cadastro de lote — originado por mensagem de texto, foto ou nota
fiscal — entra no sistema com `status = pendente_confirmacao`.

O registro só passa para `status = confirmado` após o usuário validar
explicitamente pelo WhatsApp (confirmar, editar os dados ou cancelar o
cadastro).

Não há descarte automático por tempo: um cadastro pendente permanece como
`pendente_confirmacao` indefinidamente até que o usuário tome uma ação.
Uma política de limpeza de pendências antigas (ex.: arquivamento após N
dias sem resposta) pode ser definida futuramente, mas é uma regra
separada — não faz parte da RN02.

Cancelar um cadastro ainda `pendente_confirmacao` remove o registro da
lista operacional de lotes — ele não vira um lote permanente e não recebe
um status próprio de "cancelado". A ação de cancelamento é registrada em
`historico_acoes` (RN04) para manter a rastreabilidade, mesmo que o lote
em si deixe de existir.

Enquanto o lote está `pendente_confirmacao`, `dias_restantes` e
`nivel_risco` exibidos são apenas uma **prévia**, recalculada a cada
consulta a partir da `data_validade` informada — sem valor oficial. O
cálculo se torna oficial e é fixado no registro somente no momento da
confirmação (ver RN01 e RN03).

## RN03 — Recálculo diário do nível de risco

O cálculo de `dias_restantes` e `nivel_risco` só é consolidado como
oficial no momento em que o usuário confirma o cadastro (RN02). A partir
daí, o valor fica fixo no registro até a próxima atualização — que só
acontece por dois caminhos: uma nova confirmação (não se aplica, já está
confirmado) ou o recálculo diário abaixo.

Um job agendado, executado diariamente, percorre todos os lotes com
`status = confirmado` e:

- Recalcula `dias_restantes` e `nivel_risco` conforme a RN01.
- Atualiza `data_ultima_atualizacao` do lote.
- Registra em `historico_acoes` sempre que o `nivel_risco` mudar de faixa.

É essa mudança de faixa que serve de gatilho para o envio de alertas
proativos (funcionalidade a ser implementada em fase posterior).

## RN04 — Rastreabilidade completa

Toda mudança relevante em um lote gera um registro em `historico_acoes`,
nunca uma sobrescrita silenciosa. O vocabulário de `tipo_acao` é
reconciliado com o Documento Mestre V1.2 (ver
[`docs/modelo-dados.md`](modelo-dados.md#historico_acoes) para a lista
completa, incluindo os valores definidos mas ainda não utilizados):

- Cadastro inicial (`cadastro`)
- Confirmação do usuário (`confirmacao`)
- Edição de dados (`edicao`)
- Cancelamento de um cadastro pendente antes da confirmação (`cancelamento`)
- Entrada de estoque (`entrada`)
- Venda (`venda`)
- Retirada de produto vencido (`retirada_vencimento`)
- Ajuste de quantidade (`ajuste`)
- Correção de informação registrada (`correcao`)
- Processamento de arquivo de importação (`importacao`)

`historico_acoes` possui três campos opcionais — `quantidade_anterior`,
`quantidade_movimentada` e `quantidade_resultante` — preenchidos **somente
quando a ação representar alteração real de estoque** (`entrada`, `venda`,
`retirada_vencimento`, `ajuste`, ou uma `correcao` que altere
`quantidade_disponivel`). Em qualquer outra ação, os três permanecem
`NULL`.

O mapeamento entre `tipo_acao` e `movimentacoes_estoque.tipo_movimentacao`
está em [`docs/modelo-dados.md`](modelo-dados.md#historico_acoes) e é
detalhado na RN07.

## RN05 — Isolamento por mercado

Todas as tabelas operacionais carregam `id_mercado`. Nenhuma consulta,
relatório ou alerta deve cruzar dados entre mercados (comércios)
diferentes. Cada comerciante só enxerga e recebe informações sobre o
próprio estoque.

## RN06 — Status operacional do lote e quantidade disponível

Além do campo `status` (RN02), cada lote possui um campo complementar
`status_operacional`, que reflete a disponibilidade do lote para fins
operacionais (estoque, sugestões, relatórios). Este campo não substitui
nem altera o comportamento do `status` — ambos coexistem.

O mapeamento aprovado entre `status` e `status_operacional` /
`quantidade_disponivel` é:

| `status`               | `status_operacional` | `quantidade_disponivel` |
|-------------------------|-----------------------|---------------------------|
| `confirmado`            | `disponivel`          | = `quantidade`            |
| `pendente_confirmacao`  | `disponivel`          | = `quantidade`            |
| `vendido`               | `esgotado`            | `0`                        |
| `descartado`            | `descartado`          | `0`                        |

**Compatibilidade com RN07:** os valores `vendido` e `descartado` de
`lotes.status`, na tabela acima, não são atingidos pelas movimentações de
venda/retirada introduzidas pela RN07 — nessas movimentações,
`lotes.status` permanece `confirmado` indefinidamente (inclusive após o
saldo zerar), e é `status_operacional` sozinho, derivado de
`movimentacoes_estoque`, que passa a `esgotado`/`descartado`. As linhas
`vendido`/`descartado` desta tabela documentam valores que `status`
continua podendo assumir tecnicamente (o tipo `StatusLote` do banco não
foi alterado), mas que não são mais o mecanismo usado para refletir venda
ou retirada — ver RN07.

Cada lote também possui um campo `quantidade_inicial`. Enquanto o lote
estiver `pendente_confirmacao`, `quantidade_inicial` pode ser corrigida
(em sincronia com `quantidade`, via edição do cadastro — RN02). No
momento da confirmação, o valor então vigente fica **consolidado**:
a partir da confirmação, `quantidade_inicial` torna-se imutável —
venda, retirada e ajuste (RN07) nunca a alteram. Para lotes históricos
existentes antes da aplicação da Migration 0002, `quantidade_inicial`
permanece `NULL` (sem preenchimento retroativo).

**Estado atual de implementação:** os campos `status_operacional`,
`quantidade_disponivel` e `quantidade_inicial` já estão definidos pela
Migration 0002, já executada no banco principal. O cadastro
(`criar_pendente`) grava `status_operacional = 'disponivel'` e mantém
`quantidade_inicial`/`quantidade_disponivel` sincronizados com
`quantidade`; a edição de um lote ainda `pendente_confirmacao`
(`editar_pendente`) também mantém `quantidade_inicial` e
`quantidade_disponivel` sincronizados sempre que `quantidade` é
corrigida. A confirmação (`confirmar`) não precisa alterar esses três
campos, porque `pendente_confirmacao` e `confirmado` mapeiam para o
mesmo valor (`disponivel`/`= quantidade`). Venda, descarte e FEFO
**ainda não estão implementados** — não existe, hoje, nenhum caminho de
código que leve `status_operacional` a `esgotado` ou `descartado`.

**Ausência de constraint:** `status_operacional` é atualmente um campo
`VARCHAR` livre no banco, sem `CHECK` ou tipo ENUM associado. O
vocabulário definido acima (`disponivel`, `esgotado`, `descartado`) é uma
convenção de negócio, não uma restrição estrutural — a validação desses
valores precisa ser garantida pela aplicação.

Para o histórico completo da decisão e da validação técnica desta regra,
ver [`docs/validacao-migration-0002.md`](validacao-migration-0002.md).

## RN07 — Movimentações de estoque

Um lote com `status = confirmado` pode receber movimentações reais de
estoque, registradas em `movimentacoes_estoque` (ver
[`docs/modelo-dados.md`](modelo-dados.md#movimentacoes_estoque)). Um lote
`pendente_confirmacao` nunca recebe movimentação real — correções nesse
estágio são tratadas pela edição de cadastro (RN02), não por
`movimentacoes_estoque`.

**Tipos de movimentação:** `entrada`, `venda`, `retirada`, `ajuste`.
Venda e retirada podem ser **parciais ou totais** — o lote permanece
`confirmado` em ambos os casos; não existe transição de `lotes.status`
para representar "vendido" ou "descartado" (essa granularidade passa a
ser exclusiva de `status_operacional`, abaixo). Ver RN06 para a
compatibilidade entre as duas regras.

**Regra de saldo:**
- `quantidade_disponivel` nunca pode ficar negativa.
- Enquanto `quantidade_disponivel > 0`, `status_operacional = disponivel`.
- Uma venda que zera o saldo → `status_operacional = esgotado`.
- Uma retirada que zera o saldo → `status_operacional = descartado`.
- `produtos.status` não muda automaticamente em nenhum desses casos.

**`quantidade_inicial`:** permanece imutável após a confirmação — nenhuma
venda, retirada ou ajuste a altera.

**Origem do saldo inicial:** não existe movimentação artificial em
`movimentacoes_estoque` para representar o saldo inicial de um lote. A
reconciliação usa `quantidade_inicial` (imutável, em `lotes`) como ponto
de partida:

```
quantidade_disponivel = quantidade_inicial
                       + Σ(entradas) − Σ(vendas) − Σ(retiradas) ± Σ(ajustes)
```

**Correção/estorno:** um `ajuste` nunca altera ou remove a movimentação
original — é sempre uma nova linha, com `sentido` (`entrada`/`saida`) e
`id_movimentacao_estornada` apontando para a movimentação corrigida.

**Idempotência:** a proteção primária contra duplicidade está em
`importacoes` (por arquivo) e `itens_importacao` (por linha, entre
arquivos do mesmo mercado) — não em `movimentacoes_estoque`, que mantém
apenas uma camada secundária de defesa.

**Concorrência:** toda escrita em `movimentacoes_estoque` ocorre dentro de
uma transação atômica com `SELECT ... FOR UPDATE` sobre o lote, cobrindo
também a atualização de `lotes.quantidade_disponivel`/`status_operacional`
e o registro correspondente em `historico_acoes` (RN04).

Para a especificação técnica completa (campos, constraints, índices),
ver [`docs/modelo-dados.md`](modelo-dados.md#movimentacoes_estoque).

**Adendo (2026-08-18) — comportamento de `status_operacional` em uma
`entrada` sobre lote não disponível:** nem o Documento Mestre V1.2 nem a
redação original desta RN07 definiam o que acontece quando uma `entrada`
é registrada sobre um lote cujo `status_operacional` já não é
`disponivel`. Este adendo fecha essa lacuna, aprovado explicitamente pelo
usuário:

- **Lote `esgotado`:** uma `entrada` volta `status_operacional` para
  `disponivel`. Coerente com a seção 7 do Documento Mestre ("Lote
  esgotado"), que trata o estado `esgotado` como não terminal — o lote
  "permanece armazenado para consulta, auditoria e histórico" e pode
  receber nova quantidade somada quando produto, número de lote e
  validade coincidem (seção 3 do Documento Mestre) — e com o critério de
  seleção do FEFO (seção 8), que já depende só de
  `quantidade_disponivel > 0`, não de `status_operacional`.
- **Lote `descartado`:** uma `entrada` é **rejeitada com erro** — nenhuma
  quantidade é somada, nenhum registro é criado em
  `movimentacoes_estoque` nem em `historico_acoes`. Diferente de
  `esgotado`, o valor `descartado` **não existe no Documento Mestre
  V1.2** (que só define `disponivel`/`esgotado` para `status_operacional`)
  — é uma extensão exclusiva deste projeto, introduzida pela RN06. Este
  adendo assume que um lote marcado `descartado` (saldo zerado por
  retirada de produto vencido) representa unidades fisicamente
  descartadas daquele lote específico; mercadoria nova que chegar depois
  deve virar um lote novo (ou somar a outro lote `disponivel`/`esgotado`
  já existente com mesmo produto/número de lote/validade, conforme a
  regra de igualdade de lotes do Documento Mestre, seção 3), nunca
  reabrir um lote já `descartado`.
- **`quantidade_inicial`:** permanece imutável em qualquer `entrada`,
  inclusive nos dois casos acima — apenas `quantidade_disponivel` é
  alterada. A redação original desta RN07 e da RN06 já enumerava `venda`,
  `retirada` e `ajuste` como movimentações que nunca alteram
  `quantidade_inicial`; este adendo torna explícito que `entrada` segue a
  mesma regra (já implícito na fórmula de reconciliação acima, que só move
  `quantidade_disponivel`).
