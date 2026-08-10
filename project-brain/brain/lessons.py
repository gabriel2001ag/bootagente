"""Lesson storage (seção 10)."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone

from brain.database import Database


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass
class Lesson:
    id: int
    lesson_code: str
    problem: str
    solution: str
    category: str = "general"
    files: list[str] = field(default_factory=list)
    approved: bool = True
    validated_by: str | None = None
    confidence: float = 1.0
    task_id: int | None = None
    project_id: int | None = None
    created_at: str = ""


class LessonRepository:
    def __init__(self, db: Database):
        self.db = db

    def add(
        self,
        lesson_code: str,
        problem: str,
        solution: str,
        category: str = "general",
        files: list[str] | None = None,
        approved: bool = True,
        validated_by: str | None = None,
        confidence: float = 1.0,
        task_id: int | None = None,
        project_id: int | None = None,
    ) -> Lesson:
        now = _now()
        self.db.execute(
            "INSERT OR REPLACE INTO lessons(lesson_code, project_id, task_id, problem, solution, "
            "files_json, category, approved, validated_by, confidence, created_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?, COALESCE((SELECT created_at FROM lessons WHERE lesson_code=?), ?))",
            (
                lesson_code,
                project_id,
                task_id,
                problem,
                solution,
                json.dumps(files or []),
                category,
                int(approved),
                validated_by,
                confidence,
                lesson_code,
                now,
            ),
        )
        return self.get(lesson_code)

    def get(self, lesson_code: str) -> Lesson:
        row = self.db.query_one("SELECT * FROM lessons WHERE lesson_code = ?", (lesson_code,))
        if not row:
            raise LookupError(lesson_code)
        return self._from_row(row)

    def list_approved(self, project_id: int | None = None) -> list[Lesson]:
        rows = self.db.query(
            "SELECT * FROM lessons WHERE approved = 1 AND deprecated = 0"
            " AND (project_id IS NULL OR project_id = ?)"
            " ORDER BY id",
            (project_id,),
        )
        return [self._from_row(r) for r in rows]

    def search(self, keywords: list[str], project_id: int | None = None) -> list[Lesson]:
        lessons = self.list_approved(project_id)
        if not keywords:
            return lessons
        lowered = [k.lower() for k in keywords]
        matched = []
        for lesson in lessons:
            haystack = f"{lesson.category} {lesson.problem} {lesson.solution}".lower()
            if any(k in haystack for k in lowered):
                matched.append(lesson)
        return matched

    @staticmethod
    def _from_row(row) -> Lesson:
        return Lesson(
            id=row["id"],
            lesson_code=row["lesson_code"],
            problem=row["problem"] or "",
            solution=row["solution"] or "",
            category=row["category"],
            files=json.loads(row["files_json"] or "[]"),
            approved=bool(row["approved"]),
            validated_by=row["validated_by"],
            confidence=row["confidence"],
            task_id=row["task_id"],
            project_id=row["project_id"],
            created_at=row["created_at"],
        )
