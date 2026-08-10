"""Inverted integration used by Codex inside VS Code."""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any

from brain.database import Database
from brain.learning_extractor import ExtractionSummary, LearningExtractor
from brain.projects import ProjectRepository
from core.config import BrainConfig
from core.enums import Decision, TaskStatus
from core.paths import BrainPaths, slugify
from core.task import Task, TaskRepository
from senior.provider import LearningPayload


class BridgeValidationError(ValueError):
    pass


@dataclass
class BridgeSubmission:
    task: Task
    learning: ExtractionSummary | None


class CodexWorkspaceBridge:
    """Local pull/submit bridge; it never controls the VS Code extension."""

    provider_name = "codex-vscode"

    def __init__(self, db: Database, paths: BrainPaths, config: BrainConfig | None = None):
        self.db = db
        self.paths = paths
        self.config = config
        self.tasks = TaskRepository(db)
        self.projects = ProjectRepository(db)

    def pending(self, project_id: int | None = None) -> list[Task]:
        sql = "SELECT id FROM tasks WHERE status = ?"
        params: list[Any] = [TaskStatus.SENIOR_REQUIRED.value]
        if project_id is not None:
            sql += " AND project_id = ?"
            params.append(project_id)
        sql += " ORDER BY id"
        return [self.tasks.get(row["id"]) for row in self.db.query(sql, params)]

    @staticmethod
    def discover_extension() -> dict[str, Any] | None:
        roots = [Path.home() / ".vscode" / "extensions", Path.home() / ".vscode-insiders" / "extensions"]
        manifests = [
            path / "package.json"
            for root in roots if root.exists()
            for path in root.glob("openai.chatgpt-*")
            if (path / "package.json").exists()
        ]
        if not manifests:
            return None
        manifest = max(manifests, key=lambda path: path.stat().st_mtime)
        data = json.loads(manifest.read_text(encoding="utf-8"))
        return {
            "id": f"{data.get('publisher')}.{data.get('name')}",
            "display_name": data.get("displayName"),
            "version": data.get("version"),
            "path": str(manifest.parent),
        }

    def context(self, task_id: int) -> dict[str, Any]:
        task = self.tasks.get(task_id)
        if task.status != TaskStatus.SENIOR_REQUIRED.value:
            raise BridgeValidationError(f"Task {task_id} is not waiting for Codex (status={task.status})")
        audit_dir = self._audit_dir(task)
        context_path = audit_dir / "context.json"
        if not context_path.exists():
            raise BridgeValidationError(f"Context for task {task_id} was not prepared")
        return {
            "contract_version": 1,
            "integration": "codex-vscode-inverted",
            "task": self._read_json(audit_dir / "request.json"),
            "context": self._read_json(context_path),
            "response_contract": {
                "status": "SUCCESS",
                "summary": "non-empty string",
                "decision": [item.value for item in Decision],
                "confidence": "number from 0 to 1",
                "requires_human_review": "boolean",
                "approved_for_learning": "boolean",
                "important_files": [],
                "affected_modules": [],
                "risks": [],
                "rules_discovered": [],
                "patterns_used": [],
                "lessons": [],
                "evidence": [],
            },
        }

    def submit(self, task_id: int, payload: dict[str, Any]) -> BridgeSubmission:
        task = self.tasks.get(task_id)
        if task.status != TaskStatus.SENIOR_REQUIRED.value:
            raise BridgeValidationError(
                f"Task {task_id} cannot be submitted from status {task.status}; duplicate submissions are rejected"
            )
        normalized = self._validate(payload, task.project_id)
        audit_dir = self._audit_dir(task)
        current_commit = self._current_commit(task)
        if task.git_commit_before and current_commit and task.git_commit_before != current_commit:
            raise BridgeValidationError("STALE_CONTEXT: target Git commit changed after context preparation")

        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        claim = self.db.execute(
            "UPDATE tasks SET status = ?, updated_at = ? WHERE id = ? AND status = ?",
            (TaskStatus.SENIOR_RUNNING.value, now, task.id, TaskStatus.SENIOR_REQUIRED.value),
        )
        if claim.rowcount != 1:
            raise BridgeValidationError("Task was already claimed by another Codex session")

        try:
            self._write_json(audit_dir / "senior-response.json", normalized)
            self._write_json(audit_dir / "evidence.json", {"evidence": normalized["evidence"]})
            self.db.execute(
                "INSERT INTO senior_sessions(task_id, provider, status, request_json, response_json, created_at)"
                " VALUES (?,?,?,?,?,?)",
                (
                    task.id, self.provider_name, "SUCCESS",
                    json.dumps({"contract_version": 1}),
                    json.dumps(normalized, ensure_ascii=False), now,
                ),
            )

            learning_summary = None
            learning_allowed = self.config is None or self.config.learning.automatic_after_approval
            if normalized["approved_for_learning"] and learning_allowed:
                learning = LearningPayload(
                    rules=normalized["rules_discovered"],
                    patterns=normalized["patterns_used"],
                    lessons=normalized["lessons"],
                    affected_modules=normalized["affected_modules"],
                    risks=normalized["risks"],
                    important_files=normalized["important_files"],
                )
                learning_summary = LearningExtractor(self.db).apply(learning, task.id, task.project_id)
                self._write_json(
                    audit_dir / "learning.json",
                    {
                        "rules_created": learning_summary.rules_created,
                        "patterns_created": learning_summary.patterns_created,
                        "lessons_created": learning_summary.lessons_created,
                    },
                )

            task = self.tasks.update_status(
                task.id, TaskStatus.WAITING_REVIEW,
                confidence=normalized["confidence"], decision=normalized["decision"],
            )
        except Exception:
            self.tasks.update_status(task.id, TaskStatus.FAILED)
            raise
        return BridgeSubmission(task, learning_summary)

    def _audit_dir(self, task: Task) -> Path:
        project = self.projects.get_by_id(task.project_id)
        return self.paths.task_dir(slugify(project.name), task.id)

    def _current_commit(self, task: Task) -> str | None:
        from git.git_service import GitService

        project = self.projects.get_by_id(task.project_id)
        return GitService(Path(project.path)).current_commit() if GitService.is_git_available() else None

    def _validate(self, payload: dict[str, Any], project_id: int) -> dict[str, Any]:
        if not isinstance(payload, dict) or payload.get("status") != "SUCCESS":
            raise BridgeValidationError("Response status must be SUCCESS")
        summary = payload.get("summary")
        if not isinstance(summary, str) or not summary.strip():
            raise BridgeValidationError("summary must be a non-empty string")
        try:
            decision = Decision(payload.get("decision", Decision.ANALYSIS_ONLY.value)).value
        except ValueError as exc:
            raise BridgeValidationError("decision is invalid") from exc
        confidence = payload.get("confidence")
        if not isinstance(confidence, (int, float)) or isinstance(confidence, bool) or not 0 <= confidence <= 1:
            raise BridgeValidationError("confidence must be a number from 0 to 1")
        normalized = dict(payload)
        for boolean_field, default in (
            ("requires_human_review", True),
            ("approved_for_learning", False),
        ):
            value = payload.get(boolean_field, default)
            if not isinstance(value, bool):
                raise BridgeValidationError(f"{boolean_field} must be a boolean")
            normalized[boolean_field] = value
        normalized.update(
            decision=decision,
            confidence=float(confidence),
        )
        for field in (
            "important_files", "affected_modules", "risks",
            "rules_discovered", "patterns_used", "lessons",
        ):
            value = payload.get(field, [])
            if not isinstance(value, list):
                raise BridgeValidationError(f"{field} must be a list")
            if field in ("rules_discovered", "patterns_used", "lessons") and any(
                not isinstance(item, dict) for item in value
            ):
                raise BridgeValidationError(f"every item in {field} must be an object")
            if field in ("important_files", "affected_modules", "risks") and any(
                not isinstance(item, str) for item in value
            ):
                raise BridgeValidationError(f"every item in {field} must be a string")
            normalized[field] = value
        for item in normalized["rules_discovered"]:
            text = item.get("rule", item.get("rule_text"))
            if not isinstance(text, str) or not text.strip():
                raise BridgeValidationError("every rule must contain non-empty rule or rule_text")
        for item in normalized["patterns_used"]:
            category = item.get("category")
            if not isinstance(category, str) or not category.strip():
                raise BridgeValidationError("every pattern must contain non-empty category")
            procedure = item.get("procedure", [])
            if not isinstance(procedure, list) or any(not isinstance(step, str) for step in procedure):
                raise BridgeValidationError("pattern procedure must be a list of strings")
        for item in normalized["lessons"]:
            if not isinstance(item.get("problem"), str) or not item["problem"].strip():
                raise BridgeValidationError("every lesson must contain non-empty problem")
            if not isinstance(item.get("solution"), str) or not item["solution"].strip():
                raise BridgeValidationError("every lesson must contain non-empty solution")

        evidence = payload.get("evidence", [])
        if not isinstance(evidence, list) or any(not isinstance(item, dict) for item in evidence):
            raise BridgeValidationError("evidence must be a list of objects")
        for item in evidence:
            if not isinstance(item.get("claim"), str) or not item["claim"].strip():
                raise BridgeValidationError("every evidence item must contain a non-empty claim")
            path_value = item.get("path")
            if path_value is not None:
                if not isinstance(path_value, str) or not path_value.strip():
                    raise BridgeValidationError("evidence path must be a non-empty string")
                slash_path = path_value.replace("\\", "/")
                pure = PurePosixPath(slash_path)
                if (
                    pure.is_absolute()
                    or PureWindowsPath(path_value).is_absolute()
                    or ".." in pure.parts
                ):
                    raise BridgeValidationError("evidence path must be relative and stay inside the project")
                normalized_path = pure.as_posix().lstrip("./")
                indexed = self.db.query_one(
                    "SELECT path FROM files WHERE project_id=? AND path=?",
                    (project_id, normalized_path),
                )
                if not indexed:
                    raise BridgeValidationError(
                        f"evidence path is not indexed for project {project_id}: {normalized_path}"
                    )
                project_root = Path(self.projects.get_by_id(project_id).path).resolve()
                candidate = (project_root / normalized_path).resolve()
                try:
                    candidate.relative_to(project_root)
                except ValueError as exc:
                    raise BridgeValidationError(
                        "evidence path resolves outside the project"
                    ) from exc
                if not candidate.exists() or not candidate.is_file():
                    raise BridgeValidationError(
                        f"evidence path does not exist as a regular file: {normalized_path}"
                    )
                item["path"] = normalized_path
            if "line" in item and (
                not isinstance(item["line"], int)
                or isinstance(item["line"], bool)
                or item["line"] < 1
            ):
                raise BridgeValidationError("evidence line must be a positive integer")
            if "line" in item and path_value is None:
                raise BridgeValidationError("evidence line requires an indexed path")
            if "line" in item:
                project = self.projects.get_by_id(project_id)
                absolute_path = Path(project.path) / item["path"]
                try:
                    line_count = sum(
                        1 for _ in absolute_path.open("r", encoding="utf-8", errors="replace")
                    )
                except OSError as exc:
                    raise BridgeValidationError(
                        f"evidence path cannot be read: {item['path']}"
                    ) from exc
                if item["line"] > line_count:
                    raise BridgeValidationError(
                        f"evidence line exceeds file length for {item['path']}"
                    )
            if "type" in item and not isinstance(item["type"], str):
                raise BridgeValidationError("evidence type must be a string")
        normalized["evidence"] = evidence
        return normalized

    @staticmethod
    def _read_json(path: Path) -> dict[str, Any]:
        return json.loads(path.read_text(encoding="utf-8"))

    @staticmethod
    def _write_json(path: Path, data: dict[str, Any]) -> None:
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
