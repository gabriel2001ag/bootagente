"""SeniorService: selects a SeniorProvider from config and records every
call in `senior_sessions` for auditing (seção 27).
"""
from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime, timezone
from typing import Any

from brain.database import Database
from core.config import BrainConfig
from core.enums import SeniorStatus
from core.task import Task
from senior.codex_provider import CodexProvider
from senior.mock_provider import MockSeniorProvider
from senior.provider import PatchProposal, SeniorAnalysisResult, SeniorProvider, SeniorReviewResult


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def build_provider(config: BrainConfig) -> SeniorProvider:
    provider_name = config.senior.provider.lower()
    if provider_name in ("codex", "codex-vscode"):
        return CodexProvider()
    if provider_name == "mock":
        return MockSeniorProvider(availability=SeniorStatus(config.senior.mock_availability))
    raise ValueError(f"Unknown senior provider: {provider_name!r}")


class SeniorService:
    def __init__(self, db: Database, config: BrainConfig, provider: SeniorProvider | None = None):
        self.db = db
        self.config = config
        self.provider = provider or build_provider(config)

    def check_availability(self) -> SeniorStatus:
        if not self.config.senior.enabled:
            return SeniorStatus.UNAVAILABLE
        try:
            return self.provider.check_availability()
        except Exception:
            return SeniorStatus.UNKNOWN_ERROR

    def analyze(self, task: Task, context: Any) -> SeniorAnalysisResult:
        result = self.provider.analyze(task, context)
        self._record_session(
            task.id, "AVAILABLE",
            request={"task_id": task.id, "title": task.title},
            response={"decision": result.decision.value, "confidence": result.confidence, "summary": result.summary},
        )
        return result

    def review(self, task: Task, patch: PatchProposal, context: Any) -> SeniorReviewResult:
        result = self.provider.review(task, patch, context)
        self._record_session(
            task.id, "AVAILABLE",
            request={"task_id": task.id, "patch_files": patch.files},
            response={"approved": result.approved, "comments": result.comments},
        )
        return result

    def _record_session(self, task_id: int | None, status: str, request: dict, response: dict) -> None:
        self.db.execute(
            "INSERT INTO senior_sessions(task_id, provider, status, request_json, response_json, created_at)"
            " VALUES (?,?,?,?,?,?)",
            (task_id, self.provider.name, status, json.dumps(request), json.dumps(response), _now()),
        )
