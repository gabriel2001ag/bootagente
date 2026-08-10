# Checklist de Tarefa

## Identificacao

- Tarefa: Project Brain V3 — Chat + Smart Router
- Data: 2026-08-07
- Solicitante: usuario
- Status: concluido
- Agente coordenador: dev_senior

## Entendimento

- Objetivo: evoluir o Brain com Chat, recuperação conceitual, confiança explicável e roteamento.
- Resultado esperado: `brain chat` reutiliza o conhecimento da Task 1 no caso real da Task 2.
- Fora de escopo: MCP, LLM/API paralela, automação visual e alteração do ERP.
- Criterios de aceite: comandos preservados, regressão corrigida, offline conservador e suíte verde.

## Classificacao de informacoes

### Fatos encontrados no codigo

- Chat usa tasks normais e `Orchestrator`.
- Confiança usa seis sinais determinísticos.
- Contexto é limitado e medido por caracteres.
- Gateway mantém a integração invertida do Codex.

### Regras informadas pelo usuario

- Reutilizar infraestrutura e conhecimento existentes.
- Não alterar o ERP.
- Usar Task 2 como regressão e exigir Senior quando faltar conhecimento.

### Inferencias tecnicas

- Conceitos e aliases são extensão de menor impacto para a busca literal.

### Duvidas pendentes

- Nenhuma.

## Impacto em funcoes atuais

- Funcao atual auditada: tasks, contexto, memória, fallback, QA, Git e Senior.
- Comportamento atual que funciona: comandos V1/V2 e ponte invertida.
- Mudanca ou regressao possivel: confiança excessiva ou desvio das proteções.
- Alcance e riscos: Project Brain e dados locais.
- Alternativa de menor impacto: estender componentes e manter Chat como camada fina.
- Confirmacao explicita do usuario: confirmada.

## Plano

| Etapa | Responsavel | Status | Evidencia |
| --- | --- | --- | --- |
| Auditoria e baseline | dev_senior | concluido | `103 passed`; Tasks 1/2 |
| Recuperação e router | backend_ci4_audit | concluido | módulos V3 e testes |
| Banco de dados | dev_senior | concluido | migration 0004 |
| Validacao | qa_reviewer | concluido | `119 passed`; Tasks 3/4 |
| Registro final | docs_memory | concluido | documentação V3 |

## Riscos

| Risco | Impacto | Mitigacao |
| --- | --- | --- |
| Confiança artificial | rota insegura | pesos explícitos e pergunta desconhecida |
| Memória inteira | contexto excessivo | limites e compressor |
| Chat paralelo | perda de auditoria | toda solicitação cria task normal |
| Alterar ERP | regressão | somente leitura e Git final limpo |

## Arquivos afetados

- `project-brain/core/concepts.py`
- `project-brain/core/routing.py`
- `project-brain/core/context_compressor.py`
- `project-brain/core/context_builder.py`
- `project-brain/core/orchestrator.py`
- `project-brain/brain/memory.py`
- `project-brain/brain/similarity.py`
- `project-brain/chat/`
- `project-brain/senior/gateway.py`
- `project-brain/cli/main.py`
- `project-brain/migrations/0004_chat_router.sql`
- testes e documentação do Project Brain
- ERP: nenhum arquivo alterado.

## Testes

- [x] Baseline `103 passed`
- [x] Final `119 passed`
- [x] Task 3: `orders`, `0.73`, 3/2/2/1, `ANALYSIS_ONLY` offline
- [x] Task 4: `business_flow`, `0.355`, handoff `SENIOR`
- [x] Task 3: redução `11.11%` por caracteres
- [x] ERP `OS-496`, commit `280f3e9c0caf89e637d4da6fbd80ceadf5f8155d`, limpo

## Evidencias

- `task-data/infocase-web/TASK-00003/chat-metrics.json`.
- `task-data/infocase-web/TASK-00004/chat-metrics.json`.
- Zero arquivos do ERP alterados.

## Pendencias

- MCP e aplicação automática de patches permanecem adiados.

## Retrospectiva

- O que funcionou: reuso do pipeline e do conhecimento da Task 1.
- O que precisa melhorar: medir tokens somente com fonte confiável.
- Padrao reaproveitavel: conhecimento -> conceitos -> código -> rota -> Senior.
- Nova regra: toda nova rota deve ter teste conservador de baixa confiança.
