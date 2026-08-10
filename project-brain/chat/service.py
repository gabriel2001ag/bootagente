from __future__ import annotations

import dataclasses
import json
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from brain.models import Project
from core.concepts import ConceptExpander
from core.context_compressor import ContextCompressor
from core.enums import RoutingMode
from core.nlp import DOMAIN_TRIGGER_WORDS, PortugueseNLP, Understanding
from core.orchestrator import Orchestrator, TaskRunSummary
from core.paths import BrainPaths
from core.text_normalizer import PortugueseTextNormalizer
from brain.database import Database
from core.config import BrainConfig
from chat.sessions import ChatSession, ChatSessionRepository
from chat.response_formatter import NaturalResponseFormatter
from senior.codex_workspace_bridge import CodexWorkspaceBridge
from senior.gateway import VSCodeCodexInvertedGateway
from chat.classifier import ChatMessageCategory, ChatMessageClassifier

_CONTINUATION_MARKERS = {"e", "isso", "esse", "essa", "ele", "ela", "tambem", "disso"}


@dataclass
class ChatReply:
    text: str
    task_id: int | None = None
    exit_requested: bool = False


class ChatService:
    """Thin chat layer over normal tasks, memory retrieval and the orchestrator."""

    HELP = (
        "/help /status /project /memory <query> /task /tasks /pending "
        "/offline /online /context /verbose <on|off> /exit"
    )

    def __init__(
        self, db: Database, config: BrainConfig, paths: BrainPaths, project: Project
    ):
        self.db = db
        self.config = config
        self.paths = paths
        self.project = project
        self.sessions = ChatSessionRepository(db)
        self.session: ChatSession = self.sessions.create(project.id)
        self.last_summary: TaskRunSummary | None = None
        expander = ConceptExpander(
            config.concepts.groups, config.concepts.aliases, config.concepts.relationships
        )
        normalizer = PortugueseTextNormalizer(config.language.replacements)
        self.nlp = PortugueseNLP(expander, normalizer, config.language.actions)
        self.message_classifier = ChatMessageClassifier(self.nlp)
        # Chat-turn-scoped only (seção 7/28) — never written to the Brain's
        # persistent memory, and reset whenever a new ChatService is built.
        self.last_understanding: Understanding | None = None
        # Defaults OFF: normal mode is the natural-language explanation;
        # `/verbose on` reveals the raw Route:/Decision:/session-id block
        # for auditing (seção 17/18).
        self.verbose = False

    def handle(self, message: str) -> ChatReply:
        if self.sessions.get(self.session.id).status != "ACTIVE":
            raise RuntimeError("chat session is closed")
        message = message.strip()
        if not message:
            return ChatReply("")
        self.sessions.add_message(self.session.id, "user", message)
        if message.startswith("/"):
            reply = self._handle_command(message)
        else:
            category = self.message_classifier.classify(message)
            if category in {ChatMessageCategory.GREETING, ChatMessageCategory.CASUAL_CHAT}:
                reply = self._handle_casual(category)
            elif category == ChatMessageCategory.STATUS_QUERY:
                reply = self._handle_command("/status")
            elif category == ChatMessageCategory.MEMORY_QUERY:
                reply = self._memory(message)
            elif category == ChatMessageCategory.SELF_QUERY:
                reply = self._handle_self_query()
            else:
                reply = self._handle_request(message)
        if not reply.exit_requested:
            self.sessions.add_message(
                self.session.id, "assistant", reply.text, task_id=reply.task_id
            )
        return reply

    def _handle_casual(self, category: ChatMessageCategory) -> ChatReply:
        prefix = "Olá!" if category == ChatMessageCategory.GREETING else "Tudo bem por aqui!"
        senior = (
            "Codex VS Code"
            if self.session.senior_mode == "ONLINE"
            else "UNAVAILABLE (modo local)"
        )
        return ChatReply(
            f"{prefix} Project Brain ativo.\n"
            f"Projeto: {self.project.name}\n"
            f"Senior: {senior}\n\n"
            "Como posso ajudar?"
        )

    def _handle_self_query(self) -> ChatReply:
        scoped = "(project_id IS NULL OR project_id = ?)"
        counts = {
            table: self.db.query_one(
                f"SELECT COUNT(*) n FROM {table} WHERE approved=1 AND {scoped}",
                (self.project.id,),
            )["n"]
            for table in ("rules", "patterns", "lessons")
        }
        task_counts = self.db.query_one(
            "SELECT COUNT(*) total, "
            "SUM(CASE WHEN status='SENIOR_REQUIRED' THEN 1 ELSE 0 END) pending "
            "FROM tasks WHERE project_id=?",
            (self.project.id,),
        )
        provider = self.config.senior.provider if self.config.senior.enabled else "disabled"
        knowledge_summary = (
            f"{counts['rules']} regras, {counts['patterns']} padrões, {counts['lessons']} lições"
        )
        natural = (
            "Eu sou o Project Brain, a memória técnica do seu ERP.\n\n"
            "Minha função é lembrar o que já foi analisado e aprovado no projeto para "
            "evitar que o Codex precise descobrir tudo de novo a cada tarefa.\n\n"
            "Quando você me pede alguma coisa, primeiro verifico o que já sei.\n\n"
            "Se eu tiver conhecimento suficiente, posso analisar usando minha memória "
            "e as ferramentas locais.\n\n"
            "Se ainda faltar conhecimento, preparo apenas o contexto necessário para o "
            "Codex Senior analisar. Depois que a solução é validada, o novo aprendizado "
            "pode ser armazenado para uso futuro.\n\n"
            "Estado atual:\n"
            f"- Projeto: {self.project.name}\n"
            f"- Modo: {self.session.senior_mode}\n"
            f"- Conhecimento salvo: {knowledge_summary}\n"
            f"- Tasks registradas: {task_counts['total']}\n"
            f"- Aguardando Senior: {task_counts['pending'] or 0}"
        )
        if not self.verbose:
            return ChatReply(natural)
        if provider.lower() == "codex-vscode":
            senior_description = (
                "Codex no VS Code por handoff invertido/manual; ONLINE indica a preferência "
                "da sessão, e a disponibilidade é verificada por tarefa."
            )
        else:
            senior_description = (
                f"Provider {provider}; o modo da sessão não comprova disponibilidade externa."
            )
        last_task = self.last_summary.task.id if self.last_summary else "(none)"
        technical = (
            f"Projeto: {self.project.name} ({self.project.path})\n"
            f"Senior configurado: {provider}\n"
            f"Sessão: {self.session.id} ({self.session.senior_mode})\n"
            f"Fluxo Senior: {senior_description}\n"
            f"Última task desta sessão: {last_task}"
        )
        return ChatReply(
            f"{natural}\n\n--- detalhes técnicos (/verbose off para ocultar) ---\n{technical}"
        )

    def _handle_command(self, message: str) -> ChatReply:
        command, _, argument = message.partition(" ")
        command = command.lower()
        if command == "/help":
            return ChatReply(self.HELP)
        if command == "/status":
            return ChatReply(
                f"Project: {self.project.name}\n"
                f"Session: {self.session.id} ({self.session.senior_mode})\n"
                f"Last task: {self.last_summary.task.id if self.last_summary else '(none)'}"
            )
        if command == "/project":
            return ChatReply(f"Project: {self.project.name} ({self.project.path})")
        if command == "/memory":
            return self._memory(argument)
        if command in {"/task", "/context"}:
            return self._last_context()
        if command == "/tasks":
            rows = self.db.query(
                "SELECT id,status,title FROM tasks WHERE project_id=? ORDER BY id DESC LIMIT 10",
                (self.project.id,),
            )
            return ChatReply("\n".join(f"#{r['id']} [{r['status']}] {r['title']}" for r in rows) or "No tasks.")
        if command == "/pending":
            rows = self.db.query(
                "SELECT id,title FROM tasks WHERE project_id=? AND status='SENIOR_REQUIRED'"
                " ORDER BY id",
                (self.project.id,),
            )
            return ChatReply("\n".join(f"#{r['id']} {r['title']}" for r in rows) or "No pending tasks.")
        if command == "/verbose":
            arg = argument.strip().lower()
            if arg not in {"on", "off"}:
                return ChatReply("Usage: /verbose <on|off>")
            self.verbose = arg == "on"
            return ChatReply(f"Verbose: {'ON' if self.verbose else 'OFF'}")
        if command == "/offline":
            self.session = self.sessions.set_senior_mode(self.session.id, "OFFLINE")
            return ChatReply("Senior: UNAVAILABLE\nMode: LOCAL FALLBACK")
        if command == "/online":
            self.session = self.sessions.set_senior_mode(self.session.id, "ONLINE")
            return ChatReply("Senior mode: ONLINE (availability is verified per task)")
        if command == "/exit":
            self.sessions.close(self.session.id)
            return ChatReply("Session closed.", exit_requested=True)
        return ChatReply(f"Unknown command: {command}. Use /help.")

    def _handle_request(self, message: str) -> ChatReply:
        config = deepcopy(self.config)
        if self.session.senior_mode == "OFFLINE":
            config.senior.provider = "mock"
            config.senior.mock_availability = "UNAVAILABLE"
        understanding = self.nlp.interpret(message)
        display_understanding = self._resolve_conversational_context(understanding)
        description = display_understanding.normalized_text
        if display_understanding is not understanding:
            trigger_words = " ".join(
                DOMAIN_TRIGGER_WORDS[c] for c in display_understanding.concepts if c in DOMAIN_TRIGGER_WORDS
            )
            description = f"{understanding.normalized_text} {trigger_words}".strip()
        summary = Orchestrator(self.db, config, self.paths, self.project).run_task(
            message, description=description, source="chat"
        )
        self.last_summary = summary
        self.last_understanding = display_understanding
        compressed = ContextCompressor(
            max_rules=config.retrieval.rules_limit,
            max_patterns=config.retrieval.patterns_limit,
            max_lessons=config.retrieval.lessons_limit,
            max_similar_tasks=config.retrieval.similar_tasks_limit,
        ).compress(summary.context)
        metrics_path = summary.audit_dir / "chat-metrics.json"
        metrics_path.write_text(
            json.dumps(dataclasses.asdict(compressed.metrics), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        self._record_usage(summary)
        route = self._route(summary)
        handoff = ""
        if (
            summary.task.status == "SENIOR_REQUIRED"
            and config.senior.provider.lower() == "codex-vscode"
        ):
            descriptor = VSCodeCodexInvertedGateway(
                CodexWorkspaceBridge(self.db, self.paths, config)
            ).prepare(summary.task)
            if descriptor.ready:
                handoff = f"\nSenior handoff ready: {descriptor.instruction}"
        technical_block = (
            "Memory lookup:\n"
            f"Rules: {len(summary.context.rules)}\n"
            f"Patterns: {len(summary.context.patterns)}\n"
            f"Lessons: {len(summary.context.lessons)}\n"
            f"Similar tasks: {len(summary.context.similar_tasks)}\n"
            f"Concepts: {', '.join(self._concepts(summary)) or '(none)'}\n\n"
            "Code lookup:\n"
            f"Relevant files: {len(summary.context.candidate_files)}\n\n"
            f"Task #{summary.task.id}\n"
            f"Category: {summary.category}\n"
            f"Confidence: {summary.confidence:.4f}\n"
            f"Route: {route}\n"
            f"Decision: {summary.decision.value}\n"
            f"{summary.message}\n"
            f"Context reduction (estimated by characters): "
            f"{compressed.metrics.estimated_context_reduction_percent:.2f}%"
            f"{handoff}"
        )
        # Verbose defaults ON: the technical block above is what the existing
        # test suite (and any script depending on raw Route:/Category: text)
        # asserts on. The natural-language explanation is prepended so it is
        # what a human reads first; `/verbose off` hides the technical block
        # for a purely conversational session (seção 17/18).
        text = NaturalResponseFormatter.format(
            summary, display_understanding, route, technical_block, self.verbose
        )
        return ChatReply(text, task_id=summary.task.id)

    def _resolve_conversational_context(self, understanding: Understanding) -> Understanding:
        """Follow-up inheritance (seção 7/28): a short continuation like
        "e o que falta?" borrows the previous turn's concepts/domain. Purely
        in-memory for this session — never written to persistent memory."""
        normalized_tokens = understanding.normalized_text.split()
        is_continuation = bool(normalized_tokens) and normalized_tokens[0] in _CONTINUATION_MARKERS
        if not is_continuation or not self.last_understanding or not self.last_understanding.concepts:
            return understanding
        merged_concepts = tuple(sorted(set(understanding.concepts) | set(self.last_understanding.concepts)))
        domain = understanding.domain or self.last_understanding.domain
        return dataclasses.replace(understanding, concepts=merged_concepts, domain=domain)

    def _record_usage(self, summary: TaskRunSummary) -> None:
        now = summary.task.updated_at
        for kind, items, attr in (
            ("rule", summary.context.rules, "rule_code"),
            ("pattern", summary.context.patterns, "pattern_code"),
            ("lesson", summary.context.lessons, "lesson_code"),
        ):
            for item in items:
                self.db.execute(
                    "INSERT INTO knowledge_usage(project_id,task_id,knowledge_type,"
                    "knowledge_code,result,created_at) VALUES (?,?,?,?,?,?)",
                    (self.project.id, summary.task.id, kind, getattr(item, attr), "SELECTED", now),
                )
                table = {"rule": "rules", "pattern": "patterns", "lesson": "lessons"}[kind]
                code_column = {
                    "rule": "rule_code", "pattern": "pattern_code", "lesson": "lesson_code"
                }[kind]
                self.db.execute(
                    f"UPDATE {table} SET times_used=times_used+1 WHERE {code_column}=?",
                    (getattr(item, attr),),
                )

    def _memory(self, query: str) -> ChatReply:
        if not query.strip():
            return ChatReply("Usage: /memory <query>")
        from core.task import Task

        orchestrator = Orchestrator(self.db, self.config, self.paths, self.project)
        probe = Task(id=-1, project_id=self.project.id, title=query, description="", source="chat")
        context = orchestrator.context_builder.build(probe, self.project.id)
        return ChatReply(
            f"Rules: {', '.join(x.rule_code for x in context.rules) or '(none)'}\n"
            f"Patterns: {', '.join(x.pattern_code for x in context.patterns) or '(none)'}\n"
            f"Lessons: {', '.join(x.lesson_code for x in context.lessons) or '(none)'}\n"
            f"Similar tasks: {', '.join(str(x.task.id) for x in context.similar_tasks) or '(none)'}"
        )

    def _last_context(self) -> ChatReply:
        if not self.last_summary:
            return ChatReply("No task in this session.")
        return ChatReply(self.last_summary.context.summary(), self.last_summary.task.id)

    @staticmethod
    def _route(summary: TaskRunSummary) -> str:
        if summary.local_result:
            return summary.local_result.signals.get("route", {}).get("mode", summary.mode.value)
        return RoutingMode.SENIOR.value

    @staticmethod
    def _concepts(summary: TaskRunSummary) -> list[str]:
        if not summary.local_result:
            return []
        return summary.local_result.signals.get("classification", {}).get("concepts", [])


def run_interactive_chat(
    service: ChatService,
    input_fn: Callable[[str], str] = input,
    output_fn: Callable[[str], None] = print,
) -> None:
    output_fn("Project Brain")
    output_fn(f"Project: {service.project.name}")
    output_fn(f"Senior mode: {service.session.senior_mode}")
    output_fn("Digite /help para comandos.")
    while True:
        try:
            message = input_fn("> ")
        except (EOFError, KeyboardInterrupt):
            message = "/exit"
        reply = service.handle(message)
        if reply.text:
            output_fn(reply.text)
        if reply.exit_requested:
            return
