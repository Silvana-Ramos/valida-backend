# Checkpoint — RN07: fechamento da pipeline de importação (item 6, MVP)

## 1. Objetivo

Registrar o fechamento do **MVP** da pipeline de importação — item 6 de
"Ordem de implementação" em `docs/modelo-dados.md`, a última peça
pendente da RN07. Com este fechamento, **toda a "Ordem de implementação"
está concluída**: schema (itens 1–4, Migration 0003), serviço de estoque
completo (item 5 — `entrada`/`venda`/`retirada`/`ajuste`) e agora a
pipeline de importação (item 6).

Escopo do MVP, decidido explicitamente durante o desenho (ver histórico
da sessão): **só importação de vendas via CSV**. Entrada/retirada/ajuste
via arquivo, Excel e PDF ficam fora deste MVP — ver seção 4.

## 2. O que foi implementado

| Peça | Arquivo | Detalhe |
|---|---|---|
| Modelos | `backend/app/models/importacao.py`, `backend/app/models/item_importacao.py` | `ImportacaoORM`, `ItemImportacaoORM`, mapeando `importacoes`/`itens_importacao` (Migration 0003) coluna a coluna |
| Pré-requisito | `backend/app/models/produto.py` | `codigo_sistema_origem`/`codigo_barras` adicionados (colunas já existentes desde a Migration 0002, sem consumidor até agora) — necessários para resolver produto por código |
| Schemas | `backend/app/schemas/importacao.py` | `StatusImportacao`, `StatusProcessamentoItem`, `Importacao`, `ItemImportacao` |
| Parser | `backend/app/services/importacao_parser.py` | `parsear_csv` — só biblioteca padrão (`csv`), sem dependência nova; `ArquivoInvalido` para erro crítico |
| Serviço de orquestração | `backend/app/services/importacao_service.py` | `processar_arquivo_venda`, `obter_importacao`, `listar_itens_importacao` |
| Extensão retrocompatível | `backend/app/services/movimentacao_service.py` | `registrar_venda` ganhou `origem`/`referencia_externa` opcionais (padrão `usuario`/`None`, comportamento anterior preservado) |
| Endpoints | `backend/app/routers/importacoes.py` | `POST /importacoes`, `GET /importacoes/{id}`, `GET /importacoes/{id}/itens` |
| Testes unitários | `backend/tests/test_importacao_service.py` | 19 testes, `Session` mockada |
| Testes HTTP | `backend/tests/test_importacoes_router.py` | 13 testes, `TestClient`, `get_db` sobrescrito |
| Dependência nova | `backend/requirements.txt` | `python-multipart` (exigida pelo FastAPI para `UploadFile`) |

### Regras de negócio implementadas em `processar_arquivo_venda`

- **Idempotência de arquivo:** hash SHA256 do conteúdo; mesmo `hash_arquivo` para o mesmo `id_mercado` → `ArquivoJaProcessado` (409), nada é criado.
- **Idempotência de linha:** `referencia_externa` única por mercado (checada contra **todas** as importações do mercado, não só a atual) → `status_processamento = duplicada`, sem gravar movimentação.
- **Erro crítico vs. erro de linha:** arquivo vazio/ilegível/sem colunas obrigatórias, ou acima de `MAX_LINHAS_IMPORTACAO` (500), aborta tudo antes de criar qualquer registro (`ArquivoInvalido`). Erro de linha (produto/lote não encontrado, saldo insuficiente, quantidade inválida, `referencia_externa` vazia) fica isolado naquela linha — o resto do arquivo continua.
- **Resolução de produto:** só busca (nunca cria) — `codigo_sistema_origem` → `codigo_barras` → nome exato, dentro do `id_mercado`. Não encontrado → erro de linha.
- **Resolução de lote:** número de lote explícito (exato, único) ou FEFO de **lote único** — o lote não vencido de validade mais próxima cujo saldo, sozinho, cobre a quantidade. Se nenhum lote isolado cobre → erro de linha ("requer múltiplos lotes — não suportado nesta fase").
- **Reaproveita `registrar_venda`** linha a linha — sem duplicar lógica de saldo/lock/histórico. Cada movimentação nasce com `origem = importacao_externa` e a `referencia_externa` da linha (extensão retrocompatível do serviço, ver acima).
- **Contagem e status final:** `importacoes.status` vira `concluida` (zero erro/duplicada), `concluida_com_erros` (qualquer erro ou duplicada) — nunca `falhou` nesta versão, já que erro crítico aborta antes de criar o registro.

### Códigos HTTP

| Situação | HTTP |
|---|---|
| Upload aceito e processado (mesmo com `concluida_com_erros`) | 201 (`Importacao`) |
| Header de chave ausente/inválido | 401 |
| Arquivo já processado (mesmo hash) | 409 (`ArquivoJaProcessado`) |
| Arquivo inválido/ilegível/acima do limite de linhas | 422 (`ArquivoInvalido`) |
| `GET` de importação não encontrada / de outro mercado | 404 (`ImportacaoNaoEncontrada`) |
| Qualquer outra exceção | 500 (propagação, sem captura) |

## 3. Validação executada

- **19 testes unitários** do serviço de orquestração: linha bem-sucedida (produto resolvido por código de origem, código de barras e nome, em ordem de fallback); produto não encontrado; lote explícito e ambíguo; FEFO escolhendo o lote de validade mais próxima e rejeitando quando nenhum cobre sozinho; quantidade inválida; `referencia_externa` vazia e duplicada; saldo insuficiente; lote não confirmado; arquivo já processado; arquivo inválido; limite de linhas excedido; `origem`/`referencia_externa` gravados corretamente na movimentação; mistura de linhas sucesso/erro/duplicada num mesmo arquivo; status final `concluida`.
  - **Bug real pego durante a escrita dos testes:** o mock só cobria `.filter().all()`, mas o caminho FEFO real usa `.filter().order_by().all()` — sem o `order_by()` configurado, todo lote "sumia" silenciosamente (lista vazia por padrão do `MagicMock`), fazendo os testes de sucesso falharem com "requer múltiplos lotes". Corrigido configurando os dois caminhos de query reais.
- **13 testes HTTP**: upload bem-sucedido (201), erro de linha isolado (201 com `concluida_com_erros`), arquivo já processado (409), arquivo inválido (422), autenticação (401), `id_mercado` em query ignorado, exceção inesperada (500), e os três cenários de `GET` (encontrada, não encontrada, de outro mercado, lista de itens).
  - **Segundo bug pego durante os testes:** `Importacao.model_validate(...)` exige `data_hora_inicio: datetime`, mas o `db.refresh()` mockado só populava o `id` — corrigido estendendo o mock para simular também o `server_default=func.now()` do banco.
- **Suíte completa: 141/141 testes passando** (109 pré-existentes + 32 novos), sem nenhuma conexão a banco em nenhum teste.

## 4. Fora do escopo deste MVP (decisões explícitas do desenho)

- **FEFO multi-lote:** uma linha que exigiria dividir a baixa entre vários lotes vira erro de linha, não é processada automaticamente — o modelo de dados atual (`itens_importacao.id_movimentacao` singular) não comporta múltiplas movimentações por linha sem uma migration nova.
- **Excel (`.xlsx`/`.xls`):** só CSV nesta fase — evita depender de uma biblioteca nova (`openpyxl` ou similar) sem autorização.
- **PDF:** nunca entra nesta pipeline automática (Documento Mestre V1.2, seção 9) — fica reservado para um fluxo assistido separado.
- **Entrada/retirada/ajuste via arquivo:** só `registrar_venda` ganhou os parâmetros `origem`/`referencia_externa`; os outros três serviços de movimentação não foram alterados.
- **Processamento assíncrono:** síncrono dentro da própria requisição HTTP, com teto de 500 linhas — sem fila/worker no projeto ainda.

## 5. Riscos residuais (nenhum bloqueante)

1. **Inconsistência possível entre `movimentacoes_estoque` e `itens_importacao` em caso de crash no meio do processamento.** Cada linha bem-sucedida já foi commitada por `registrar_venda` (transação própria) antes do `ItemImportacaoORM` correspondente ser commitado — uma falha exatamente nesse intervalo deixaria a movimentação gravada sem o item de importação refletir isso. Aceitável para o piloto; já era um risco conhecido desde o desenho.
2. **Nenhum teste sob concorrência real** — mesmo risco já registrado nos checkpoints anteriores para os locks `SELECT FOR UPDATE` (aqui reforçado pela resolução de lote via FEFO, que lê o saldo antes do lock definitivo dentro de `registrar_venda`).
3. **Processamento síncrono de até 500 linhas por requisição não foi testado sob carga real** — cada linha faz pelo menos um `SELECT FOR UPDATE`; o tempo de resposta em produção, com um banco real, é desconhecido nesta fase.
4. **Precedência entre 401 e 422 ainda não testada** — mesmo risco já registrado nos checkpoints de `venda`/`retirada`/`ajuste`.
5. **Comparação de chave de API não é de tempo constante** — mesmo risco já registrado, compartilhado por todos os endpoints.
6. **Passo operacional pendente, não um bug de código** — `settings.mercado_api_keys` no ambiente real segue em `{}`.

## 6. Status geral

**MVP da pipeline de importação fechado — e com ele, toda a "Ordem de implementação" da RN07 (itens 1 a 6) está concluída.** Desenho aprovado em todas as 6 decisões estruturais levantadas (FEFO de lote único, CSV apenas, PDF fora de escopo, erro crítico vs. erro de linha, processamento síncrono com teto de linhas, upload via endpoint HTTP), código implementado exatamente conforme aprovado, dois bugs reais pegos e corrigidos durante a escrita dos testes, 141/141 testes passando. Os riscos residuais são de reforço ou compartilhados com etapas anteriores — nenhum impede considerar este MVP concluído. Ampliações futuras (FEFO multi-lote, Excel, outros tipos de movimentação via arquivo, processamento assíncrono) ficam para quando o volume real do piloto justificar.
