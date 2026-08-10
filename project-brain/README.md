# Project Brain

Project Brain é uma ferramenta local para analisar projetos, guardar conhecimento
estruturado e trabalhar com o Codex no VS Code e agentes determinísticos. A V1 não
usa LLM local, GPU, embeddings ou banco vetorial, e não altera o código do
projeto analisado.

## Requisitos

- Python 3.11 ou superior (3.12+ recomendado)
- Git
- `rg` (ripgrep) opcional; há fallback em Python
- PHP/Composer opcionais para validações de projetos PHP

## Instalação

No diretório `project-brain`:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

A CLI pode ser executada sem instalação de pacote:

```powershell
python -m cli.main --help
```

## Uso rápido

Registre e indexe um projeto alvo:

```powershell
python -m cli.main init C:\caminho\do\projeto
```

Use o projeto ativo nos comandos seguintes:

```powershell
python -m cli.main inspect
python -m cli.main status
python -m cli.main task "Limitar a impressão para no máximo 50 pedidos"
python -m cli.main task history
python -m cli.main memory search "pedido"
python -m cli.main inspect file app\Controllers\Pedido.php
python -m cli.main inspect module pedido
python -m cli.main senior status
python -m cli.main learn
```

Use `--project <id-ou-caminho>` nos comandos que oferecem essa opção para
selecionar outro projeto registrado.

## Codex no VS Code

O Senior oficial é o Codex usado normalmente dentro do VS Code. O Brain não
chama API OpenAI, Codex CLI, comandos internos da extensão ou automação visual.
A integração é invertida e assíncrona:

```text
Brain prepara contexto → Codex consulta → Codex trabalha → Codex submete JSON → Brain aprende
```

```powershell
python -m cli.main task "Adicionar validação X"
python -m cli.main senior pending
python -m cli.main senior context 1
python -m cli.main senior submit 1 --file resultado-codex.json
```

`approved_for_learning` precisa ser `true` para persistir conhecimento.
Respostas inválidas, repetidas ou preparadas sobre um commit Git antigo são
recusadas. `senior status` detecta o manifesto da extensão, sem afirmar que
uma sessão esteja autenticada:

```powershell
python -m cli.main senior status
```

## Mock e modo offline

O `MockSeniorProvider` continua disponível somente para testes. Configure
`senior.provider: mock` e ajuste
`senior.mock_availability` para um dos estados suportados:

```text
AVAILABLE
UNAVAILABLE
RATE_LIMITED
AUTH_ERROR
QUOTA_EXCEEDED
TIMEOUT
UNKNOWN_ERROR
```

Quando o Senior está indisponível, o orquestrador consulta regras, padrões,
lições e tarefas similares. A confiança determina uma destas decisões:

```text
AUTO_EXECUTE_ALLOWED
PATCH_REQUIRES_REVIEW
ANALYSIS_ONLY
REQUIRES_SENIOR
```

Apesar do nome `AUTO_EXECUTE_ALLOWED`, ele não autoriza controlar o VS Code ou
executar uma integração externa.

## Dados e auditoria

Na primeira execução, o sistema cria o banco SQLite e aplica
`migrations/0001_init.sql`. O projeto ativo fica em `state.json`, e cada task
gera evidências em `task-data/`, incluindo contexto, decisão, comandos, testes
e revisão. Esses artefatos são locais e não devem ser versionados.

O projeto alvo precisa ser um repositório Git quando `git.required` estiver
habilitado. Mudanças preexistentes são registradas e preservadas.

O `CommandRunner` bloqueia comandos destrutivos. A V1 não executa deploy,
commit automático, alteração destrutiva de banco ou escrita automática no
projeto alvo.

## Testes

```powershell
python -m pytest -q
```

A suíte cobre banco e migrations, indexação, busca, memória, similaridade,
providers, fallback, Git, denylist, QA e CLI.

## Arquitetura e limites

As decisões técnicas anteriores estão em [ARCHITECTURE.md](ARCHITECTURE.md) e
[V2_ARCHITECTURE.md](V2_ARCHITECTURE.md).

## V3: Brain Chat

A V3 adiciona Chat, recuperação conceitual e roteamento inteligente como
camadas sobre as tasks e o `Orchestrator` existentes. Cada solicitação em texto
livre cria uma task normal e preserva a mesma auditoria, QA, segurança Git,
proteção de arquivos sensíveis e handoff Senior.

```powershell
python -m cli.main chat
```

Comandos da sessão:

```text
/help
/status
/project
/memory <consulta>
/task
/tasks
/pending
/offline
/online
/context
/exit
```

O resultado mostra rules, patterns, lessons, tarefas similares, conceitos,
arquivos relevantes, categoria, confiança, rota, decisão e redução estimada de
contexto. As sessões e mensagens são persistidas separadamente do conhecimento.

O roteamento é determinístico:

- `ANALYSIS_ONLY`: análise com confiança local a partir de `0.40`;
- `LOCAL`: evidência forte (`>= 0.80`) e Senior indisponível;
- `HYBRID`: evidência forte (`>= 0.80`) e Senior disponível;
- `SENIOR`: confiança inferior e Senior disponível;
- `WAITING_FOR_SENIOR`: confiança inferior e Senior indisponível.

O `ConfidenceEngine` combina similaridade (30%), rules (15%), patterns (15%),
lessons (15%), validação (15%) e conceitos (10%). `/offline` força a verificação
do fallback: havendo evidência suficiente, o Brain entrega análise local;
caso contrário, exige Senior sem inventar conhecimento.

Desabilitar `fallback.enabled` impede análise autônoma quando o Senior automático
está indisponível. O handoff invertido `codex-vscode` continua consultando a
memória de forma read-only antes de preparar o contexto, pois o Brain sempre deve
ser consultado antes do Codex.

O baseline anterior à correção do pré-router era `119 passed`; a validação final
registrou `132 passed`. O caso real recuperou 3 rules, 2 patterns, 2 lessons e 1 task
similar, com confiança `0.73`, `ANALYSIS_ONLY` offline e redução estimada de
contexto de `11.11%` por caracteres.

### Pré-router conversacional

Antes da recuperação técnica, `ChatMessageClassifier` classifica a mensagem em:
`GREETING`, `CASUAL_CHAT`, `COMMAND`, `STATUS_QUERY`, `MEMORY_QUERY`,
`CODE_QUESTION`, `ANALYSIS_TASK`, `IMPLEMENTATION_TASK` ou `UNKNOWN`.
Intenção técnica tem precedência quando uma saudação aparece junto de pedido de
análise, implementação ou código.

Saudações e conversa casual recebem resposta local imediata. Consultas naturais
de status e memória usam handlers locais. Esses caminhos não criam task, não
consultam memória/código, não executam router ou handoff e não geram auditoria
ou uso de conhecimento. Antes da correção, `ola` criou a Task 5,
`unknown/0.08/SENIOR`, handoff e 15 arquivos candidatos; depois, a mesma entrada
teve resposta local e delta de tasks igual a zero.

Os filtros mínimos configurados para recuperação são: rule `0.20`, pattern
`0.20`, lesson `0.10`, task similar `0.10` e código `0.20`. A classificação de
status é deliberadamente conservadora por lista explícita; paráfrases ainda não
reconhecidas seguem o pipeline técnico para evitar que uma pergunta funcional,
como status de NF-e, seja confundida com status do Brain.

O mapa de reuso, fórmula, gateway e limites estão em
[V3_ARCHITECTURE.md](V3_ARCHITECTURE.md).
