"""Rule storage (seção 8)."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone

from brain.database import Database


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass
class Rule:
    id: int
    rule_code: str
    category: str
    rule_text: str
    condition: str | None = None
    dont: list[str] = field(default_factory=list)
    confidence: float = 1.0
    source: str = "manual"
    approved: bool = True
    project_id: int | None = None
    created_at: str = ""


class RuleRepository:
    def __init__(self, db: Database):
        self.db = db

    def add(
        self,
        rule_code: str,
        category: str,
        rule_text: str,
        condition: str | None = None,
        dont: list[str] | None = None,
        confidence: float = 1.0,
        source: str = "manual",
        approved: bool = True,
        project_id: int | None = None,
    ) -> Rule:
        now = _now()
        self.db.execute(
            "INSERT OR REPLACE INTO rules(rule_code, project_id, category, condition_text, "
            "rule_text, dont_json, confidence, source, approved, created_at) "
            "VALUES (?,?,?,?,?,?,?,?,?, COALESCE((SELECT created_at FROM rules WHERE rule_code=?), ?))",
            (
                rule_code,
                project_id,
                category,
                condition,
                rule_text,
                json.dumps(dont or []),
                confidence,
                source,
                int(approved),
                rule_code,
                now,
            ),
        )
        return self.get(rule_code)

    def get(self, rule_code: str) -> Rule:
        row = self.db.query_one("SELECT * FROM rules WHERE rule_code = ?", (rule_code,))
        if not row:
            raise LookupError(rule_code)
        return self._from_row(row)

    def list_approved(self, project_id: int | None = None) -> list[Rule]:
        rows = self.db.query(
            "SELECT * FROM rules WHERE approved = 1 AND deprecated = 0"
            " AND (project_id IS NULL OR project_id = ?)"
            " ORDER BY id",
            (project_id,),
        )
        return [self._from_row(r) for r in rows]

    def search(self, keywords: list[str], project_id: int | None = None) -> list[Rule]:
        rules = self.list_approved(project_id)
        if not keywords:
            return rules
        lowered = [k.lower() for k in keywords]
        matched = []
        for rule in rules:
            haystack = f"{rule.category} {rule.rule_text} {rule.condition or ''}".lower()
            if any(k in haystack for k in lowered):
                matched.append(rule)
        return matched

    @staticmethod
    def _from_row(row) -> Rule:
        return Rule(
            id=row["id"],
            rule_code=row["rule_code"],
            category=row["category"],
            rule_text=row["rule_text"],
            condition=row["condition_text"],
            dont=json.loads(row["dont_json"] or "[]"),
            confidence=row["confidence"],
            source=row["source"],
            approved=bool(row["approved"]),
            project_id=row["project_id"],
            created_at=row["created_at"],
        )
