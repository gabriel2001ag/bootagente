"""PHPAgent: conservative PHP code location, no editing (seção 17).

V1 uses the regex-based symbol index built by `analysis/code_scanner.py`
(already persisted in `symbols`) instead of a real AST. This is
intentional: the spec explicitly forbids "regex cega para alterações
perigosas" (blind regex for dangerous edits) — so this agent only ever
*locates* classes/methods, it never rewrites files. Real AST-backed
transformations (e.g. via `nikic/php-parser`) are a V2 item.
"""
from __future__ import annotations

from dataclasses import dataclass

from agents.base_agent import Agent, AgentResult
from brain.database import Database
from core.enums import AgentResultStatus
from core.task import Task


@dataclass
class SymbolLocation:
    file: str
    symbol_type: str
    name: str
    class_name: str | None
    line_start: int | None


class PHPAgent(Agent):
    name = "php_agent"

    def __init__(self, db: Database, project_id: int):
        self.db = db
        self.project_id = project_id

    def find_class(self, class_name: str) -> list[SymbolLocation]:
        rows = self.db.query(
            "SELECT f.path AS path, s.symbol_type, s.name, s.class_name, s.line_start "
            "FROM symbols s JOIN files f ON f.id = s.file_id "
            "WHERE f.project_id = ? AND s.symbol_type = 'class' AND s.name = ?",
            (self.project_id, class_name),
        )
        return [SymbolLocation(r["path"], r["symbol_type"], r["name"], r["class_name"], r["line_start"]) for r in rows]

    def find_method(self, method_name: str, class_name: str | None = None) -> list[SymbolLocation]:
        if class_name:
            rows = self.db.query(
                "SELECT f.path AS path, s.symbol_type, s.name, s.class_name, s.line_start "
                "FROM symbols s JOIN files f ON f.id = s.file_id "
                "WHERE f.project_id = ? AND s.symbol_type = 'method' AND s.name = ? AND s.class_name = ?",
                (self.project_id, method_name, class_name),
            )
        else:
            rows = self.db.query(
                "SELECT f.path AS path, s.symbol_type, s.name, s.class_name, s.line_start "
                "FROM symbols s JOIN files f ON f.id = s.file_id "
                "WHERE f.project_id = ? AND s.symbol_type = 'method' AND s.name = ?",
                (self.project_id, method_name),
            )
        return [SymbolLocation(r["path"], r["symbol_type"], r["name"], r["class_name"], r["line_start"]) for r in rows]

    def run(self, task: Task, context) -> AgentResult:
        candidate_files = getattr(context, "candidate_files", None) or []
        php_files = [f for f in candidate_files if f.endswith(".php")]
        if not php_files:
            return AgentResult(AgentResultStatus.NO_MATCH, 0.0, "no PHP candidate files in context")

        locations: list[dict] = []
        for path in php_files:
            rows = self.db.query(
                "SELECT s.symbol_type, s.name, s.class_name, s.line_start FROM symbols s "
                "JOIN files f ON f.id = s.file_id WHERE f.project_id = ? AND f.path = ?",
                (self.project_id, path),
            )
            for r in rows:
                locations.append(
                    {"file": path, "symbol_type": r["symbol_type"], "name": r["name"],
                     "class_name": r["class_name"], "line_start": r["line_start"]}
                )

        if not locations:
            return AgentResult(
                AgentResultStatus.NO_MATCH, 0.2,
                "candidate PHP files found but no indexed symbols in them",
                data={"files": php_files},
            )

        return AgentResult(
            AgentResultStatus.OK, 0.5,
            f"located {len(locations)} symbol(s) in {len(php_files)} candidate PHP file(s); "
            "no automatic code edit performed (V1 is analysis-only, see ARCHITECTURE.md)",
            data={"locations": locations},
        )
