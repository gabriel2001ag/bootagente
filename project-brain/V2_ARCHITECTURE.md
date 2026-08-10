# V2-alpha — Codex no VS Code

## Decisão

O Senior oficial é a extensão `openai.chatgpt` do VS Code. A inspeção do
manifesto instalado encontrou comandos de interface, mas nenhuma API pública
de prompt/resposta. O Project Brain não invoca a extensão, API OpenAI, Codex
CLI, cliques ou teclado.

O fluxo é invertido e assíncrono:

```text
brain task
  → busca, memória, Git e ContextBuilder
  → SENIOR_REQUIRED + senior-request.json
Codex no VS Code
  → brain senior pending/context
  → trabalha normalmente no workspace
  → brain senior submit --file resultado.json
Brain
  → valida contrato e contexto Git
  → registra senior_sessions e senior-response.json
  → WAITING_REVIEW
  → aprende somente com approved_for_learning=true
```

## Extensão encontrada

- ID: `openai.chatgpt`
- Nome: `Codex – OpenAI’s coding agent`
- Versão auditada: `26.5803.41515`
- Comandos públicos encontrados: abertura de sidebar/painel, criação de chat e
  adição de arquivo/contexto.
- API pública de prompt/resposta: não encontrada no manifesto nem exportada
  pelo entrypoint auditado.

A versão é evidência do ambiente auditado, não requisito fixo do Brain.

## Contrato

`brain senior context <task-id>` entrega task, contexto filtrado e o contrato
esperado. `brain senior submit` exige:

- `status: SUCCESS`;
- `summary` não vazio;
- `decision` reconhecida;
- `confidence` entre 0 e 1;
- listas estruturadas para arquivos, módulos, riscos e aprendizado.

Submissões inválidas ou repetidas não avançam a task. Mudança do commit desde a
preparação produz `STALE_CONTEXT`. Aprendizado só é aplicado quando
`approved_for_learning` é verdadeiro.

## Limites atuais

- A presença da extensão não prova autenticação ou disponibilidade da sessão.
- O Codex continua responsável por trabalhar no workspace; o Brain não controla
  a interface.
- Implementação, QA e review ainda precisam ser registrados pelo Codex por meio
  do contrato; a ponte não intercepta automaticamente toda ação da extensão.
- Um MCP/skill dedicado pode substituir os comandos locais no futuro, desde que
  use uma integração oficial e preserve o mesmo contrato.

