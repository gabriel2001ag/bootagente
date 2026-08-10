"""LearningExtractor: turns a structured Senior output (seção 12 contract)
into rows in `rules` / `patterns` / `lessons` (seção 24/25).

V1 does not attempt to derive this automatically from a raw diff — the
Senior (today: MockSeniorProvider) is the one producing the structured
`LearningPayload`. A future, purely-local diff-based extractor is a V2 item.
"""
from __future__ import annotations

from dataclasses import dataclass

from brain.database import Database
from brain.lessons import LessonRepository
from brain.patterns import PatternRepository
from brain.rules import RuleRepository
from senior.provider import LearningPayload


def _next_code(db: Database, table: str, code_column: str, prefix: str) -> str:
    row = db.query_one(f"SELECT COUNT(*) AS n FROM {table}")
    n = (row["n"] if row else 0) + 1
    return f"{prefix}-{n:04d}"


@dataclass
class ExtractionSummary:
    rules_created: list[str]
    patterns_created: list[str]
    lessons_created: list[str]


class LearningExtractor:
    def __init__(self, db: Database):
        self.db = db
        self.rules = RuleRepository(db)
        self.patterns = PatternRepository(db)
        self.lessons = LessonRepository(db)

    def apply(self, payload: LearningPayload, task_id: int, project_id: int) -> ExtractionSummary:
        rules_created = []
        for rule_data in payload.rules:
            code = rule_data.get("id") or _next_code(self.db, "rules", "rule_code", "RULE")
            self.rules.add(
                rule_code=code,
                category=rule_data.get("category", "general"),
                rule_text=rule_data.get("rule", rule_data.get("rule_text", "")),
                condition=rule_data.get("condition"),
                dont=rule_data.get("dont", []),
                confidence=float(rule_data.get("confidence", 1.0)),
                source="senior_learning",
                approved=bool(rule_data.get("approved", True)),
                project_id=project_id,
            )
            rules_created.append(code)

        patterns_created = []
        for pattern_data in payload.patterns:
            code = pattern_data.get("id") or _next_code(self.db, "patterns", "pattern_code", "PATTERN")
            self.patterns.add(
                pattern_code=code,
                category=pattern_data.get("category", "general"),
                trigger=pattern_data.get("trigger"),
                framework=pattern_data.get("framework"),
                procedure=pattern_data.get("procedure", []),
                approved=bool(pattern_data.get("approved", True)),
                confidence=float(pattern_data.get("confidence", 1.0)),
                project_id=project_id,
            )
            patterns_created.append(code)

        lessons_created = []
        for lesson_data in payload.lessons:
            code = lesson_data.get("id") or _next_code(self.db, "lessons", "lesson_code", "LESSON")
            self.lessons.add(
                lesson_code=code,
                problem=lesson_data.get("problem", ""),
                solution=lesson_data.get("solution", ""),
                category=lesson_data.get("category", "general"),
                files=lesson_data.get("files", []),
                approved=bool(lesson_data.get("approved", True)),
                validated_by=lesson_data.get("validated_by", "senior"),
                confidence=float(lesson_data.get("confidence", 1.0)),
                task_id=task_id,
                project_id=project_id,
            )
            lessons_created.append(code)

        return ExtractionSummary(rules_created, patterns_created, lessons_created)
