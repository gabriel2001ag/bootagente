"""Project registry (tabela `projects`, seção 6).

Enables `brain init <path>` to register (or re-use) a target project, and
subsequent commands to operate on the "active project" tracked in
`state.json` (see core/paths.py and ARCHITECTURE.md section 2).
"""
from __future__ import annotations

from datetime import datetime, timezone

from brain.database import Database
from brain.models import Project


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class ProjectRepository:
    def __init__(self, db: Database):
        self.db = db

    def get_or_create(self, path: str, name: str | None = None, vcs: str = "git") -> Project:
        row = self.db.query_one("SELECT * FROM projects WHERE path = ?", (path,))
        if row:
            return self._from_row(row)
        now = _now()
        project_name = name or path.rstrip("/\\").split("/")[-1].split("\\")[-1]
        cur = self.db.execute(
            "INSERT INTO projects(name, path, vcs, primary_language, created_at, updated_at)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            (project_name, path, vcs, None, now, now),
        )
        return self.get_by_id(cur.lastrowid)

    def get_by_id(self, project_id: int) -> Project:
        row = self.db.query_one("SELECT * FROM projects WHERE id = ?", (project_id,))
        if not row:
            raise LookupError(f"Project {project_id} not found")
        return self._from_row(row)

    def get_by_path(self, path: str) -> Project | None:
        row = self.db.query_one("SELECT * FROM projects WHERE path = ?", (path,))
        return self._from_row(row) if row else None

    def list_all(self) -> list[Project]:
        return [self._from_row(r) for r in self.db.query("SELECT * FROM projects ORDER BY id")]

    def touch_indexed(self, project_id: int, primary_language: str | None = None) -> None:
        now = _now()
        if primary_language:
            self.db.execute(
                "UPDATE projects SET last_indexed_at = ?, updated_at = ?, primary_language = ? WHERE id = ?",
                (now, now, primary_language, project_id),
            )
        else:
            self.db.execute(
                "UPDATE projects SET last_indexed_at = ?, updated_at = ? WHERE id = ?",
                (now, now, project_id),
            )

    @staticmethod
    def _from_row(row) -> Project:
        return Project(
            id=row["id"],
            name=row["name"],
            path=row["path"],
            vcs=row["vcs"],
            primary_language=row["primary_language"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            last_indexed_at=row["last_indexed_at"],
        )
