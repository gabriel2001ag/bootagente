# V3 — Project Brain Chat + Smart Router

## Decisão

A V3 evolui incrementalmente o pipeline existente. O Chat transforma mensagens
significativas em tasks normais e trabalha sobre `Orchestrator`,
`ContextBuilder`, memória, QA, Git e o handoff invertido do Codex. Não existe um
segundo sistema de tasks nem integração paralela com LLM.

## Mapa de reuso

| Requisito V3 | Tratamento | Componente |
| --- | --- | --- |
| Pipeline de task | reutilizado | `core/orchestrator.py` |
| Contexto de código e memória | estendido | `core/context_builder.py` |
| Rules, patterns e lessons | estendido | `brain/memory.py` |
| Similaridade | estendido | `brain/similarity.py` |
| Classificação, confiança e router | novo sobre o pipeline | `core/routing.py` |
| Conceitos e aliases | novo | `core/concepts.py` |
| Compressão e métricas | novo sobre `TaskContext` | `core/context_compressor.py` |
| Chat e sessões | novo | `chat/service.py`, `chat/sessions.py` |
| Handoff Senior | adapter sobre a ponte | `senior/gateway.py` |
| CLI | estendida | `cli/main.py` com `brain chat` |
| Persistência V3 | estendida | `migrations/0004_chat_router.sql` |
| Segurança, QA e Git | reutilizados | `CommandRunner`, `QAAgent`, `GitService` e ponte |
| MCP | adiado | etapa posterior |
| Escrita automática no ERP | adiada | fora do escopo |

## Fluxo

```text
mensagem do Chat
  -> pré-router conversacional
  -> resposta local para casual/status/memória, sem task
  -> ou intenção técnica
  -> task normal
  -> expansão de conceitos
  -> rules/patterns/lessons/tasks similares
  -> busca de código e ContextBuilder
  -> ConfidenceEngine
  -> SmartRouter
  -> LOCAL / ANALYSIS_ONLY / HYBRID / SENIOR / WAITING_FOR_SENIOR
  -> auditoria, métricas e eventual handoff invertido
```

## Pré-router conversacional

`chat/classifier.py` executa antes do router técnico. As categorias exatas são
`GREETING`, `CASUAL_CHAT`, `COMMAND`, `STATUS_QUERY`, `MEMORY_QUERY`,
`CODE_QUESTION`, `ANALYSIS_TASK`, `IMPLEMENTATION_TASK` e `UNKNOWN`.
Implementação, análise e código têm precedência sobre saudação em frases mistas.

`GREETING` e `CASUAL_CHAT` retornam resposta local; `STATUS_QUERY` e
`MEMORY_QUERY` direcionam aos handlers correspondentes. Esses caminhos não
criam task, não executam retrieval, busca de código, `SmartRouter`, handoff,
auditoria ou registro em `knowledge_usage`.

Regressão comprovada:

| Entrada `ola` | Antes (Task 5) | Depois |
| --- | --- | --- |
| Categoria/confiança | `unknown` / `0.08` | `GREETING`, sem score técnico |
| Rota | `SENIOR` | resposta local |
| Task criada | 1 | 0 |
| Arquivos candidatos | 15 | busca não executada |
| Handoff/auditoria/usage | executados | não executados |

Os thresholds de inclusão são rule `0.20`, pattern `0.20`, lesson `0.10`, task
similar `0.10` e código `0.20`. O teste relacionado a itens de pedido continua
recuperando 3 rules, 2 patterns e 2 lessons e seguindo `ANALYSIS_ONLY`.

Limite conhecido: consultas naturais de status usam correspondências explícitas.
Paráfrases não catalogadas podem seguir conservadoramente o pipeline técnico.
Isso evita classificar uma pergunta de negócio, como status de NF-e, como status
operacional do Project Brain.

O `ContextCompressor` limita rules, patterns, lessons, tarefas similares e
arquivos. A redução compara, em caracteres JSON, o contexto completo e o payload
selecionado; não representa tokens reais.

`fallback.enabled: false` impede o pipeline local quando um provider automático
está indisponível e deixa a task em `WAITING_FOR_SENIOR`. No provider
`codex-vscode`, a recuperação determinística e read-only continua obrigatória
antes do handoff, mesmo com o fallback desabilitado: ela prepara o contexto
mínimo exigido pelo Senior, não executa patch e não é tratada como autonomia
local.

## Fórmula de confiança

```text
confidence =
    0.30 * melhor similaridade
  + 0.15 * min(1, rules / 3)
  + 0.15 * min(1, patterns / 2)
  + 0.15 * min(1, lessons / 2)
  + 0.15 * confiança de validação
  + 0.10 * min(1, conceitos / 2)
```

O valor é arredondado a quatro casas. Análise com confiança `>= 0.40` segue
`ANALYSIS_ONLY`. Mudança com `>= 0.80` segue `HYBRID` com Senior ou `LOCAL`
sem ele. Abaixo disso segue `SENIOR` quando disponível ou
`WAITING_FOR_SENIOR`.

## Senior Gateway

`VSCodeCodexInvertedGateway` adapta `CodexWorkspaceBridge` e fornece
`brain senior context <task-id>`. Não chama API OpenAI, Codex CLI, comandos
privados, teclado ou interface visual. O contrato continua rejeitando resposta
inválida, contexto Git obsoleto e aprendizado não aprovado.

## Evidência de regressão

| Métrica | Antes (Task 2) | Depois (Task 3) |
| --- | ---: | ---: |
| Categoria | `unknown` | `orders` |
| Confiança | `0.20` | `0.73` |
| Rules | 3 | 3 |
| Patterns | 0 | 2 |
| Lessons | 2 | 2 |
| Tasks similares | 0 | 1 |
| Resultado | `REQUIRES_SENIOR` | `ANALYSIS_ONLY` offline |

A Task 3 registrou 15 arquivos candidatos, 12 selecionados e redução estimada
de `11.11%` por caracteres. A Task 4, sem memória adequada, permaneceu
conservadora: `business_flow`, confiança `0.355` e handoff `SENIOR`.

## Limites

- Recuperação determinística, sem embeddings nem LLM local.
- Métrica de contexto em caracteres, não tokens.
- A extensão `openai.chatgpt` não comprova autenticação.
- Handoff do Codex manual e assíncrono.
- `symbols_selected` foi zero no caso real.
- Chat não autoriza escrita automática nem contorna Git, arquivos sensíveis,
  denylist, QA, aprovação de aprendizagem ou evidências.
- Paráfrases de status fora da lista explícita ainda podem cair no pipeline
  técnico; a cobertura deve crescer somente com casos não ambíguos.
