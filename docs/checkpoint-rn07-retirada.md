# Checkpoint — RN07: fechamento da etapa de retirada de estoque

## 1. Objetivo

Registrar o fechamento da implementação de **retirada** (retirada de
produto vencido) da RN07 (`docs/regras-negocio.md#rn07--movimentações-de-estoque`),
a terceira movimentação implementada depois de `entrada` e `venda`. Cobre
o desenho aprovado, os arquivos alterados, a validação executada e os
riscos residuais.

Contexto: `retirada` reaproveita integralmente o padrão de serviço já
fechado em `entrada`/`venda` (transação única, `SELECT ... FOR UPDATE`,
isolamento por `id_mercado`, endpoint por trás de
`Depends(obter_id_mercado_atual)`), com duas diferenças de negócio
próprias: exige que o lote esteja de fato vencido, e o destino do saldo
zerado é `descartado`, não `esgotado`.

## 2. O que foi implementado

| Peça | Arquivo | Detalhe |
|---|---|---|
| Schema de entrada | `backend/app/schemas/movimentacao_estoque.py` | `RetiradaEstoqueRequest` (`quantidade: Decimal` com `Field(gt=0)`, `criado_por: Optional[int]`) |
| Exceções de negócio | `backend/app/services/movimentacao_service.py` | `LoteNaoVencidoNaoAceitaRetirada` (lote ainda não vencido) e `SaldoInsuficienteParaRetirada` (cobre saldo insuficiente e lote já `esgotado`/`descartado`, sem checagem separada de `status_operacional`) |
| Serviço | `backend/app/services/movimentacao_service.py` | `registrar_retirada(db, id_mercado, id_lote, request)` |
| Endpoint | `backend/app/routers/lotes.py` | `POST /lotes/{id_lote}/retirada` |
| Testes unitários | `backend/tests/test_movimentacao_service_retirada.py` | 15 testes, `Session` mockada |
| Testes HTTP | `backend/tests/test_lotes_router_retirada.py` | 13 testes, `TestClient`, `get_db` sobrescrito |

### Regras de negócio implementadas em `registrar_retirada`

- **Isolamento por `id_mercado`:** idêntico a `entrada`/`venda` — parâmetro confiável do serviço; lote de outro mercado é `LoteNaoEncontrado` (RN05).
- **`SELECT ... FOR UPDATE` com `populate_existing=True`:** mesma correção da armadilha do identity map já aplicada em `entrada`/`venda`.
- **Checagem de vencimento (própria de `retirada`):** logo após confirmar `lote.status == confirmado` e **antes** da checagem de saldo, `dias_restantes` é recalculado na hora via `lote_service.calcular_risco(lote_orm.data_validade)` — nunca confia em `nivel_risco`/`dias_restantes` persistidos (RN03: só oficiais até o próximo job diário). Rejeita com `LoteNaoVencidoNaoAceitaRetirada` se `dias_restantes >= 0` (inclui o caso "vence hoje", que não é vencido — RN01 define vencido como `dias_restantes < 0`).
- **Transação única com rollback explícito:** idêntico a `entrada`/`venda` — `try/except Exception: db.rollback(); raise` cobrindo até o `commit()`.
- **Atualização de `quantidade_disponivel` e `status_operacional`:** retirada parcial mantém `disponivel`; retirada que zera o saldo muda para **`descartado`** (não `esgotado` — esse é o destino exclusivo de `venda`).
- **`quantidade_inicial` imutável:** nunca tocada.
- **`movimentacoes_estoque`:** `tipo_movimentacao = retirada`, `sentido = None`, `origem = usuario`, `id_movimentacao_estornada = None`.
- **`historico_acoes`:** `tipo_acao = TipoAcao.RETIRADA_VENCIMENTO` — **nome diferente** de `tipo_movimentacao = retirada` (RN04); verificado explicitamente por teste dedicado (ver seção 3) para evitar o risco de troca por cópia de `registrar_venda`.

### Códigos HTTP do endpoint

| Situação | HTTP |
|---|---|
| Sucesso | 201 (`MovimentacaoEstoque`) |
| Header de chave ausente/inválido | 401 |
| Lote não encontrado / de outro mercado | 404 (`LoteNaoEncontrado`) |
| Lote não `confirmado` | 409 (`AcaoInvalidaParaStatus`) |
| Lote ainda não vencido | 409 (`LoteNaoVencidoNaoAceitaRetirada`) |
| Saldo insuficiente | 409 (`SaldoInsuficienteParaRetirada`) |
| `quantidade <= 0` | 422 (automático do Pydantic) |
| Qualquer outra exceção | 500 (propagação, sem captura) |

## 3. Validação executada

- **15 testes unitários** (`Session` mockada, nenhuma conexão a banco): retirada parcial mantendo `disponivel`; retirada total zerando saldo e mudando para `descartado`; saldo insuficiente sem gravar nada; lote já `esgotado`/`descartado` rejeitados pela mesma checagem de saldo; lote não vencido rejeitado; caso-limite "vence hoje" (`dias_restantes == 0`) ainda rejeitado; checagem de vencimento comprovadamente antes da de saldo (lote não vencido **e** saldo insuficiente ao mesmo tempo → erro de vencimento, não de saldo); lote de outro mercado; lote não confirmado; `quantidade_inicial` nunca alterada; rollback em falha antes do commit; commit único; `SELECT FOR UPDATE` com `populate_existing=True` (argumentos conferidos); **conteúdo exato de `historico_orm.tipo_acao == TipoAcao.RETIRADA_VENCIMENTO` e `movimentacao_orm.tipo_movimentacao == TipoMovimentacao.RETIRADA`** inspecionado diretamente.
- **13 testes HTTP** (`TestClient`, `get_db` sobrescrito): retirada parcial 201; retirada total 201 com saldo zero; header ausente 401; chave inválida 401; lote não encontrado 404; lote de outro mercado 404; lote não confirmado 409; lote não vencido 409; saldo insuficiente 409; quantidade `0`/`-1` → 422; `id_mercado` em query ignorado; exceção inesperada → 500.
- **Suíte completa: 69/69 testes passando** (41 pré-existentes + 15 + 13 novos), sem nenhuma conexão a banco em nenhum teste.

## 4. Riscos residuais

1. **Resolvido nesta etapa (era risco residual de `venda`):** o checkpoint de `venda` registrava que "`descartado` ainda não é alcançável por nenhum caminho de código real". Agora é — uma retirada total leva a `status_operacional = descartado`. O item 5 do checkpoint de `venda` (`checkpoint-rn07-venda.md`) deve ser lido como obsoleto a partir desta etapa.
2. **Resolvido nesta etapa (era risco residual de `venda`):** o checkpoint de `venda` apontava que nenhum teste verificava o conteúdo de `historico_acoes` (só a contagem de `db.add()`). Em `retirada`, um teste dedicado (`test_grava_tipo_acao_retirada_vencimento_e_tipo_movimentacao_retirada`) inspeciona diretamente `tipo_acao` e `tipo_movimentacao` gravados. Vale retroportar esse mesmo teste para `entrada` e `venda`, que ainda não têm.
3. **Precedência entre 401 e 422 ainda não testada** — mesmo risco já registrado em `venda`, não específico de `retirada`.
4. **Comparação de chave de API não é de tempo constante** — mesmo risco já registrado em `venda` (`dict.get()`, não `hmac.compare_digest`); compartilhado por todos os endpoints de movimentação, não específico de `retirada`.
5. **Novo — checagem de vencimento usa `date.today()` do servidor, sem considerar fuso do mercado.** `mercados.timezone` existe desde a Migration 0002 mas não é usado por `calcular_risco()`. Para mercados fora do fuso do servidor, um lote pode ser tratado como "ainda não vencido" ou "já vencido" um dia antes/depois do que seria correto no fuso local do comerciante. Baixo impacto no piloto (poucos mercados, provavelmente mesmo fuso), mas vale registrar para quando a RN03 (recálculo diário) for implementada com fuso por mercado.
6. **Passo operacional pendente, não um bug de código** — mesmo risco já registrado em `venda`: `settings.mercado_api_keys` no ambiente real segue em `{}`.

## 5. Status geral

**Etapa de retirada da RN07 fechada.** Desenho aprovado (incluindo a decisão explícita de exigir lote vencido), código implementado exatamente conforme aprovado, validação estática e 69/69 testes passando. Os riscos residuais listados são de reforço ou compartilhados com etapas anteriores — nenhum é bloqueante. `ajuste` (RN07) segue como próxima etapa, não iniciada.
