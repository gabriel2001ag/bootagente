# Registro de Decisao Tecnica

- Data: 2026-08-07
- Tarefa: Project Brain V3 — Chat + Smart Router
- Status: concluido
- Decisor: dev_senior

## Contexto

A Task 2 obteve `unknown` e `0.2`, embora a Task 1 tivesse conhecimento
diretamente relacionado a pedidos e itens.

## Opcoes consideradas

1. Criar pipeline exclusivo para Chat.
2. Trocar a recuperação por API/LLM/embeddings.
3. Estender memória, similaridade e contexto e adicionar Chat/router ao Orchestrator.

## Decisao

Adotar a opção 3. Chat cria tasks normais; conceitos melhoram a recuperação; a
confiança combina sinais explícitos; o router seleciona local, análise, híbrido
ou Senior; o gateway preserva o handoff invertido.

## Motivo

Corrige o caso real, reaproveita auditoria e proteções, evita duplicação e
mantém operação offline sem inventar conhecimento.

## Impacto

- Task 2: `unknown`, `0.2`, 3/0/2/0 matches.
- Task 3: `orders`, `0.73`, 3/2/2/1, `ANALYSIS_ONLY` offline.
- Task 4: `business_flow`, `0.355`, `SENIOR`.
- Suite: `103 passed` para `119 passed`.
- ERP: zero arquivos alterados e Git limpo.

## Plano de reversao

Remover a entrada `chat`, módulos V3 e migration 0004 em desenvolvimento,
restaurando o Orchestrator anterior. Não reverter tasks ou conhecimento.
