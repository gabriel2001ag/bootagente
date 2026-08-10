"""CodexProvider: placeholder for the real Codex/API integration.

Explicitly a V2 item (seção 30). This file exists to match the directory
layout in seção 4 and to make the abstraction concrete, but it does NOT
call any external API in V1. `check_availability()` always returns
UNAVAILABLE with a clear reason rather than silently pretending to work,
and the other methods raise `NotImplementedError` so a caller can never
mistake this for a working integration.
"""
from __future__ import annotations

from typing import Any

from core.enums import SeniorStatus
from core.task import Task
from senior.provider import (
    LearningPayload,
    PatchProposal,
    SeniorAnalysisResult,
    SeniorProvider,
    SeniorReviewResult,
)


class CodexProvider(SeniorProvider):
    name = "codex"

    def __init__(self, api_key: str | None = None, base_url: str | None = None):
        self.api_key = api_key
        self.base_url = base_url

    def check_availability(self) -> SeniorStatus:
        return SeniorStatus.UNAVAILABLE

    def analyze(self, task: Task, context: Any) -> SeniorAnalysisResult:
        raise NotImplementedError(
            "CodexProvider.analyze is not implemented in V1 — use MockSeniorProvider. "
            "See ARCHITECTURE.md 'Adiado para a Segunda Entrega'."
        )

    def review(self, task: Task, patch: PatchProposal, context: Any) -> SeniorReviewResult:
        raise NotImplementedError("CodexProvider.review is not implemented in V1.")

    def extract_learning(self, task: Task, result: SeniorAnalysisResult) -> LearningPayload:
        raise NotImplementedError("CodexProvider.extract_learning is not implemented in V1.")
