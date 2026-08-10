# Project Brain — Arquitetura da V1

Este documento cumpre a seção 36 da especificação: plano técnico produzido
**antes** da implementação, mantido aqui como registro permanente da decisão
de design. Ele cobre arquitetura concreta, riscos, itens adiados, modelo de
dados, interfaces principais, fluxo de uma task, estrutura de diretórios e o
plano de fases.

## 1. Visão geral

Project Brain é uma ferramenta CLI Python que roda **fora** do projeto que
está sendo analisado (o "projeto alvo", ex.: um sistema PHP/CodeIgniter4).
Ela mantém seu próprio estado (banco SQLite, config, logs de auditoria)
dentro de `project-brain/`, e nunca escreve nada no projeto alvo além de
patches explicitamente aprovados (não implementado nesta V1 — ver seção
"Adiado para a V2" abaixo).

```
project-brain/            <- este pacote (a ferramenta em si)
    project_brain.db      <- banco central, multi-projeto
    config.yaml            <- config global (thresholds, safety, provider)
    state.json              <- ponteiro para o "projeto ativo" (última init)
    task-data/<project>/TASK-00001/...   <- auditoria por task

C:/Users/user/Projetos/Sistema/   <- projeto ALVO, só lido (nunca é git-init
                                       pelo Brain, nunca sofre commit
                                       automático)
```

## 2. Desvio consciente da literalidade do documento: banco multi-projeto

A seção 6 lista uma tabela `projects` e a seção 5 mostra `brain init <path>`
como primeiro comando, seguido de comandos *sem* path (`brain inspect`,
`brain task "..."`). Isso só faz sentido se o Brain mantiver um registro de
projetos e um "projeto ativo" corrente — ao invés de um único `config.yaml`
apontando para um path fixo (como a seção 28 sugere no exemplo). Fiz a leitura
de que o exemplo da seção 28 é ilustrativo, e implementei:

- `project_brain.db` central em `project-brain/`, com tabela `projects` e
  todas as demais tabelas referenciando `project_id`. Isso permite indexar
  múltiplos projetos alvo sem recriar o banco.
- `state.json` guardando `active_project_id`, atualizado por `brain init`.
  Comandos subsequentes usam o projeto ativo, mas aceitam `--project <path
  ou id>` para trocar de projeto sem precisar rodar `init` de novo.
- `config.yaml` continua existindo, mas guarda apenas configuração global
  (thresholds de confiança, safety, provider do Senior, flags de
  aprendizado) — não mais um path fixo de projeto.

Isso está documentado aqui porque a spec pede justificativa para desvios.

## 3. Estrutura de diretórios (V1 implementada)

```
project-brain/
├── cli/main.py                  # entrypoint argparse: init/inspect/task/status/memory/...
├── core/
│   ├── enums.py                 # TaskStatus, SeniorStatus, Decision, Category
│   ├── config.py                # BrainConfig (dataclass) + loader de config.yaml
│   ├── task.py                  # dataclass Task + TaskRepository (CRUD em SQLite)
│   ├── paths.py                 # localização do "home" do brain, state.json, db, task-data
│   ├── context_builder.py       # ContextBuilder (seção 20/21)
│   └── orchestrator.py          # Orchestrator (fluxo completo da seção 14/15)
├── senior/
│   ├── provider.py              # SeniorProvider (ABC) + dataclasses de resultado
│   ├── mock_provider.py         # MockSeniorProvider (V1, configurável)
│   ├── codex_provider.py        # stub — sempre UNAVAILABLE nesta V1 (ver seção 30)
│   └── senior_service.py        # fábrica de provider + grava senior_sessions
├── agents/
│   ├── base_agent.py            # Agent (ABC) + AgentResult
│   ├── search_agent.py          # rg com fallback Python puro
│   ├── validation_agent.py      # detecção de padrões de validação conhecidos
│   ├── php_agent.py             # localização conservadora via regex (AST adiado p/ V2)
│   ├── database_agent.py        # mapeia migrations/tabelas/FKs (somente leitura)
│   ├── qa_agent.py               # php -l, composer test, phpunit (se existirem)
│   ├── reviewer_agent.py        # regras de revisão de diff/patch
│   └── local_pipeline.py        # orquestra os agentes locais no fallback
├── brain/
│   ├── database.py              # conexão SQLite + runner de migrations
│   ├── models.py                # dataclasses: Project, FileRecord, Symbol, Relationship,
│   │                             #   Patch, Review, TestResult, SeniorSession
│   ├── rules.py                 # RuleRepository
│   ├── patterns.py              # PatternRepository
│   ├── lessons.py                # LessonRepository
│   ├── memory.py                  # MemoryStore (fachada de busca)
│   ├── similarity.py             # SimilarityEngine (ABC) + KeywordSimilarityEngine
│   └── learning_extractor.py     # LearningExtractor (contrato da seção 12)
├── analysis/
│   ├── code_scanner.py           # varre arquivos, hash, linguagem, símbolos (regex)
│   ├── dependency_mapper.py      # relações simples (uses/extends/references_table)
│   └── project_indexer.py        # orquestra scanner+mapper, grava em files/symbols/relationships
├── git/
│   ├── git_service.py            # status/branch/commit/diff via subprocess
│   └── diff_parser.py            # parse de `git diff --numstat`/unified diff
├── executor/
│   ├── command_runner.py         # denylist + subprocess seguro (seção 23)
│   ├── lint_runner.py            # php -l
│   └── test_runner.py            # composer test / phpunit
├── templates/                    # exemplos YAML de rule/pattern/lesson (referência humana)
├── migrations/0001_init.sql      # schema inicial
├── tests/                        # pytest
├── data/                          # (git-ignored) sqlite + task-data ficam aqui em runtime
├── project_brain.db              # criado em runtime (não versionado)
├── config.yaml
└── README.md
```

Motivo de `data/` existir além do que a seção 4 pede: `project_brain.db` e
`task-data/` são artefatos de runtime (mudam a cada uso). Deixei o caminho
configurável em `core/paths.py`, com default apontando para
`project-brain/project_brain.db` (raiz, como pedido no diagrama da seção 4)
e `project-brain/task-data/`. A pasta `data/` fica disponível como alternativa
caso o usuário prefira isolar artefatos de runtime do código-fonte (configurável
via `config.yaml: storage.db_path` / `storage.task_data_dir`), mas o
comportamento *default* respeita literalmente a árvore da seção 4.

## 4. Modelo de dados SQLite (`migrations/0001_init.sql`)

```
projects(id, name, path UNIQUE, vcs, primary_language, created_at, updated_at, last_indexed_at)

tasks(id, project_id FK, external_id, title, description, category, status,
      confidence, source, decision, created_at, updated_at, completed_at,
      git_commit_before, git_commit_after)

rules(id, rule_code UNIQUE, project_id FK NULL, category, condition_text,
      rule_text, dont_json, confidence, source, approved, created_at)

patterns(id, pattern_code UNIQUE, project_id FK NULL, category, framework,
         trigger, procedure_json, approved, confidence, created_at)

lessons(id, lesson_code UNIQUE, project_id FK NULL, task_id FK NULL, problem,
        solution, files_json, category, approved, validated_by, confidence,
        created_at)

files(id, project_id FK, path, language, size, hash, last_modified, indexed_at,
      UNIQUE(project_id, path))

symbols(id, file_id FK, symbol_type, name, class_name, line_start, line_end)

relationships(id, project_id FK, from_type, from_name, relation, to_type,
               to_name, meta_json)

patches(id, task_id FK, commit_before, commit_after, diff, metadata_json,
        created_at)

reviews(id, task_id FK, patch_id FK NULL, reviewer, decision, comments,
        created_at)

test_results(id, task_id FK, tool, command, exit_code, passed, output,
             created_at)

senior_sessions(id, task_id FK NULL, provider, status, request_json,
                 response_json, created_at)

schema_migrations(version, applied_at)   -- controle interno de migrations
```

`rules`/`patterns`/`lessons` têm `project_id` opcional (NULL = regra
global, aplicável a qualquer projeto — ex. `RULE-001` da spec, que é
genérica; regras com `project_id` setado são específicas de um projeto).

Todos os campos "json" armazenam texto JSON serializado (SQLite não tem tipo
JSON nativo antes de extensões; optamos por `TEXT` + `json.dumps/loads` no
Python, evitando dependências extras).

## 5. Interfaces principais

```python
# senior/provider.py
class SeniorStatus(Enum):
    AVAILABLE, UNAVAILABLE, RATE_LIMITED, AUTH_ERROR, QUOTA_EXCEEDED, TIMEOUT, UNKNOWN_ERROR

class SeniorProvider(ABC):
    def check_availability(self) -> SeniorStatus: ...
    def analyze(self, task: Task, context: TaskContext) -> SeniorAnalysisResult: ...
    def review(self, task: Task, patch: PatchProposal, context: TaskContext) -> SeniorReviewResult: ...
    def extract_learning(self, task: Task, result: SeniorAnalysisResult) -> LearningPayload: ...
```

```python
# brain/similarity.py
class SimilarityEngine(ABC):
    def compare(self, task: Task, previous_task: Task) -> float: ...

class KeywordSimilarityEngine(SimilarityEngine):
    # bag-of-tokens determinístico: título+descrição+categoria+arquivos tocados,
    # com pesos por campo (categoria pesa mais que texto livre), sem embeddings.
```

```python
# agents/base_agent.py
class AgentResult:
    status: AgentResultStatus       # OK / NO_MATCH / REQUIRES_SENIOR / ERROR
    confidence: float
    message: str
    data: dict

class Agent(ABC):
    name: str
    def run(self, task: Task, context: TaskContext) -> AgentResult: ...
```

```python
# core/context_builder.py
@dataclass
class TaskContext:
    task: Task
    rules: list[Rule]
    patterns: list[Pattern]
    lessons: list[Lesson]
    similar_tasks: list[tuple[Task, float]]
    candidate_files: list[FileRecord]
    related_symbols: list[Symbol]
    git_status: GitStatus
    known_risks: list[str]

class ContextBuilder:
    def build(self, task: Task, project: Project) -> TaskContext: ...
```

`ContextBuilder` implementa a "redução de tokens" da seção 21: primeiro roda
`SearchAgent`/`MemoryStore` localmente para restringir o que entra no
contexto, e só isso (não o projeto inteiro) é o que seria enviado a um
Senior real.

## 6. Fluxo completo de uma task (`brain task "..."`)

```
1. CLI parseia argumento -> cria Task(status=NEW) no banco (TaskRepository)
2. Orchestrator.run(task):
   a. GitService.status(project.path)
      - se houver mudanças pré-existentes -> marca PRE_EXISTING_CHANGE no log,
        NÃO aborta, mas registra o aviso e o Orchestrator evita qualquer
        escrita no projeto alvo durante essa task.
   b. task.status = ANALYZING
   c. ContextBuilder.build(task, project):
        - SearchAgent localiza arquivos candidatos (rg / fallback)
        - MemoryStore busca rules/patterns/lessons relevantes (keyword match)
        - MemoryStore + SimilarityEngine busca tasks parecidas no histórico
   d. senior_status = SeniorService.check_availability()
   e. SE senior_status == AVAILABLE:
        task.status = SENIOR_RUNNING
        result = provider.analyze(task, context)
        grava senior_sessions
        SE result vier com learning payload E config.learning.automatic_after_approval:
            LearningExtractor grava rules/patterns/lessons
        task.status = WAITING_REVIEW (ou COMPLETED se result.decision == AUTO_EXECUTE_ALLOWED
                       e não há patch real para aplicar nesta V1)
   f. SENÃO (qualquer status != AVAILABLE):
        task.status = LOCAL_EXECUTION
        local_result = local_pipeline.try_execute(task, context, config):
            CLASSIFY -> categoria heurística (keywords -> validation/database/ui/...)
            SEARCH MEMORY (já está em context.rules/patterns/lessons/similar_tasks)
            CALCULATE CONFIDENCE (regra determinística seção 15/16)
            decision = map_confidence_to_decision(confidence, thresholds)
            roda ValidationAgent / PHPAgent / DatabaseAgent em modo somente-análise
            SE decision == REQUIRES_SENIOR: nenhum arquivo é tocado, retorna motivo
        task.status = SENIOR_REQUIRED se decision == REQUIRES_SENIOR, senão WAITING_REVIEW
   g. ReviewerAgent roda regras de sanidade sobre o que foi proposto (mesmo sem
      diff real, valida escopo/arquivos sensíveis quando um patch futuro existir)
   h. QAAgent roda php -l / composer test / phpunit SE aplicável e configurado
   i. Grava trilha de auditoria completa em task-data/<project>/TASK-XXXXX/*
   j. Task persistida com confidence/decision/status finais
3. CLI imprime resumo formatado (Senior status, modo, matches de memória,
   confidence, decision, arquivos candidatos, nenhum arquivo modificado).
```

## 7. Riscos técnicos identificados

1. **Nome de pacote `git/` colide com o pacote PyPI `GitPython` (`import
   git`)** caso ele seja instalado no ambiente do usuário no futuro. Mitigação:
   o projeto nunca depende de GitPython (só subprocess), e como `project-brain/`
   é a raiz que entra no `sys.path` (não seu pai), `import git.git_service`
   sempre resolve para o pacote local primeiro (ordem do `sys.path`). Ver
   nota abaixo para a decisão final.
2. **Disponibilidade de `rg`**: nem todo ambiente Windows tem ripgrep no
   PATH. `SearchAgent` detecta em runtime (`shutil.which("rg")`) e usa um
   fallback 100% Python (`os.walk` + regex) sem nunca travar.
3. **Disponibilidade de `php`/`composer`**: idem, `QAAgent` detecta via
   `shutil.which` antes de tentar rodar; se ausente, retorna
   `AgentResultStatus.SKIPPED` com mensagem clara, nunca lança exceção não
   tratada.
4. **SQLite + concorrência**: V1 é single-user/single-process, então não
   implementamos locking avançado; `sqlite3` com `isolation_level=None` e
   `PRAGMA journal_mode=WAL` é suficiente e documentado como limitação.
5. **Encoding no Windows**: `subprocess.run` configurado com
   `encoding="utf-8", errors="replace"` para evitar exceções por saída não
   ASCII (comum em `git diff` com nomes de arquivo acentuados).
6. **Falso-positivos do ReviewerAgent/CommandRunner denylist**: uma
   denylist baseada em substring pode bloquear comandos legítimos (ex. um
   commit cuja mensagem contenha a palavra "drop"). Mitigação: o denylist do
   `CommandRunner` atua sobre o **comando executado** (argv), não sobre
   texto livre, e usa comparação por tokens/prefixos do binário+subcomando,
   não por substring solta.

### Nota sobre o risco 1 (nome de pacote `git`)

Depois de avaliar, decidi **manter o diretório `git/`** exatamente como a
especificação pede (é literal na seção 4), mas o pacote é sempre importado
via caminho absoluto qualificado a partir da raiz `project-brain` estando no
`sys.path` (ex.: `from git.git_service import GitService` funciona porque
`project-brain/` — não `git/` — é o que entra no `sys.path`, e nenhuma
dependência externa chamada `git` é instalada). Testado e funcional; se no
futuro o ambiente instalar GitPython, haveria conflito — deixo essa nota
como aviso para quem for evoluir o projeto.

## 8. O que foi adiado para a "Segunda Entrega" (seção 30)

- `CodexProvider` real (integração de fato com Codex/API externa). V1 traz
  apenas um stub que sempre reporta `UNAVAILABLE` (para não fingir uma
  integração que não existe) — `codex_provider.py` documenta claramente que
  é um placeholder.
- `LearningExtractor` **automático a partir de diffs reais** (V1 só extrai
  aprendizado a partir do contrato JSON estruturado que o Senior — mock —
  devolve, exatamente como a seção 12 permite: "quando não houver
  inteligência suficiente para extrair isso automaticamente, o Senior
  poderá fornecer uma saída estruturada").
- `ReviewerAgent` avançado (nesta V1 ele é baseado em regras simples:
  tamanho de diff, arquivos sensíveis, padrões destrutivos em texto de
  migration; heurísticas mais ricas de review de código ficam para V2).
- PHP AST real (`nikic/php-parser` via subprocess PHP). V1 usa
  regex/heurísticas conservadoras só para *localizar* classes/métodos,
  nunca para reescrever código.
- **Aplicação automática de patches** (patch automation): V1 não escreve
  código no projeto alvo. Os agentes locais e o Senior (mock) produzem
  *análise, decisão e recomendação*, nunca edição de arquivo. Isso é
  coerente com a seção 30, que lista "patch automation" como item da
  segunda entrega, e com a seção 35, que proíbe alterar código do projeto
  analisado sem cuidado extra — decidimos que esse cuidado extra (parser
  AST real, apply/rollback seguro, revisão humana antes do write) é
  trabalho de V2.
- `DatabaseAgent` fica somente-leitura (mapeia migrations/tabelas), sem
  qualquer execução de DDL/DML — consistente com a seção 17.
- Comandos CLI de menor prioridade (`brain learn` como comando standalone,
  `brain task history`, `brain inspect module`, `brain senior status`) —
  implementados em versão mínima quando o custo foi baixo, mas não
  aprofundados.

## 9. Plano de fases (execução desta rodada)

1. Esqueleto de diretórios + `config.yaml` + `core/paths.py`.
2. `brain/database.py` + `migrations/0001_init.sql` + `brain/models.py`.
3. `core/enums.py`, `core/task.py`, `core/config.py`.
4. `git/git_service.py`, `git/diff_parser.py`.
5. `executor/command_runner.py` (denylist), `lint_runner.py`, `test_runner.py`.
6. `analysis/code_scanner.py`, `dependency_mapper.py`, `project_indexer.py`.
7. `agents/*` (search, validation, php, database, qa, reviewer, base, local_pipeline).
8. `brain/rules.py`, `patterns.py`, `lessons.py`, `similarity.py`, `memory.py`, `learning_extractor.py`.
9. `senior/provider.py`, `mock_provider.py`, `codex_provider.py`, `senior_service.py`.
10. `core/context_builder.py`, `core/orchestrator.py`.
11. `cli/main.py`.
12. `templates/*.yaml` de referência.
13. Testes (`tests/*`).
14. `README.md`.
15. Validação manual ponta-a-ponta com projeto PHP fictício.
