"""Task dataclass + persistence (seção 7)."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from brain.database import Database
from core.enums import TaskCategory, TaskStatus


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass
class Task:
    id: int
    project_id: int
    title: str
    description: str
    category: str = TaskCategory.UNKNOWN.value
    status: str = TaskStatus.NEW.value
    confidence: float | None = None
    decision: str | None = None
    source: str = "cli"
    external_id: str | None = None
    created_at: str = ""
    updated_at: str = ""
    completed_at: str | None = None
    git_commit_before: str | None = None
    git_commit_after: str | None = None


class TaskRepository:
    def __init__(self, db: Database):
        self.db = db

    def create(
        self,
        project_id: int,
        title: str,
        description: str = "",
        source: str = "cli",
        external_id: str | None = None,
    ) -> Task:
        now = _now()
        cur = self.db.execute(
            "INSERT INTO tasks(project_id, external_id, title, description, category, "
            "status, source, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?)",
            (
                project_id,
                external_id,
                title,
                description,
                TaskCategory.UNKNOWN.value,
                TaskStatus.NEW.value,
                source,
                now,
                now,
            ),
        )
        return self.get(cur.lastrowid)

    def get(self, task_id: int) -> Task:
        row = self.db.query_one("SELECT * FROM tasks WHERE id = ?", (task_id,))
        if not row:
            raise LookupError(f"Task {task_id} not found")
        return self._from_row(row)

    def list_for_project(self, project_id: int, limit: int = 50) -> list[Task]:
        rows = self.db.query(
            "SELECT * FROM tasks WHERE project_id = ? ORDER BY id DESC LIMIT ?",
            (project_id, limit),
        )
        return [self._from_row(r) for r in rows]

    def update_status(
        self,
        task_id: int,
        status: TaskStatus,
        confidence: float | None = None,
        decision: str | None = None,
        category: str | None = None,
        completed: bool = False,
    ) -> Task:
        now = _now()
        fields = ["status = ?", "updated_at = ?"]
        params: list = [status.value, now]
        if confidence is not None:
            fields.append("confidence = ?")
            params.append(confidence)
        if decision is not None:
            fields.append("decision = ?")
            params.append(decision)
        if category is not None:
            fields.append("category = ?")
            params.append(category)
        if completed:
            fields.append("completed_at = ?")
            params.append(now)
        params.append(task_id)
        self.db.execute(f"UPDATE tasks SET {', '.join(fields)} WHERE id = ?", params)
        return self.get(task_id)

    def set_git_commits(self, task_id: int, before: str | None, after: str | None) -> None:
        self.db.execute(
            "UPDATE tasks SET git_commit_before = ?, git_commit_after = ? WHERE id = ?",
            (before, after, task_id),
        )

    def reset_for_refresh(self, task_id: int) -> Task:
        now = _now()
        self.db.execute(
            "UPDATE tasks SET status=?, category=?, confidence=NULL, decision=NULL, "
            "completed_at=NULL, git_commit_before=NULL, git_commit_after=NULL, updated_at=? "
            "WHERE id=?",
            (TaskStatus.ANALYZING.value, TaskCategory.UNKNOWN.value, now, task_id),
        )
        return self.get(task_id)

    def update_definition(
        self, task_id: int, title: str | None = None, description: str | None = None
    ) -> Task:
        if title is None and description is None:
            return self.get(task_id)
        fields = ["updated_at=?"]
        params: list = [_now()]
        if title is not None:
            fields.append("title=?")
            params.append(title)
        if description is not None:
            fields.append("description=?")
            params.append(description)
        params.append(task_id)
        self.db.execute(f"UPDATE tasks SET {', '.join(fields)} WHERE id=?", params)
        return self.get(task_id)

    @staticmethod
    def _from_row(row) -> Task:
        return Task(
            id=row["id"],
            project_id=row["project_id"],
            title=row["title"],
            description=row["description"] or "",
            category=row["category"],
            status=row["status"],
            confidence=row["confidence"],
            decision=row["decision"],
            source=row["source"],
            external_id=row["external_id"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            completed_at=row["completed_at"],
            git_commit_before=row["git_commit_before"],
            git_commit_after=row["git_commit_after"],
        )
