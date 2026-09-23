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

**Fuso horário de `data_atual` (correção de 2026-08-26):** `data_atual`
é sempre a data corrente **no fuso horário do mercado** dono do lote
(`mercados.timezone`), nunca o relógio/fuso do servidor onde a
aplicação roda. Quando o mercado não tem `timezone` configurado
(`NULL` — hoje a maioria, já que o campo foi criado na Migration 0002
só para agendamento de relatórios/alertas e nunca foi preenchido para
este fim) ou o valor salvo não é um fuso IANA reconhecido, usa-se o
fallback padrão `America/Sao_Paulo`. Calcular com o fuso do servidor
(tipicamente UTC no Railway) causava classificação incorreta perto da
virada do dia — um lote podia ser tratado como vencido, ou deixar de
ser, horas antes/depois do horário local do comércio. Implementado em
`hoje_do_mercado` (`backend/app/services/lote_service.py`), usado por
todo chamador de `calcular_risco`.

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

**Estado atual de implementação:** o recálculo em si está implementado
em `app/services/recalculo_risco_service.py` (`recalcular_todos`), com
o ponto de entrada executável `backend/scripts/recalcular_risco_diario.py`.
Percorre todos os lotes `confirmado` de todos os mercados numa única
execução — uma exceção deliberada ao isolamento por mercado (RN05):
não é uma requisição em nome de nenhum mercado, é uma rotina de
sistema que processa cada lote isoladamente, um de cada vez. Cada lote
é travado e commitado individualmente; um erro num lote fica
registrado no resumo da execução e não impede os demais de serem
processados. `data_atual` (RN01) é resolvida **por lote**, a partir do
fuso do mercado dono daquele lote — não existe um "hoje" único para a
execução inteira do job, já que mercados diferentes podem estar em
fusos diferentes. `dias_restantes`/`data_ultima_atualizacao` são sempre
atualizados; `historico_acoes` só recebe um registro novo quando
`nivel_risco` muda de faixa (`tipo_acao = status_alterado`,
`origem = sistema` — primeiro uso real desses dois valores do
vocabulário, até então só declarados). O job é idempotente por
natureza: rodar duas vezes no mesmo dia não duplica histórico, porque a
segunda execução já não encontra nenhuma mudança de faixa.

**Ainda não agendado de fato:** o script existe e está testado, mas
nenhum agendador externo (cron, Task Scheduler, ou o mecanismo de cron
de uma hospedagem) o chama ainda — isso depende da decisão de
hospedagem, ainda não tomada. Também **ainda não implementado**: o
envio de alertas proativos que a mudança de faixa deveria disparar
(depende, além do job estar agendado, de Message Templates
pré-aprovados pela Meta — ver a nota sobre a janela de 24h em
`CLAUDE.md`).

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

**Lotes esgotados/descartados não geram alerta operacional (correção de
2026-08-26):** `nivel_risco` (RN01) é calculado só a partir da validade,
sem nenhuma relação com estoque — um lote pode estar numa faixa de risco
e, ao mesmo tempo, já não ter mais unidades disponíveis
(`status_operacional` = `esgotado`/`descartado`). Como `lotes.status`
permanece `confirmado` nesses casos (ver "Compatibilidade com RN07"
acima), nenhuma lista ou alerta voltado para ação do comerciante pode
filtrar só por `status`/`nivel_risco` — precisa também excluir
`status_operacional` != `disponivel`, senão volta a mostrar produtos que
já não existem mais em estoque. Implementado em
`_listar_produtos_vencendo` (`backend/app/services/whatsapp_webhook_service.py`,
única lista de risco ativa hoje). O job diário de recálculo (RN03) e o
histórico de mudança de faixa continuam cobrindo todo lote confirmado,
esgotado inclusive — o filtro é só na camada que decide o que vira
alerta, nunca no cálculo de risco em si. Quando os alertas proativos por
WhatsApp (RN03) forem implementados, o mesmo filtro se aplica lá.

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
mesmo valor (`disponivel`/`= quantidade`). Venda e retirada (RN07) **já
estão implementadas** e levam `status_operacional` a `esgotado` (venda
que zera o saldo) ou `descartado` (retirada que zera o saldo); FEFO
segue não implementado. `status_operacional` (junto com `quantidade`,
que passou a refletir `quantidade_disponivel`) é exposto por GET
/lotes e GET /lotes/{id_lote} — ver schema `Lote` em
`backend/app/schemas/lote.py`.

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

**Venda x vencimento (RN01):** `venda` nunca é aceita sobre um lote vencido
(`dias_restantes < 0`), mesmo com saldo disponível — é rejeitada sem
gravar nada (nem movimentação, nem alteração de `quantidade_disponivel`).
`dias_restantes` é recalculado na hora a partir de `data_validade`, nunca
a partir do valor persistido (só oficial até o próximo job diário, RN03).
Produto vencido só pode sair do estoque por `retirada` (que, no sentido
oposto, exige que o lote já esteja vencido para ser aceita) — nunca por
`venda`.

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

## RN08 — Gestão Preventiva de Perdas (Fase 1)

Gera diariamente, por mercado, uma fotografia dos lotes em risco de
vencimento (`relatorios_acao_diaria` + `itens_relatorio_diario`), e
permite registrar e acompanhar ações preventivas tomadas sobre eles
(`acoes_preventivas`). Ver [`docs/modelo-dados.md`](modelo-dados.md)
para a especificação técnica das 3 tabelas (Migration 0007).

**Lote acionável (decisão da Gestão Preventiva — reaproveita RN01/RN06
sem alterar o texto delas):** um lote entra na fotografia do dia quando,
simultaneamente: `status = confirmado`; `nivel_risco` (RN01) está numa
das faixas `atencao`/`risco`/`urgente`/`vencido` (`normal` fica de
fora); `status_operacional` (RN06) é `disponivel` (`esgotado`/
`descartado` ficam de fora) — mesmo critério já usado em
`_listar_produtos_vencendo` (RN06).

**Um relatório por mercado/dia:** `UNIQUE (id_mercado, data_referencia)`
em `relatorios_acao_diaria`. A geração é idempotente: se já existe
relatório para o dia (resolvido no fuso do mercado, RN01), a chamada
devolve o existente sem regenerar nem duplicar itens.

**Classificação, prioridade e valor em risco de cada item:**
- `classificacao_validade` = `nivel_risco` (RN01), sem recálculo
  próprio.
- `prioridade`: mapeamento 1:1 com `nivel_risco` — `vencido → CRITICA`,
  `urgente → ALTA`, `risco → MEDIA`, `atencao → BAIXA`.
- `valor_em_risco` = `preco_custo × quantidade_disponivel`; `NULL`
  quando `preco_custo` é nulo — nunca estimado.
- `acao_recomendada`: texto fixo por nível de risco.
- `qtd_vence_hoje`: contagem de itens com `dias_restantes == 0` —
  subconjunto informativo de `qtd_urgentes` (faixa 0–3 dias de RN01),
  não uma faixa própria.

**Ações preventivas (Fase 1):**
- Uma ação por item: garantida só na camada de aplicação (o registro
  procura uma ação já existente antes de criar outra); não há `UNIQUE`
  no banco para isso — uma constraint equivalente poderá ser avaliada
  numa migration futura.
- `acao_recomendada` da ação é sempre copiada do item, nunca aceita do
  cliente.
- Status permitidos: `recomendada` (default — registrada, ainda não
  iniciada), `em_andamento`, `concluida` (único que conta para
  `total_acoes_realizadas`), `cancelada`. Sem regra de transição entre
  eles nesta fase — qualquer valor fora do vocabulário é rejeitado.
- `total_acoes_recomendadas` é definido só pela geração do relatório —
  nunca alterado ao registrar ou atualizar uma ação.
- `total_acoes_realizadas` é recalculado (contagem completa das ações
  `concluida` vinculadas ao relatório, nunca incremento/decremento)
  sempre que uma atualização altera o `status` de uma ação.

**Isolamento por mercado (RN05):** `relatorios_acao_diaria` tem
`id_mercado` direto. `itens_relatorio_diario` e `acoes_preventivas` não
têm essa coluna — o isolamento é garantido via JOIN até
`relatorios_acao_diaria.id_mercado` na camada de serviço.

**Estado atual de implementação:** completo — models, schemas,
`app/services/relatorio_acao_diaria_service.py` (`gerar_ou_obter`,
`listar_itens`), `app/services/acao_preventiva_service.py`
(`registrar`, `atualizar`), e o router
`app/routers/relatorios_acao_diaria.py`
(`POST /relatorios-acao-diaria`,
`GET /relatorios-acao-diaria/{id_relatorio}/itens`,
`POST /relatorios-acao-diaria/itens/{id_item_relatorio}/acoes`,
`PATCH /relatorios-acao-diaria/acoes/{id_acao_preventiva}`), registrado
em `main.py`.

**Ainda NÃO implementado nesta fase:**
- Nenhum job/script diário que chame `gerar_ou_obter` automaticamente —
  a geração hoje só acontece sob demanda, via chamada HTTP explícita
  (mesma situação de "ainda não agendado" já descrita na RN03). Não há
  agendador (cron, Task Scheduler, ou equivalente da hospedagem)
  configurado para este relatório.
- Nenhum consumo dos campos `mercados.relatorio_diario_ativo`/
  `horario_relatorio_diario` (Migration 0002) — continuam existindo no
  banco, mas sem nenhum leitor no código; a geração não verifica se o
  mercado tem o relatório diário "ativado", nem respeita o horário
  configurado.
- `acao_movimentacoes` — tabela da Fase 2, não criada, não implementada.
- `episodios_risco` — tabela da Fase 2, não criada, não implementada.
- Cálculo automático de "perda evitada" — funcionalidade da Fase 2, não
  implementada; nenhum campo ou lógica desta fase calcula valor
  efetivamente economizado.
- Envio de alertas proativos relacionados a este relatório (depende,
  além de tudo acima, dos Message Templates pré-aprovados pela Meta —
  mesma pendência já registrada na RN03).
