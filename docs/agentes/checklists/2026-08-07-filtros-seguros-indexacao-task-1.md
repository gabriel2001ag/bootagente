# Checklist de Tarefa

## Identificacao

- Tarefa: filtros seguros, protecao sensivel, rebuild do ERP e refresh da Task 1
- Data: 2026-08-07
- Solicitante: usuario do ERP `infocase_web`
- Status: concluido
- Agente coordenador: dev_senior

## Entendimento

- Objetivo: reduzir ruido e impedir leitura de conteudo sensivel no indice, preservando o Project Brain fora do ERP.
- Resultado esperado: filtros reutilizaveis, auditoria segura, rebuild somente do indice do projeto 1, novo contexto da Task 1 e handoff ao Codex Senior.
- Fora de escopo: alterar funcionalidade do ERP, executar aprendizagem sem evidencia ou controlar programaticamente a extensao Codex.
- Criterios de aceite: filtros Windows, protecao sensivel antes da leitura, testes verdes, indice menor sem perder codigo relevante e Task 1 em `SENIOR_REQUIRED`.

## Classificacao de informacoes

### Fatos encontrados no codigo

- O Project Brain suporta configuracao global e por projeto, scanner, indexador, busca, auditoria e revisoes de contexto.
- O indice anterior tinha `13810` arquivos, `5541` simbolos e `1951` relacionamentos.
- O rebuild final tem `9378` arquivos, `5230` simbolos e `1409` relacionamentos.
- A auditoria final registrou `21802` skips: `9682` vendor, `4406` writable, `0` node_modules, `0` public/uploads e `7714` outros.
- Os skips writable dividem-se em `4271` de `writable_*` e `135` de `writable`.
- `.env` e `*.cache` foram classificados como `SKIPPED_SENSITIVE`, uma ocorrencia cada, sem persistir conteudo.

### Regras informadas pelo usuario

- O Project Brain deve permanecer externo ao ERP.
- Nenhum codigo funcional do ERP pode ser alterado nesta etapa.
- Excludes devem ter defaults seguros e extensao/sobrescrita por projeto.
- Conhecimento futuro deve conter evidencia real.

### Inferencias tecnicas

- A separacao entre globs comuns e sensiveis reduz o risco de leitura acidental e torna a auditoria explicita.
- Rebuild atomico evita deixar o projeto sem indice valido caso a nova indexacao falhe.

### Duvidas pendentes

- Nenhuma para esta etapa.

## Impacto em funcoes atuais

- Funcao atual auditada: indexacao, busca, montagem de contexto e handoff de task.
- Comportamento atual que funciona: projeto externo registrado e Task 1 existente.
- Mudanca ou regressao possivel: filtros excessivos poderiam ocultar codigo legitimo; rebuild poderia invalidar contexto anterior.
- Alcance e riscos: somente Project Brain e seus dados do projeto 1.
- Alternativa de menor impacto: filtros configuraveis, testes de arquivos legitimos e preservacao das revisoes anteriores.
- Confirmacao explicita do usuario: confirmada no pedido da etapa.

## Plano

| Etapa | Responsavel | Status | Evidencia |
| --- | --- | --- | --- |
| Levantamento tecnico | dev_senior | concluido | scanner, indexador, buscas e contexto auditados |
| Banco de dados | backend_ci4_audit | concluido | migrations de skips e revisoes |
| Backend | backend_ci4_audit | concluido | filtros, sensibilidade, rebuild e refresh |
| Frontend | frontend_ui | concluido | nao aplicavel; nenhuma interface alterada |
| Validacao | qa_reviewer | concluido | `103 passed` |
| Registro final | docs_memory | concluido | checklist, decisao, retrospectiva e memoria |

## Riscos

| Risco | Impacto | Mitigacao |
| --- | --- | --- |
| Excluir codigo legitimo | contexto incompleto | defaults restritos, configuracao por projeto e testes de PHP em `app/` e `public/` |
| Persistir segredo | exposicao de credencial | classificacao `SKIPPED_SENSITIVE` antes da leitura e auditoria sem conteudo |
| Perder indice anterior | indisponibilidade | rebuild atomico |
| Contexto baseado em indice antigo | analise ruidosa | refresh da Task 1 com duas revisoes preservadas |
| Alteracao preexistente no ERP | atribuicao incorreta | risco `PRE_EXISTING_CHANGE` registrado e ERP nao modificado pelo Brain |

## Arquivos afetados

- `project-brain/config.yaml`
- `project-brain/core/config.py`
- `project-brain/analysis/code_scanner.py`
- `project-brain/analysis/project_indexer.py`
- `project-brain/agents/search_agent.py`
- `project-brain/core/context_builder.py`
- `project-brain/core/orchestrator.py`
- `project-brain/core/task.py`
- `project-brain/cli/main.py`
- `project-brain/senior/codex_workspace_bridge.py`
- `project-brain/migrations/0002_index_skips.sql`
- `project-brain/migrations/0003_test_result_revisions.sql`
- `project-brain/tests/test_config.py`
- `project-brain/tests/test_indexer.py`
- `project-brain/tests/test_search_agent.py`
- `project-brain/tests/test_cli_init.py`
- `project-brain/tests/test_codex_workspace_bridge.py`
- Arquivos funcionais alterados no ERP pelo Brain: nenhum.

## Testes

- [x] Caminhos Windows com `/` e `\`
- [x] Exclusoes de `.git`, vendor, node_modules, writable, writable_*, uploads e temporarios
- [x] Protecao de `.env`, `*.cache` e demais globs sensiveis
- [x] PHP legitimo em `app/` e `public/`
- [x] Scanner, indexador, busca e fallback compartilham filtros
- [x] Rebuild e refresh da Task 1
- [x] Suite final: `103 passed`

## Evidencias

- Antes: `13810` files, `5541` symbols, `1951` relationships.
- Depois: `9378` files, `5230` symbols, `1409` relationships.
- Task 1: mesmo ID, `SENIOR_REQUIRED`, contexto final de `2468` bytes, `15` candidatos e `2` revisoes.
- Git ERP: branch `OS-496`, commit iniciado por `806ae`; dirty apenas por modificacao local preexistente do usuario em `app/Views/pedido/impressao/pedido_lote.php`.

## Pendencias

- O handoff esta pronto; a analise funcional pelo Codex Senior ainda deve ser executada e seus conhecimentos aceitos somente com evidencia.

## Retrospectiva

- O que funcionou: filtros comuns e sensiveis centralizados, rebuild atomico e revisoes de contexto.
- O que precisa melhorar: manter metricas de skips visiveis para detectar novas fontes de ruido.
- Padrao reaproveitavel: toda exclusao sensivel deve ocorrer antes da leitura e registrar somente metadados seguros.
- Nova regra para proximas tarefas: refresh de contexto e preservacao da revisao anterior sempre que o indice que o originou for substituido.
