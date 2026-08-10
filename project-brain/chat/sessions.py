from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from brain.database import Database


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass
class ChatSession:
    id: int
    project_id: int
    status: str
    senior_mode: str
    created_at: str
    updated_at: str


@dataclass
class ChatMessage:
    id: int
    session_id: int
    role: str
    message: str
    task_id: int | None
    created_at: str


class ChatSessionRepository:
    """Stores conversation history without promoting it to project knowledge."""

    def __init__(self, db: Database):
        self.db = db

    def create(self, project_id: int, senior_mode: str = "ONLINE") -> ChatSession:
        now = _now()
        cur = self.db.execute(
            "INSERT INTO chat_sessions(project_id, status, senior_mode, created_at, updated_at)"
            " VALUES (?, 'ACTIVE', ?, ?, ?)",
            (project_id, senior_mode, now, now),
        )
        return self.get(cur.lastrowid)

    def get(self, session_id: int) -> ChatSession:
        row = self.db.query_one("SELECT * FROM chat_sessions WHERE id=?", (session_id,))
        if not row:
            raise LookupError(f"Chat session {session_id} not found")
        return ChatSession(**dict(row))

    def set_senior_mode(self, session_id: int, mode: str) -> ChatSession:
        mode = mode.upper()
        if mode not in {"ONLINE", "OFFLINE"}:
            raise ValueError("senior mode must be ONLINE or OFFLINE")
        self.db.execute(
            "UPDATE chat_sessions SET senior_mode=?, updated_at=? WHERE id=?",
            (mode, _now(), session_id),
        )
        return self.get(session_id)

    def close(self, session_id: int) -> None:
        self.db.execute(
            "UPDATE chat_sessions SET status='CLOSED', updated_at=? WHERE id=?",
            (_now(), session_id),
        )

    def add_message(
        self, session_id: int, role: str, message: str, task_id: int | None = None
    ) -> ChatMessage:
        role = role.lower()
        if role not in {"user", "assistant", "system"}:
            raise ValueError("invalid chat role")
        cur = self.db.execute(
            "INSERT INTO chat_messages(session_id, role, message, task_id, created_at)"
            " VALUES (?,?,?,?,?)",
            (session_id, role, message, task_id, _now()),
        )
        row = self.db.query_one("SELECT * FROM chat_messages WHERE id=?", (cur.lastrowid,))
        return ChatMessage(**dict(row))

    def recent(self, session_id: int, limit: int = 20) -> list[ChatMessage]:
        rows = self.db.query(
            "SELECT * FROM (SELECT * FROM chat_messages WHERE session_id=?"
            " ORDER BY id DESC LIMIT ?) ORDER BY id",
            (session_id, limit),
        )
        return [ChatMessage(**dict(row)) for row in rows]

