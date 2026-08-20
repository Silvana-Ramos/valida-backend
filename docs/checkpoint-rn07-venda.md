# Checkpoint — RN07: fechamento da etapa de venda de estoque

## 1. Objetivo

Registrar o fechamento da implementação de **venda** (saída de estoque)
da RN07 (`docs/regras-negocio.md#rn07--movimentações-de-estoque`), a
segunda movimentação implementada depois de `entrada`. Cobre o desenho
aprovado, os arquivos alterados, a validação executada e os riscos
residuais encontrados na revisão final.

Contexto: `entrada` já havia sido implementada e fechada antes desta
etapa, seguindo o mesmo padrão de serviço (transação única, `SELECT ...
FOR UPDATE`, isolamento por `id_mercado`, endpoint por trás de
`Depends(obter_id_mercado_atual)`). `venda` reaproveita integralmente
esse padrão.

## 2. O que foi implementado

| Peça | Arquivo | Detalhe |
|---|---|---|
| Schema de entrada | `backend/app/schemas/movimentacao_estoque.py` | `VendaEstoqueRequest` (`quantidade: Decimal` com `Field(gt=0)`, `criado_por: Optional[int]`) — `id_lote` vem da rota, não do corpo |
| Exceção de negócio | `backend/app/services/movimentacao_service.py` | `SaldoInsuficienteParaVenda` — exceção única, cobre saldo parcial insuficiente e lote já `esgotado`/`descartado` (ambos sempre têm `quantidade_disponivel = 0`, RN07), sem checagem separada de `status_operacional` |
| Serviço | `backend/app/services/movimentacao_service.py` | `registrar_venda(db, id_mercado, id_lote, request)` |
| Endpoint | `backend/app/routers/lotes.py` | `POST /lotes/{id_lote}/venda` |
| Testes unitários | `backend/tests/test_movimentacao_service_venda.py` | 11 testes, `Session` mockada |
| Testes HTTP | `backend/tests/test_lotes_router_venda.py` | 12 testes, `TestClient`, `get_db` sobrescrito com `Session` mockada |

### Regras de negócio implementadas em `registrar_venda`

- **Isolamento por `id_mercado`:** parâmetro obrigatório do serviço, vindo de fonte confiável (nunca do corpo/query do cliente); lote de outro mercado é tratado como `LoteNaoEncontrado` (mesma exceção do "não existe", sem vazar existência — RN05).
- **`SELECT ... FOR UPDATE` com `populate_existing=True`:** `db.get(LoteORM, id_lote, with_for_update=True, populate_existing=True)` — trava a linha do lote e evita a armadilha do identity map do SQLAlchemy (mesma correção já aplicada em `entrada`).
- **Transação única com rollback explícito:** todo o corpo (leitura travada, checagens, `db.add` da movimentação e do histórico, `db.commit()`) roda dentro de `try/except Exception: db.rollback(); raise` — qualquer falha antes ou durante o commit reverte e libera o lock, sem mascarar a exceção original.
- **Atualização de `quantidade_disponivel` e `status_operacional`:** venda parcial mantém `status_operacional = disponivel`; venda que zera o saldo muda para `esgotado`. Saldo insuficiente (`quantidade_solicitada > quantidade_disponivel`) é rejeitado antes de qualquer escrita.
- **`quantidade_inicial` imutável:** nunca é tocada em nenhum caminho de `registrar_venda`.
- **`movimentacoes_estoque`:** grava `tipo_movimentacao = venda`, `sentido = None`, `origem = usuario`, `id_movimentacao_estornada = None` — satisfaz todos os `CHECK`s da Migration 0003 (`quantidade_movimentada > 0`, `quantidade_anterior >= 0`, `quantidade_resultante >= 0`, `sentido` nulo fora de `ajuste`, etc.).
- **`historico_acoes`:** grava `tipo_acao = TipoAcao.VENDA` com `quantidade_anterior`/`quantidade_movimentada`/`quantidade_resultante` preenchidos (RN04).

### Códigos HTTP do endpoint

| Situação | HTTP |
|---|---|
| Sucesso | 201 (`MovimentacaoEstoque`) |
| Header de chave ausente/inválido | 401 |
| Lote não encontrado / de outro mercado | 404 (`LoteNaoEncontrado`) |
| Lote não `confirmado` | 409 (`AcaoInvalidaParaStatus`) |
| Saldo insuficiente | 409 (`SaldoInsuficienteParaVenda`) |
| `quantidade <= 0` | 422 (automático do Pydantic) |
| Qualquer outra exceção | 500 (propagação, sem captura) |

## 3. Validação executada

- **11 testes unitários** (`test_movimentacao_service_venda.py`, `Session` mockada — nenhuma conexão a banco real ou em memória): venda parcial mantendo `disponivel`; venda total zerando saldo e mudando para `esgotado`; saldo insuficiente sem gravar nada; lote já `esgotado` rejeitado por saldo insuficiente; lote `descartado` rejeitado por saldo insuficiente; lote de outro mercado → `LoteNaoEncontrado`; lote não confirmado → `AcaoInvalidaParaStatus`; `quantidade_inicial` nunca alterada; rollback em falha antes do commit; commit único; `SELECT FOR UPDATE` com `populate_existing=True` (argumentos conferidos explicitamente).
- **12 testes HTTP** (`test_lotes_router_venda.py`, `TestClient`, `get_db` sobrescrito): venda parcial 201; venda total 201 com saldo zero; header ausente 401; chave inválida 401; lote não encontrado 404; lote de outro mercado 404; lote não confirmado 409; saldo insuficiente 409; quantidade `0` e `-1` → 422; `id_mercado` em query string ignorado; exceção inesperada → 500 (via `TestClient(app, raise_server_exceptions=False)`).
- **Suíte completa: 41/41 testes passando** (23 pré-existentes + 11 + 12 novos), sem nenhuma conexão a banco em nenhum teste.

## 4. Riscos residuais (nenhum bloqueante)

1. **Conteúdo de `historico_acoes` não é verificado por nenhum teste** — só a contagem de `db.add()` é checada; `tipo_acao = TipoAcao.VENDA` e as quantidades gravadas nunca são inspecionadas diretamente (diferente de `movimentacao_orm`, que é coberto indiretamente pela resposta HTTP). Um erro de cópia futuro nesse campo não seria pego pela suíte atual.
2. **Assimetria de rigor entre as suítes de `entrada` e `venda`** — a suíte de `venda` tem 2 testes que a de `entrada` não tem (asserção explícita dos argumentos do `SELECT FOR UPDATE`; exceção inesperada → 500). Vale replicar esses 2 testes em `entrada` depois.
3. **Precedência entre 401 e 422 não testada** — nenhum teste cobre o caso de header inválido **e** quantidade inválida simultaneamente.
4. **Comparação de chave de API não é de tempo constante** — `dict.get()` padrão, não `hmac.compare_digest`; risco teórico de timing attack, aceito como proporcional para o piloto (já discutido na comparação de alternativas).
5. **`descartado` ainda não é alcançável por nenhum caminho de código real** — só `entrada` sabe rejeitá-lo como precondição; `retirada_vencimento` (única operação que produziria esse estado) não existe ainda. Cobertura de teste preparatória, sem risco operacional atual.
6. **Passo operacional pendente, não um bug de código** — `settings.mercado_api_keys` no ambiente real segue no padrão `{}`; a variável `MERCADO_API_KEYS` ainda precisa ser configurada no servidor antes de qualquer uso real do endpoint.

## 5. Status geral

**Etapa de venda da RN07 fechada.** Desenho aprovado, código implementado exatamente conforme aprovado, validação estática e testes (41/41) passando. Os 6 riscos residuais acima são oportunidades de reforço (mais asserções, testes replicados, decisão de precedência, dureza de comparação), não defeitos funcionais — nenhum impede considerar esta etapa concluída. `retirada` e `ajuste` (RN07) seguem como próximas etapas separadas, não iniciadas.
