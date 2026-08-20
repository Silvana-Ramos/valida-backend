# Valida

## Visão geral

Valida é um agente de IA para pequenos comércios (minimercados, padarias,
açougues, hortifrutis, farmácias, lojas de conveniência) com o objetivo de
**reduzir perdas de produtos por vencimento**.

O agente funciona principalmente pelo WhatsApp, permitindo:

- Cadastrar produtos por mensagem de texto, foto ou nota fiscal.
- Consultar produtos próximos da validade.
- Classificar o risco de cada item conforme os dias restantes até o
  vencimento.
- Sugerir ações para evitar perdas (descontos, combos, destaque na loja,
  reorganização de prateleiras).
- Gerar alertas proativos e relatórios periódicos.

Cada item cadastrado (produto + quantidade + validade, com número de lote
opcional) é chamado de **lote** no sistema. É sobre os lotes que o Valida
calcula risco, gera alertas e sugere ações.

## Arquitetura

```
Comerciante (WhatsApp)
        │
        ▼
Camada de integração WhatsApp (Cloud API da Meta)
        │
        ▼
Backend de orquestração (webhook + agente)
        │
   ┌────┼─────────────┬───────────────┐
   ▼    ▼              ▼               ▼
NLU/LLM  Visão (foto/NF)  Regras de risco  Scheduler (alertas)
   │    │              │               │
   └────┴──────┬───────┴───────────────┘
                ▼
         Banco de dados (produtos, lotes, validades, histórico)
                ▼
      Geração de relatórios e sugestões de ação
                ▼
      Resposta/alerta de volta pelo WhatsApp
```

O WhatsApp é a interface. A inteligência do sistema está em três blocos:
extração de dados (texto, foto, nota fiscal), classificação de risco e
motor de sugestões.

Ponto de atenção arquitetural: mensagens proativas (alertas de vencimento
enviados pelo agente, fora de uma resposta direta ao usuário) só podem ser
enviadas fora da janela de 24h da Meta usando **Message Templates
pré-aprovados**. Isso afeta o desenho da funcionalidade de alertas desde o
início.

## Tecnologias

| Camada | Escolha |
|---|---|
| Integração WhatsApp | WhatsApp Cloud API (Meta), direto, com Business Manager verificado |
| Backend | Python + FastAPI |
| IA (texto, visão, sugestões) | Provedor de IA a definir na implementação. A arquitetura deve permitir troca de provedor sem alterar as regras de negócio. A IA será usada para interpretar mensagens livres, analisar fotos/rótulos e notas fiscais e gerar sugestões de ação. |
| Banco de dados | PostgreSQL |
| Agendamento | Job diário (ex.: APScheduler/Celery) para recálculo de risco e disparo de alertas |
| Hospedagem (MVP) | A definir na fase de implementação (ex.: Railway/Render/Fly.io), migração para nuvem maior na fase de escala |

## Regras oficiais do negócio

As regras de negócio (RN01 a RN05) que governam classificação de risco,
confirmação de cadastro, recálculo diário, rastreabilidade e isolamento
por mercado estão consolidadas em [`docs/regras-negocio.md`](docs/regras-negocio.md).
Essas regras são a fonte de verdade — qualquer implementação futura deve
segui-las.

## Modelo de dados

O modelo de dados (tabelas `mercados`, `usuarios`, `produtos`, `lotes`,
`historico_acoes`, `faixas_risco`) está descrito em
[`docs/modelo-dados.md`](docs/modelo-dados.md). Neste estágio o documento é
descritivo — ainda não há schema SQL nem migrations no projeto.

## Instruções para desenvolvimento

- O projeto está em fase de documentação (Fase 0 do plano de
  desenvolvimento). Nenhum banco de dados, API, webhook ou integração com a
  Meta foi criado ainda.
- Antes de implementar qualquer regra de risco, cadastro ou alerta,
  consulte `docs/regras-negocio.md` — não reinterprete as faixas de risco
  ou o fluxo de confirmação sem alinhar com o usuário primeiro.
- Antes de criar ou alterar tabelas, consulte `docs/modelo-dados.md` como
  referência de campos e relacionamentos.
- Todo cadastro de lote (texto, foto ou nota fiscal) deve passar por
  confirmação explícita do usuário antes de ser persistido como
  definitivo (RN02) — isso deve valer tanto para a lógica de negócio
  quanto para qualquer prototipagem.
- Todas as tabelas e consultas operacionais devem respeitar o isolamento
  por `id_mercado` (RN05) — nunca implementar uma consulta que cruze dados
  entre mercados diferentes.
- Mudanças relevantes em regras de negócio ou no modelo de dados devem ser
  refletidas nos arquivos correspondentes em `docs/`, mantendo-os como
  fonte de verdade atualizada.
- Próximas etapas do plano de desenvolvimento (schema SQL, backend
  FastAPI, webhook do WhatsApp, integração com a Meta) só devem ser
  iniciadas mediante confirmação explícita do usuário.
