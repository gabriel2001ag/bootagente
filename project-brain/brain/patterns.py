"""Pattern storage (seção 9)."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone

from brain.database import Database


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass
class Pattern:
    id: int
    pattern_code: str
    category: str
    framework: str | None
    trigger: str | None
    procedure: list[str] = field(default_factory=list)
    approved: bool = True
    confidence: float = 1.0
    project_id: int | None = None
    created_at: str = ""


class PatternRepository:
    def __init__(self, db: Database):
        self.db = db

    def add(
        self,
        pattern_code: str,
        category: str,
        trigger: str | None = None,
        framework: str | None = None,
        procedure: list[str] | None = None,
        approved: bool = True,
        confidence: float = 1.0,
        project_id: int | None = None,
    ) -> Pattern:
        now = _now()
        self.db.execute(
            "INSERT OR REPLACE INTO patterns(pattern_code, project_id, category, framework, "
            "trigger, procedure_json, approved, confidence, created_at) "
            "VALUES (?,?,?,?,?,?,?,?, COALESCE((SELECT created_at FROM patterns WHERE pattern_code=?), ?))",
            (
                pattern_code,
                project_id,
                category,
                framework,
                trigger,
                json.dumps(procedure or []),
                int(approved),
                confidence,
                pattern_code,
                now,
            ),
        )
        return self.get(pattern_code)

    def get(self, pattern_code: str) -> Pattern:
        row = self.db.query_one("SELECT * FROM patterns WHERE pattern_code = ?", (pattern_code,))
        if not row:
            raise LookupError(pattern_code)
        return self._from_row(row)

    def list_approved(self, project_id: int | None = None) -> list[Pattern]:
        rows = self.db.query(
            "SELECT * FROM patterns WHERE approved = 1 AND deprecated = 0"
            " AND (project_id IS NULL OR project_id = ?)"
            " ORDER BY id",
            (project_id,),
        )
        return [self._from_row(r) for r in rows]

    def search_by_trigger(self, trigger: str, project_id: int | None = None) -> list[Pattern]:
        return [p for p in self.list_approved(project_id) if p.trigger == trigger]

    @staticmethod
    def _from_row(row) -> Pattern:
        return Pattern(
            id=row["id"],
            pattern_code=row["pattern_code"],
            category=row["category"],
            framework=row["framework"],
            trigger=row["trigger"],
            procedure=json.loads(row["procedure_json"] or "[]"),
            approved=bool(row["approved"]),
            confidence=row["confidence"],
            project_id=row["project_id"],
            created_at=row["created_at"],
        )
