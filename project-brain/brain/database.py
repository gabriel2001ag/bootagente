"""SQLite connection + migration runner (seção 6).

Deliberately dependency-free: stdlib `sqlite3` only. Migrations are plain
`.sql` files under `migrations/`, applied once each, tracked in
`schema_migrations`.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any, Iterable


class Database:
    def __init__(self, db_path: Path, migrations_dir: Path, **sqlite_kwargs):
        self.db_path = db_path
        self.migrations_dir = migrations_dir
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(db_path), **sqlite_kwargs)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._ensure_migrations_table()
        self.apply_migrations()

    # -- migrations ---------------------------------------------------
    def _ensure_migrations_table(self) -> None:
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS schema_migrations ("
            "version TEXT PRIMARY KEY, applied_at TEXT NOT NULL)"
        )
        self._conn.commit()

    def apply_migrations(self) -> list[str]:
        applied: list[str] = []
        if not self.migrations_dir.exists():
            return applied
        already = {
            row["version"]
            for row in self._conn.execute("SELECT version FROM schema_migrations")
        }
        for sql_file in sorted(self.migrations_dir.glob("*.sql")):
            version = sql_file.stem
            if version in already:
                continue
            script = sql_file.read_text(encoding="utf-8")
            try:
                self._conn.executescript(script)
            except Exception:
                self._conn.rollback()
                raise
            self._conn.execute(
                "INSERT INTO schema_migrations(version, applied_at) VALUES (?, datetime('now'))",
                (version,),
            )
            self._conn.commit()
            applied.append(version)
        return applied

    # -- query helpers --------------------------------------------------
    @property
    def conn(self) -> sqlite3.Connection:
        return self._conn

    def execute(self, sql: str, params: Iterable[Any] = ()) -> sqlite3.Cursor:
        cur = self._conn.execute(sql, tuple(params))
        self._conn.commit()
        return cur

    def query(self, sql: str, params: Iterable[Any] = ()) -> list[sqlite3.Row]:
        return list(self._conn.execute(sql, tuple(params)))

    def query_one(self, sql: str, params: Iterable[Any] = ()) -> sqlite3.Row | None:
        rows = self.query(sql, params)
        return rows[0] if rows else None

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> "Database":
        return self

    def __exit__(self, *exc) -> None:
        self.close()
