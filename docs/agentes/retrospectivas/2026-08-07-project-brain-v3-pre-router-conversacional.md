# Retrospectiva

- Data: 2026-08-07
- Tarefa: correção V3 — pré-router conversacional
- Agentes envolvidos: dev_senior, backend_ci4_audit, qa_reviewer, docs_memory

## Resultado

O Chat agora encerra conversa casual e consultas operacionais reconhecidas antes
de criar task ou executar recuperação, busca, router e handoff.

## Evidencias

- Baseline `119 passed`; final `132 passed`.
- Antes: `ola` gerou Task 5 `unknown/0.08/SENIOR`, 15 arquivos e handoff.
- Depois: resposta local, delta de tasks 0 e ausência de retrieval, código,
  router, handoff, auditoria e uso de conhecimento.
- Fluxo de itens preservado: 3 rules, 2 patterns, 2 lessons, `ANALYSIS_ONLY`.
- ERP limpo em `OS-496`, commit `280f3e9c0caf89e637d4da6fbd80ceadf5f8155d`.

## Problemas encontrados

- Uma saudação era tratada como solicitação técnica desconhecida.
- Correspondência ampla de status poderia capturar status funcional de NF-e.

## Aprendizados do projeto

- Classificação deve anteceder criação de task e consumo do pipeline.
- Teste casual precisa verificar ausência de todos os efeitos laterais.
- Intenção técnica em frase mista deve vencer a saudação.
- Paráfrases de status devem ser adicionadas conservadoramente.

## Checklists atualizados

- Criado checklist e decisão específicos do pré-router conversacional.
- README, arquitetura V3 e memória operacional atualizados.
