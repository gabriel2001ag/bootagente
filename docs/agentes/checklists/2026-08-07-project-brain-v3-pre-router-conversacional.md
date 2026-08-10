# Checklist de Tarefa

## Identificacao

- Tarefa: correção V3 — pré-router conversacional
- Data: 2026-08-07
- Solicitante: usuario
- Status: concluido
- Agente coordenador: dev_senior

## Entendimento

- Objetivo: impedir que conversa casual crie task técnica e handoff Senior.
- Resultado esperado: `ola` recebe resposta local sem efeitos técnicos.
- Fora de escopo: classificação semântica por LLM e alteração do ERP.
- Criterios de aceite: intents explícitos, thresholds mínimos, regressões e suíte verde.

## Classificacao de informacoes

### Fatos encontrados no codigo

- O classificador roda antes do pipeline técnico.
- Há nove categorias explícitas e prioridade para intenção técnica.
- Casual, status e memória podem encerrar localmente sem task.

### Regras informadas pelo usuario

- Conversa casual não deve consumir o pipeline técnico.
- Perguntas funcionais ambíguas não podem virar status operacional por engano.

### Inferencias tecnicas

- Lista explícita de status é mais segura que correspondência ampla nesta versão.

### Duvidas pendentes

- Nenhuma para a correção; paráfrases adicionais ficam como lacuna conhecida.

## Impacto em funcoes atuais

- Funcao atual auditada: entrada do Chat antes do Orchestrator.
- Comportamento atual que funciona: tarefas técnicas e comandos explícitos.
- Mudanca ou regressao possivel: saudação misturada ocultar intenção técnica.
- Alcance e riscos: somente classificação inicial do Chat.
- Alternativa de menor impacto: classificador determinístico com precedência técnica.
- Confirmacao explicita do usuario: confirmada.

## Plano

| Etapa | Responsavel | Status | Evidencia |
| --- | --- | --- | --- |
| Baseline e causa | dev_senior | concluido | `119 passed`; Task 5 |
| Classificador/pré-router | backend_ci4_audit | concluido | `chat/classifier.py`, `chat/service.py` |
| Thresholds | backend_ci4_audit | concluido | configuração e testes focados |
| Validacao | qa_reviewer | concluido | `132 passed` |
| Registro final | docs_memory | concluido | documentação desta correção |

## Riscos

| Risco | Impacto | Mitigacao |
| --- | --- | --- |
| Ocultar tarefa técnica em saudação mista | análise não executada | intenção técnica tem precedência |
| Status amplo capturar pergunta de negócio | resposta incorreta | frases explícitas e teste de NF-e |
| Overlap fraco poluir contexto | confiança artificial | thresholds por tipo |

## Arquivos afetados

- `project-brain/chat/classifier.py`
- `project-brain/chat/service.py`
- configuração, testes e documentação do Project Brain
- ERP: nenhum arquivo alterado.

## Testes

- [x] Baseline `119 passed`
- [x] Final `132 passed`
- [x] Antes: Task 5 `unknown/0.08/SENIOR`, 15 arquivos e handoff
- [x] Depois: `ola` local, delta de tasks 0, sem retrieval/router/handoff/auditoria/usage
- [x] Task de itens: 3/2/2 e `ANALYSIS_ONLY`
- [x] ERP `OS-496`, commit `280f3e9c0caf89e637d4da6fbd80ceadf5f8155d`, limpo

## Evidencias

- Testes de Chat e core determinístico aprovados na suíte de `132 passed`.
- Git do ERP limpo e sem arquivos alterados.

## Pendencias

- Ampliar paráfrases de status somente com exemplos não ambíguos.

## Retrospectiva

- O que funcionou: separar interação conversacional de intenção técnica.
- O que precisa melhorar: cobertura controlada de paráfrases.
- Padrao reaproveitavel: classificar antes de criar recursos persistentes.
- Nova regra: caminhos casuais devem provar ausência de efeitos laterais.
