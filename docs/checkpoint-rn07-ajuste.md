# Checkpoint — RN07: fechamento da etapa de ajuste de estoque

## 1. Objetivo

Registrar o fechamento da implementação de **ajuste** (correção/estorno
de estoque) da RN07 (`docs/regras-negocio.md#rn07--movimentações-de-estoque`),
a quarta e última movimentação prevista pela RN07, depois de `entrada`,
`venda` e `retirada`. Com este fechamento, o item 5 da "Ordem de
implementação" de `docs/modelo-dados.md` (*"Código de serviço de estoque
(entrada, venda, retirada, ajuste)"*) está **completo**.

Contexto: `ajuste` reaproveita o padrão de serviço já fechado nas três
etapas anteriores (transação única, `SELECT ... FOR UPDATE`, isolamento
por `id_mercado`, endpoint por trás de `Depends(obter_id_mercado_atual)`),
mas é estruturalmente diferente — não é uma ação nova e independente,
é uma correção que pode ir em qualquer direção (`sentido`) e,
opcionalmente, referenciar (sem alterar ou remover) uma movimentação
anterior.

## 2. O que foi implementado

| Peça | Arquivo | Detalhe |
|---|---|---|
| Schema de entrada | `backend/app/schemas/movimentacao_estoque.py` | `AjusteEstoqueRequest` (`quantidade: Decimal` com `Field(gt=0)`, `sentido: SentidoMovimentacao`, `id_movimentacao_estornada: Optional[int]`, `criado_por: Optional[int]`) |
| Exceções de negócio | `backend/app/services/movimentacao_service.py` | `SaldoInsuficienteParaAjuste` (saldo insuficiente em `sentido=saida`), `MovimentacaoEstornadaNaoEncontrada` (referência inválida), `MovimentacaoJaEstornada` (bloqueio de duplo-estorno); reaproveita `LoteDescartadoNaoAceitaEntrada` (já existente, de `entrada`) para `sentido=entrada` sobre lote `descartado` |
| Serviço | `backend/app/services/movimentacao_service.py` | `registrar_ajuste(db, id_mercado, id_lote, request)` |
| Endpoint | `backend/app/routers/lotes.py` | `POST /lotes/{id_lote}/ajuste` |
| Testes unitários | `backend/tests/test_movimentacao_service_ajuste.py` | 22 testes, `Session` mockada |
| Testes HTTP | `backend/tests/test_lotes_router_ajuste.py` | 18 testes, `TestClient`, `get_db` sobrescrito |

### Regras de negócio implementadas em `registrar_ajuste`

- **Isolamento por `id_mercado`**, **`SELECT ... FOR UPDATE` com `populate_existing=True`** no lote, **transação única com rollback explícito**, **`quantidade_inicial` imutável** — idênticos às três etapas anteriores.
- **`sentido = entrada`**: soma ao saldo; lote `esgotado` reativa para `disponivel` (mesma regra de `entrada`); lote `descartado` rejeita (`LoteDescartadoNaoAceitaEntrada`, reaproveitada, não duplicada).
- **`sentido = saida`**: subtrai do saldo; saldo insuficiente rejeita (`SaldoInsuficienteParaAjuste`) sem gravar nada; saldo zerado muda `status_operacional` para **`esgotado`** — nunca `descartado` (exclusivo de `retirada`).
- **Estorno opcional (`id_movimentacao_estornada`)**: quando informado, a movimentação referenciada é travada com `SELECT ... FOR UPDATE` **antes** de validar que existe no mesmo `id_lote`/`id_mercado` (`MovimentacaoEstornadaNaoEncontrada` se não) e que nenhuma outra linha já a referencia (`MovimentacaoJaEstornada` se sim) — o lock serializa tentativas concorrentes de estornar a mesma movimentação duas vezes. Quando omitido, o ajuste funciona como correção livre de contagem/inventário.
- **`movimentacoes_estoque`**: `tipo_movimentacao = ajuste`, `sentido` sempre preenchido (única das quatro movimentações em que isso é obrigatório), `id_movimentacao_estornada` preenchido só quando aplicável.
- **`historico_acoes`**: `tipo_acao = TipoAcao.AJUSTE` — mesmo nome de `tipo_movimentacao` (diferente de `retirada_vencimento`/`retirada`), menor risco de troca por cópia.

### Códigos HTTP do endpoint

| Situação | HTTP |
|---|---|
| Sucesso | 201 (`MovimentacaoEstoque`) |
| Header de chave ausente/inválido | 401 |
| Lote não encontrado / de outro mercado | 404 (`LoteNaoEncontrado`) |
| Movimentação a estornar não encontrada/de outro lote/mercado | 404 (`MovimentacaoEstornadaNaoEncontrada`) |
| Lote não `confirmado` | 409 (`AcaoInvalidaParaStatus`) |
| Movimentação já estornada por outra linha | 409 (`MovimentacaoJaEstornada`) |
| Lote `descartado` com `sentido = entrada` | 409 (`LoteDescartadoNaoAceitaEntrada`) |
| Saldo insuficiente (`sentido = saida`) | 409 (`SaldoInsuficienteParaAjuste`) |
| `quantidade <= 0` ou `sentido` inválido | 422 (automático do Pydantic) |
| Qualquer outra exceção | 500 (propagação, sem captura) |

## 3. Validação executada

- **22 testes unitários** (`Session` mockada, nenhuma conexão a banco): os dois sentidos (soma/subtrai, mantendo `disponivel`); reativação de `esgotado` e rejeição de `descartado` em `sentido=entrada`; saldo insuficiente e zeragem para `esgotado` em `sentido=saida` (incluindo lote já `esgotado`/`descartado`, cobertos pela mesma checagem de saldo); isolamento por `id_mercado`; lote não confirmado; `quantidade_inicial` imutável; modo sem estorno (`id_movimentacao_estornada = None` no resultado); estorno referenciando movimentação inexistente, de outro lote e de outro mercado (todos `MovimentacaoEstornadaNaoEncontrada`); duplo-estorno bloqueado; estorno válido gravado corretamente; `SELECT FOR UPDATE` com `populate_existing=True` conferido **tanto no lote quanto na movimentação estornada**; rollback em falha; commit único; conteúdo exato de `tipo_acao = TipoAcao.AJUSTE` e `tipo_movimentacao = TipoMovimentacao.AJUSTE` inspecionado diretamente.
- **18 testes HTTP** (`TestClient`, `get_db` sobrescrito): ajuste de entrada e saída 201; reativação de `esgotado` 201; lote `descartado` 409; saldo insuficiente 409; header ausente/inválido 401; lote não encontrado/outro mercado 404; lote não confirmado 409; quantidade inválida e `sentido` inválido 422; estorno não encontrado 404; duplo-estorno 409; estorno válido 201 com `id_movimentacao_estornada` correto na resposta; `id_mercado` em query ignorado; exceção inesperada → 500.
- **Suíte completa: 109/109 testes passando** (69 pré-existentes + 22 + 18 novos), sem nenhuma conexão a banco em nenhum teste.

## 4. Riscos residuais

1. **`sentido` não é validado contra a movimentação sendo estornada.** O serviço não confere se o `sentido` informado é coerente com uma reversão real da movimentação referenciada (ex.: estornar uma `entrada` de +5 com `sentido = entrada` em vez de `saida` **soma** em vez de reverter). A correção da direção fica inteiramente a critério de quem chama a API — a RN07 não especifica essa validação, e não foi implementada. Vale decidir se isso deveria ser reforçado no futuro (ex.: sugerir ou até obrigar o `sentido` oposto ao da movimentação original).
2. **Estornar um `ajuste` com outro `ajuste` não é restringido.** Nada impede que `id_movimentacao_estornada` aponte para uma linha que já é, ela mesma, um estorno — encadeamentos de correções não têm limite nem tratamento especial. RN07 não trata esse caso.
3. **Proteção de duplo-estorno é raciocinada, não testada sob concorrência real.** O `SELECT FOR UPDATE` na movimentação referenciada foi projetado para serializar duas tentativas simultâneas de estorno (mesmo princípio já usado no lock do lote), mas, como todos os testes usam `Session` mockada, essa garantia nunca foi exercida contra um Postgres real com transações concorrentes de fato.
4. **Precedência entre 401 e 422 ainda não testada** — mesmo risco já registrado nos checkpoints de `venda`/`retirada`, não específico de `ajuste`.
5. **Comparação de chave de API não é de tempo constante** — mesmo risco já registrado, compartilhado por todos os quatro endpoints de movimentação.
6. **Passo operacional pendente, não um bug de código** — mesmo risco já registrado: `settings.mercado_api_keys` no ambiente real segue em `{}`.

## 5. Status geral

**Etapa de ajuste da RN07 fechada — e com ela, o serviço de estoque completo (`entrada`, `venda`, `retirada`, `ajuste`).** Desenho aprovado em todos os pontos que foram levantados como abertos (suporte aos dois modos, estorno opcional, saldo zerado → `esgotado`, reativação de `esgotado` sem reativar `descartado`, bloqueio de duplo-estorno), código implementado exatamente conforme aprovado, validação estática e 109/109 testes passando. Os riscos residuais são de reforço (validação de coerência de `sentido`, teste de concorrência real) ou compartilhados com etapas anteriores — nenhum é bloqueante.
