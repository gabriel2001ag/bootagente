# Retrospectiva

- Data: 2026-08-07
- Tarefa: Project Brain V3 — Chat + Smart Router
- Agentes envolvidos: dev_senior, backend_ci4_audit, qa_reviewer, docs_memory

## Resultado

A V3 adicionou Chat, recuperação conceitual, confiança, Smart Router, compressão
de contexto, sessões e gateway sem substituir o pipeline nem alterar o ERP.

## Evidencias

- Baseline `103 passed`; final `119 passed`.
- Task 3: `orders`, `0.73`, 3 rules, 2 patterns, 2 lessons, 1 similar,
  `ANALYSIS_ONLY` offline.
- Task 3: 6101 para 5423 caracteres, redução estimada `11.11%`.
- Task 4: `business_flow`, `0.355`, handoff `SENIOR`.
- ERP `OS-496`, commit `280f3e9c0caf89e637d4da6fbd80ceadf5f8155d`,
  limpo e sem arquivos alterados.

## Problemas encontrados

- A busca literal não recuperava patterns nem task similar no caso real.
- O score anterior não tratava lessons e conceitos como sinais independentes.

## Aprendizados do projeto

- Conhecimento antes do código melhora classificação e reduz contexto.
- Confiança deve expor sinais e pesos e manter casos novos conservadores.
- Chat deve ser camada fina sobre tasks e proteções.
- Redução em caracteres não equivale a tokens.

## Checklists atualizados

- Criado checklist V3.
- Criada decisão de evolução incremental.
- Atualizada memória apenas com fatos validados.
