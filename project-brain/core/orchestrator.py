"""Orchestrator: the full task flow (seções 14/15/26/27).

    task = parse_task()
    context = build_context(task)
    if senior.available():
        result = senior.analyze(task, context)
    else:
        result = local_agents.try_execute(task, context)

V1 never writes to the target project (see ARCHITECTURE.md — patch
automation is a V2 feature). Every run produces a full audit trail under
`task-data/<project>/TASK-XXXXX/`.
"""
from __future__ import annotations

import dataclasses
import json
import shutil
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from agents.local_pipeline import LocalExecutionResult, try_execute
from agents.qa_agent import QAAgent
from brain.database import Database
from brain.learning_extractor import LearningExtractor
from brain.memory import MemoryStore
from brain.models import Project
from brain.similarity import KeywordSimilarityEngine
from core.concepts import ConceptExpander
from core.config import BrainConfig
from core.context_builder import ContextBuilder, TaskContext
from core.enums import Decision, ExecutionMode, RoutingMode, SeniorStatus, TaskStatus
from core.routing import Classification, SmartRouter
from core.paths import BrainPaths, slugify
from core.task import Task, TaskRepository
from senior.senior_service import SeniorService


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _json_default(obj: Any) -> Any:
    if hasattr(obj, "value") and isinstance(getattr(obj, "value"), (str, int)):
        return obj.value
    if dataclasses.is_dataclass(obj):
        return dataclasses.asdict(obj)
    return str(obj)


@dataclass
class TaskRunSummary:
    task: Task
    mode: ExecutionMode
    senior_status: SeniorStatus
    decision: Decision
    confidence: float
    category: str
    message: str
    context: TaskContext
    audit_dir: Path
    local_result: LocalExecutionResult | None = None
    warnings: list[str] = field(default_factory=list)


class Orchestrator:
    def __init__(self, db: Database, config: BrainConfig, paths: BrainPaths, project: Project):
        self.db = db
        self.config = config
        self.paths = paths
        self.project = project
        self.task_repo = TaskRepository(db)
        expander = ConceptExpander(
            config.concepts.groups, config.concepts.aliases, config.concepts.relationships
        )
        self.memory = MemoryStore(
            db, KeywordSimilarityEngine(concept_expander=expander), concept_expander=expander
        )
        self.context_builder = ContextBuilder(
            self.memory, Path(project.path), config.indexing, project.id, config.retrieval
        )
        self.senior_service = SeniorService(db, config)
        self.learning_extractor = LearningExtractor(db)

    def run_task(self, title: str, description: str = "", source: str = "cli") -> TaskRunSummary:
        task = self.task_repo.create(self.project.id, title=title, description=description, source=source)
        return self._prepare_task(task, archive_existing=False)

    def refresh_task(
        self, task_id: int, title: str | None = None, description: str | None = None
    ) -> TaskRunSummary:
        task = self.task_repo.get(task_id)
        if task.project_id != self.project.id:
            raise ValueError(f"Task {task_id} does not belong to project {self.project.id}")
        if task.status not in {TaskStatus.SENIOR_REQUIRED.value, TaskStatus.FAILED.value}:
            raise ValueError(f"Task {task_id} cannot be refreshed from status {task.status}")
        prior_session = self.db.query_one(
            "SELECT id FROM senior_sessions WHERE task_id=? AND status='SUCCESS'", (task_id,)
        )
        if prior_session:
            raise ValueError(f"Task {task_id} already has a successful Senior submission")
        audit_dir = self.paths.task_dir(slugify(self.project.name), task.id)
        if (audit_dir / "senior-response.json").exists():
            raise ValueError(f"Task {task_id} already has a Senior response artifact")
        task = self.task_repo.update_definition(task_id, title=title, description=description)
        return self._prepare_task(task, archive_existing=True)

    def _prepare_task(self, task: Task, archive_existing: bool) -> TaskRunSummary:
        audit_dir = self.paths.task_dir(slugify(self.project.name), task.id)
        if archive_existing and audit_dir.exists():
            revisions_dir = audit_dir / "revisions"
            revision_number = len([p for p in revisions_dir.glob("*") if p.is_dir()]) + 1
            revision_dir = revisions_dir / f"{revision_number:04d}"
            revision_dir.mkdir(parents=True, exist_ok=False)
            for artifact in audit_dir.iterdir():
                if artifact.name == "revisions" or not artifact.is_file():
                    continue
                shutil.copy2(artifact, revision_dir / artifact.name)
            self._archive_test_results(task.id, revision_number)
        audit_dir.mkdir(parents=True, exist_ok=True)
        self._write(
            audit_dir / "request.json",
            {"title": task.title, "description": task.description, "source": task.source},
        )

        task = (
            self.task_repo.reset_for_refresh(task.id)
            if archive_existing
            else self.task_repo.update_status(task.id, TaskStatus.ANALYZING)
        )

        git_commit_before = self.context_builder_git_commit()
        context = self.context_builder.build(task, self.project.id)
        self._write(audit_dir / "context.json", self._context_to_dict(context))

        warnings: list[str] = []
        if context.git_status and context.git_status.has_pre_existing_changes:
            warnings.append(
                "PRE_EXISTING_CHANGE: target project has uncommitted changes; "
                "Project Brain will not attempt any file modification for this task."
            )

        senior_status = self.senior_service.check_availability()
        if (
            self.config.senior.provider.lower() != "codex-vscode"
            and senior_status != SeniorStatus.AVAILABLE
            and not self.config.fallback.enabled
        ):
            summary = self._wait_for_senior(task, context, audit_dir, senior_status)
            local_preview = None
        else:
            local_preview = try_execute(
                task, context, self.config, self.db, self.project.id, Path(self.project.path)
            )
        if local_preview is not None:
            classification_data = local_preview.signals.get("classification", {})
            classification = Classification(
                category=classification_data.get("category", local_preview.category),
                concepts=tuple(classification_data.get("concepts", [])),
                intent=classification_data.get("intent", "unknown"),
                reasons=tuple(classification_data.get("reasons", [])),
            )
            routing_status = (
                SeniorStatus.MANUAL_HANDOFF
                if self.config.senior.provider.lower() == "codex-vscode"
                else senior_status
            )
            route = SmartRouter().route(classification, local_preview.confidence, routing_status)
            local_preview.signals["route"] = {"mode": route.mode.value, "reason": route.reason}

            if route.mode in {RoutingMode.LOCAL, RoutingMode.ANALYSIS_ONLY}:
                summary = self._run_with_local_fallback(
                    task, context, audit_dir, senior_status, local_preview, route.mode
                )
            elif self.config.senior.provider.lower() == "codex-vscode":
                summary = self._queue_for_workspace(task, context, audit_dir, local_preview)
            elif senior_status == SeniorStatus.AVAILABLE:
                summary = self._run_with_senior(task, context, audit_dir)
            else:
                summary = self._run_with_local_fallback(task, context, audit_dir, senior_status)

        if summary.mode != ExecutionMode.WAITING_FOR_SENIOR:
            self._run_qa(task, context, audit_dir)

        git_commit_after = self.context_builder_git_commit()
        self.task_repo.set_git_commits(task.id, git_commit_before, git_commit_after)

        summary.warnings = warnings
        summary.audit_dir = audit_dir
        self._write(
            audit_dir / "decision.json",
            {
                "mode": summary.mode.value,
                "senior_status": summary.senior_status.value,
                "decision": summary.decision.value,
                "confidence": summary.confidence,
                "category": summary.category,
                "message": summary.message,
                "warnings": warnings,
            },
        )
        return summary

    def _archive_test_results(self, task_id: int, revision: int) -> None:
        with self.db.conn:
            self.db.conn.execute(
                "INSERT INTO test_result_revisions("
                "original_test_result_id, task_id, revision, tool, command, exit_code, "
                "passed, output, created_at, archived_at"
                ") SELECT id, task_id, ?, tool, command, exit_code, passed, output, "
                "created_at, ? FROM test_results WHERE task_id=?",
                (revision, _now(), task_id),
            )
            self.db.conn.execute("DELETE FROM test_results WHERE task_id=?", (task_id,))

    # -- internal steps ---------------------------------------------------
    def context_builder_git_commit(self) -> str | None:
        from git.git_service import GitService

        if not GitService.is_git_available():
            return None
        return GitService(Path(self.project.path)).current_commit()

    def _run_with_senior(self, task: Task, context: TaskContext, audit_dir: Path) -> TaskRunSummary:
        task = self.task_repo.update_status(task.id, TaskStatus.SENIOR_RUNNING)
        result = self.senior_service.analyze(task, context)

        if result.learning and self.config.learning.automatic_after_approval:
            extraction = self.learning_extractor.apply(result.learning, task.id, self.project.id)
            self._write(audit_dir / "learning.json", dataclasses.asdict(extraction))

        final_status = (
            TaskStatus.COMPLETED if result.decision == Decision.AUTO_EXECUTE_ALLOWED else TaskStatus.WAITING_REVIEW
        )
        task = self.task_repo.update_status(
            task.id, final_status, confidence=result.confidence, decision=result.decision.value,
            completed=(final_status == TaskStatus.COMPLETED),
        )
        return TaskRunSummary(
            task=task,
            mode=ExecutionMode.SENIOR,
            senior_status=SeniorStatus.AVAILABLE,
            decision=result.decision,
            confidence=result.confidence,
            category=task.category,
            message=result.summary,
            context=context,
            audit_dir=audit_dir,
        )

    def _wait_for_senior(
        self, task: Task, context: TaskContext, audit_dir: Path, senior_status: SeniorStatus
    ) -> TaskRunSummary:
        task = self.task_repo.update_status(
            task.id,
            TaskStatus.SENIOR_REQUIRED,
            confidence=0.0,
            decision=Decision.REQUIRES_SENIOR.value,
            category=task.category,
        )
        return TaskRunSummary(
            task=task,
            mode=ExecutionMode.WAITING_FOR_SENIOR,
            senior_status=senior_status,
            decision=Decision.REQUIRES_SENIOR,
            confidence=0.0,
            category=task.category,
            message="Senior unavailable and local fallback is disabled. No local agents were run.",
            context=context,
            audit_dir=audit_dir,
        )

    def _queue_for_workspace(
        self, task: Task, context: TaskContext, audit_dir: Path,
        local_result: LocalExecutionResult | None = None,
    ) -> TaskRunSummary:
        local_result = local_result or try_execute(
            task, context, self.config, self.db, self.project.id, Path(self.project.path)
        )
        self._write(audit_dir / "local_execution.json", self._local_result_to_dict(local_result))
        task = self.task_repo.update_status(
            task.id,
            TaskStatus.SENIOR_REQUIRED,
            confidence=local_result.confidence,
            decision=Decision.REQUIRES_SENIOR.value,
            category=local_result.category,
        )
        self._write(
            audit_dir / "senior-request.json",
            {
                "integration": "codex-vscode-inverted",
                "task_id": task.id,
                "instruction": (
                    f"Codex in VS Code must read this task with `brain senior context {task.id}` "
                    f"and submit a validated JSON result with `brain senior submit {task.id} --file <path>`."
                ),
            },
        )
        return TaskRunSummary(
            task=task,
            mode=ExecutionMode.WORKSPACE_HANDOFF,
            senior_status=SeniorStatus.MANUAL_HANDOFF,
            decision=Decision.REQUIRES_SENIOR,
            confidence=local_result.confidence,
            category=local_result.category,
            message="Context prepared for Codex in VS Code; no external process was invoked.",
            context=context,
            audit_dir=audit_dir,
            local_result=local_result,
        )

    def _run_with_local_fallback(
        self, task: Task, context: TaskContext, audit_dir: Path, senior_status: SeniorStatus,
        local_result: LocalExecutionResult | None = None,
        route_mode: RoutingMode | None = None,
    ) -> TaskRunSummary:
        task = self.task_repo.update_status(task.id, TaskStatus.LOCAL_EXECUTION)
        local_result = local_result or try_execute(
            task, context, self.config, self.db, self.project.id, Path(self.project.path)
        )
        if route_mode == RoutingMode.ANALYSIS_ONLY:
            local_result.decision = Decision.ANALYSIS_ONLY
            local_result.message = (
                "Deterministic memory provides sufficient evidence for local analysis. "
                "No files were modified."
            )
        self._write(audit_dir / "local_execution.json", self._local_result_to_dict(local_result))

        if local_result.decision == Decision.REQUIRES_SENIOR:
            final_status = TaskStatus.SENIOR_REQUIRED
        elif local_result.decision == Decision.AUTO_EXECUTE_ALLOWED:
            final_status = TaskStatus.COMPLETED
        else:
            final_status = TaskStatus.WAITING_REVIEW

        task = self.task_repo.update_status(
            task.id, final_status,
            confidence=local_result.confidence, decision=local_result.decision.value,
            category=local_result.category, completed=(final_status == TaskStatus.COMPLETED),
        )
        return TaskRunSummary(
            task=task,
            mode=ExecutionMode.LOCAL_FALLBACK,
            senior_status=senior_status,
            decision=local_result.decision,
            confidence=local_result.confidence,
            category=local_result.category,
            message=local_result.message,
            context=context,
            audit_dir=audit_dir,
            local_result=local_result,
        )

    def _run_qa(self, task: Task, context: TaskContext, audit_dir: Path) -> None:
        php_files = [f for f in context.candidate_files if f.endswith(".php")]
        if not (self.config.qa.run_php_lint and php_files):
            return
        qa_agent = QAAgent(Path(self.project.path))
        result = qa_agent.lint(php_files)
        self._write(audit_dir / "tests.json", {"status": result.status.value, "message": result.message, "data": result.data})
        self.db.execute(
            "INSERT INTO test_results(task_id, tool, command, exit_code, passed, output, created_at)"
            " VALUES (?,?,?,?,?,?,?)",
            (
                task.id, "php -l", "php -l <candidate files>", 0 if result.ok else 1,
                int(result.ok), result.message, _now(),
            ),
        )

    # -- serialization helpers --------------------------------------------
    @staticmethod
    def _write(path: Path, data: dict) -> None:
        path.write_text(json.dumps(data, indent=2, default=_json_default, ensure_ascii=False), encoding="utf-8")

    @staticmethod
    def _context_to_dict(context: TaskContext) -> dict:
        return {
            "task": dataclasses.asdict(context.task),
            "rules": [dataclasses.asdict(r) for r in context.rules],
            "patterns": [dataclasses.asdict(p) for p in context.patterns],
            "lessons": [dataclasses.asdict(l) for l in context.lessons],
            "similar_tasks": [
                {"task_id": s.task.id, "title": s.task.title, "score": s.score} for s in context.similar_tasks
            ],
            "candidate_files": context.candidate_files,
            "keywords": context.keywords,
            "git_status": dataclasses.asdict(context.git_status) if context.git_status else None,
            "known_risks": context.known_risks,
        }

    @staticmethod
    def _local_result_to_dict(result: LocalExecutionResult) -> dict:
        return {
            "category": result.category,
            "confidence": result.confidence,
            "decision": result.decision.value,
            "message": result.message,
            "signals": result.signals,
            "agent_findings": result.agent_findings,
            "files_modified": result.files_modified,
        }
