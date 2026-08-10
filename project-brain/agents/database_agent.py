"""DatabaseAgent: read-only mapping of migrations/tables/fields/FKs/indexes
(seção 17 e 19).

Never executes DDL/DML. Parses CodeIgniter4-style migration files
(`$this->forge->...`) with regex — best-effort, safe to be incomplete.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from agents.base_agent import Agent, AgentResult
from core.enums import AgentResultStatus
from core.task import Task

_CREATE_TABLE_RE = re.compile(r"createTable\(\s*['\"](\w+)['\"]")
_ADD_FIELD_KEY_RE = re.compile(r"['\"](\w+)['\"]\s*=>\s*\[")
_ADD_FOREIGN_KEY_RE = re.compile(
    r"addForeignKey\(\s*['\"](\w+)['\"]\s*,\s*['\"](\w+)['\"]\s*,\s*['\"](\w+)['\"]"
)
_ADD_KEY_RE = re.compile(r"addKey\(\s*(\[[^\]]*\]|['\"][\w]+['\"])")
_ADD_FIELD_BLOCK_RE = re.compile(r"addField\(\s*\[(.*?)\]\s*\)", re.DOTALL)
_DROP_TABLE_RE = re.compile(r"dropTable\(\s*['\"](\w+)['\"]")


@dataclass
class MigrationInfo:
    file: str
    tables_created: list[str] = field(default_factory=list)
    tables_dropped: list[str] = field(default_factory=list)
    fields: dict[str, list[str]] = field(default_factory=dict)  # table -> field names
    foreign_keys: list[tuple[str, str, str]] = field(default_factory=list)  # (col, table, refcol)
    indexes: list[str] = field(default_factory=list)


MIGRATION_DIR_CANDIDATES = ("app/Database/Migrations", "database/migrations")


class DatabaseAgent(Agent):
    name = "database_agent"

    def __init__(self, project_root: Path):
        self.project_root = Path(project_root)

    def find_migration_dir(self) -> Path | None:
        for candidate in MIGRATION_DIR_CANDIDATES:
            path = self.project_root / candidate
            if path.exists() and path.is_dir():
                return path
        return None

    def parse_migration(self, file_path: Path) -> MigrationInfo:
        text = file_path.read_text(encoding="utf-8", errors="replace")
        info = MigrationInfo(file=str(file_path.relative_to(self.project_root).as_posix()))
        info.tables_created = _CREATE_TABLE_RE.findall(text)
        info.tables_dropped = _DROP_TABLE_RE.findall(text)
        for fk in _ADD_FOREIGN_KEY_RE.finditer(text):
            info.foreign_keys.append((fk.group(1), fk.group(2), fk.group(3)))
        for block in _ADD_FIELD_BLOCK_RE.finditer(text):
            field_names = _ADD_FIELD_KEY_RE.findall(block.group(1))
            table_hint = info.tables_created[0] if info.tables_created else "unknown"
            info.fields.setdefault(table_hint, []).extend(field_names)
        for key_match in _ADD_KEY_RE.finditer(text):
            info.indexes.append(key_match.group(1).strip())
        return info

    def map_all_migrations(self) -> list[MigrationInfo]:
        migration_dir = self.find_migration_dir()
        if not migration_dir:
            return []
        results = []
        for php_file in sorted(migration_dir.glob("*.php")):
            results.append(self.parse_migration(php_file))
        return results

    def run(self, task: Task, context) -> AgentResult:
        migrations = self.map_all_migrations()
        if not migrations:
            return AgentResult(
                AgentResultStatus.SKIPPED, 0.0,
                "no migrations directory found (app/Database/Migrations or database/migrations)",
            )
        tables = sorted({t for m in migrations for t in m.tables_created})
        return AgentResult(
            AgentResultStatus.OK, 0.6,
            f"mapped {len(migrations)} migration file(s), {len(tables)} table(s) (read-only)",
            data={"tables": tables, "migrations": [m.file for m in migrations]},
        )
