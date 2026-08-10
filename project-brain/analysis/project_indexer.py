"""ProjectIndexer: orchestrates CodeScanner + DependencyMapper and persists
into `files` / `symbols` / `relationships` (seções 18, 19).

Incremental: files whose hash didn't change are not re-inserted (existing
row + symbols are reused as-is) to keep re-indexing cheap on large repos.
"""
from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from analysis.code_scanner import IgnoreMatcher, ScanSkip, scan_project
from analysis.dependency_mapper import map_relationships
from brain.database import Database
from core.config import IndexingConfig


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass
class IndexStats:
    files_scanned: int
    files_indexed: int
    files_unchanged: int
    symbols_indexed: int
    relationships_indexed: int
    primary_language: str | None
    files_skipped: int = 0


class ProjectIndexer:
    def __init__(self, db: Database, config: IndexingConfig | None = None):
        self.db = db
        self.config = config or IndexingConfig()

    def clear(self, project_id: int, connection: sqlite3.Connection | None = None) -> None:
        """Clear only derived index data, atomically preserving project memory/tasks."""
        def clear_with(conn: sqlite3.Connection) -> None:
            conn.execute(
                "DELETE FROM symbols WHERE file_id IN "
                "(SELECT id FROM files WHERE project_id = ?)",
                (project_id,),
            )
            conn.execute("DELETE FROM relationships WHERE project_id = ?", (project_id,))
            conn.execute("DELETE FROM files WHERE project_id = ?", (project_id,))
            conn.execute("DELETE FROM index_skips WHERE project_id = ?", (project_id,))
        if connection is not None:
            clear_with(connection)
            return
        with self.db.conn:
            clear_with(self.db.conn)

    def rebuild(self, project_id: int, project_root: Path) -> IndexStats:
        """Replace the complete derived index in one rollback-safe transaction."""
        with self.db.conn:
            self.clear(project_id, connection=self.db.conn)
            return self.index(project_id, project_root, connection=self.db.conn)

    def index(
        self,
        project_id: int,
        project_root: Path,
        connection: sqlite3.Connection | None = None,
    ) -> IndexStats:
        execute = connection.execute if connection is not None else self.db.execute
        query = (
            lambda sql, params=(): list(connection.execute(sql, tuple(params)))
            if connection is not None
            else self.db.query(sql, params)
        )
        ignored_dirs, ignored_globs, sensitive_globs = self.config.for_project(project_id)
        matcher = IgnoreMatcher.from_config(ignored_dirs, ignored_globs, sensitive_globs)
        skipped: list[ScanSkip] = []
        scanned_files = scan_project(project_root, matcher=matcher, skipped=skipped)
        existing = {
            row["path"]: (row["id"], row["hash"])
            for row in query("SELECT id, path, hash FROM files WHERE project_id = ?", (project_id,))
        }

        indexed = 0
        unchanged = 0
        total_symbols = 0
        total_relationships = 0
        language_counts: dict[str, int] = {}
        now = _now()
        execute("DELETE FROM index_skips WHERE project_id = ?", (project_id,))
        for item in skipped:
            execute(
                "INSERT INTO index_skips(project_id, path, reason, observed_at) VALUES (?,?,?,?)",
                (project_id, item.path, item.reason, now),
            )

        # Clear relationships for this project and recompute; cheap enough
        # for V1 project sizes and avoids stale duplicate relationships.
        execute("DELETE FROM relationships WHERE project_id = ?", (project_id,))

        for scanned in scanned_files:
            if scanned.language:
                language_counts[scanned.language] = language_counts.get(scanned.language, 0) + 1

            prior = existing.get(scanned.path)
            if prior and prior[1] == scanned.hash:
                unchanged += 1
                file_id = prior[0]
            else:
                if prior:
                    file_id = prior[0]
                    execute(
                        "UPDATE files SET language=?, size=?, hash=?, last_modified=?, indexed_at=? WHERE id=?",
                        (scanned.language, scanned.size, scanned.hash, scanned.last_modified, now, file_id),
                    )
                    execute("DELETE FROM symbols WHERE file_id = ?", (file_id,))
                else:
                    cur = execute(
                        "INSERT INTO files(project_id, path, language, size, hash, last_modified, indexed_at)"
                        " VALUES (?,?,?,?,?,?,?)",
                        (project_id, scanned.path, scanned.language, scanned.size, scanned.hash,
                         scanned.last_modified, now),
                    )
                    file_id = cur.lastrowid
                for symbol in scanned.symbols:
                    execute(
                        "INSERT INTO symbols(file_id, symbol_type, name, class_name, line_start, line_end)"
                        " VALUES (?,?,?,?,?,?)",
                        (file_id, symbol.symbol_type, symbol.name, symbol.class_name,
                         symbol.line_start, symbol.line_end),
                    )
                indexed += 1
            total_symbols += len(scanned.symbols)

            if scanned.language == "php":
                try:
                    text = scanned.absolute_path.read_text(encoding="utf-8", errors="replace")
                except OSError:
                    text = ""
                for rel in map_relationships(scanned, text):
                    execute(
                        "INSERT INTO relationships(project_id, from_type, from_name, relation, to_type, "
                        "to_name, meta_json) VALUES (?,?,?,?,?,?,?)",
                        (project_id, rel.from_type, rel.from_name, rel.relation, rel.to_type,
                         rel.to_name, json.dumps(rel.meta)),
                    )
                    total_relationships += 1

        # Remove DB rows for files that disappeared from disk.
        current_paths = {f.path for f in scanned_files}
        stale_paths = set(existing.keys()) - current_paths
        for stale_path in stale_paths:
            file_id, _ = existing[stale_path]
            execute("DELETE FROM symbols WHERE file_id = ?", (file_id,))
            execute("DELETE FROM files WHERE id = ?", (file_id,))

        primary_language = max(language_counts, key=language_counts.get) if language_counts else None

        return IndexStats(
            files_scanned=len(scanned_files),
            files_indexed=indexed,
            files_unchanged=unchanged,
            symbols_indexed=total_symbols,
            relationships_indexed=total_relationships,
            primary_language=primary_language,
            files_skipped=len(skipped),
        )
