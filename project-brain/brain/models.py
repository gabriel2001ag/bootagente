"""Plain dataclasses mirroring SQLite rows (seções 6, 18, 19).

Kept intentionally simple: no ORM. Repositories in this package convert
`sqlite3.Row` <-> dataclass explicitly, which keeps SQL visible and easy to
audit (seção 32: interfaces claras, baixo acoplamento).
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Project:
    id: int
    name: str
    path: str
    vcs: str
    primary_language: str | None
    created_at: str
    updated_at: str
    last_indexed_at: str | None = None


@dataclass
class FileRecord:
    id: int
    project_id: int
    path: str
    language: str | None
    size: int
    hash: str | None
    last_modified: str | None
    indexed_at: str


@dataclass
class Symbol:
    id: int
    file_id: int
    symbol_type: str
    name: str
    class_name: str | None
    line_start: int | None
    line_end: int | None


@dataclass
class Relationship:
    id: int
    project_id: int
    from_type: str
    from_name: str
    relation: str
    to_type: str
    to_name: str
    meta: dict = field(default_factory=dict)


@dataclass
class Patch:
    id: int
    task_id: int
    commit_before: str | None
    commit_after: str | None
    diff: str | None
    metadata: dict = field(default_factory=dict)
    created_at: str = ""


@dataclass
class Review:
    id: int
    task_id: int
    patch_id: int | None
    reviewer: str
    decision: str
    comments: str | None
    created_at: str = ""


@dataclass
class TestResult:
    id: int
    task_id: int
    tool: str
    command: str | None
    exit_code: int | None
    passed: bool
    output: str | None
    created_at: str = ""


@dataclass
class SeniorSession:
    id: int
    task_id: int | None
    provider: str
    status: str
    request: dict = field(default_factory=dict)
    response: dict = field(default_factory=dict)
    created_at: str = ""
