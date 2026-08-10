# Registro de Decisao Tecnica

- Data: 2026-08-07
- Tarefa: correção V3 — pré-router conversacional
- Status: concluido
- Decisor: dev_senior

## Contexto

`ola` atravessava o pipeline técnico, criou a Task 5 com `unknown/0.08/SENIOR`,
selecionou 15 arquivos e preparou handoff.

## Opcoes consideradas

1. Manter toda entrada como task.
2. Usar correspondência ampla para qualquer conversa.
3. Classificar deterministicamente antes do router, com intents explícitos e precedência técnica.

## Decisao

Adotar a opção 3. Casual, status operacional e memória podem responder sem task;
análise, implementação, código e desconhecido permanecem no pipeline técnico.

## Motivo

Elimina custo e auditoria indevidos sem enfraquecer o tratamento conservador de
solicitações técnicas ou ambíguas.

## Impacto

- `ola`: de Task 5 `unknown/0.08/SENIOR` para resposta local e zero tasks.
- Suite: `119 passed` para `132 passed`.
- Retrieval mínimo: rule/pattern `0.20`, lesson/similar `0.10`, código `0.20`.
- Fluxo de itens preservado com 3 rules, 2 patterns, 2 lessons e `ANALYSIS_ONLY`.
- ERP inalterado.

## Plano de reversao

Remover o pré-router e restaurar o encaminhamento direto ao `_handle_request`.
Essa reversão não altera dados do ERP, mas reintroduz tasks casuais indevidas.
