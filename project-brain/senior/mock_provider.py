"""MockSeniorProvider (seção 29, item 14): the only Senior provider shipped
in V1.

Lets us build and test the whole architecture (availability handling,
context building, learning extraction) without any external dependency.
Availability and canned responses are configurable, both for CLI demos
("senior online" vs "senior offline") and for tests.
"""
from __future__ import annotations

from typing import Any

from core.enums import Decision, SeniorStatus
from core.task import Task
from senior.provider import (
    LearningPayload,
    PatchProposal,
    SeniorAnalysisResult,
    SeniorProvider,
    SeniorReviewResult,
)


class MockSeniorProvider(SeniorProvider):
    name = "mock"

    def __init__(
        self,
        availability: SeniorStatus = SeniorStatus.AVAILABLE,
        canned_decision: Decision = Decision.PATCH_REQUIRES_REVIEW,
        canned_confidence: float = 0.9,
        auto_approve_reviews: bool = True,
    ):
        self.availability = availability
        self.canned_decision = canned_decision
        self.canned_confidence = canned_confidence
        self.auto_approve_reviews = auto_approve_reviews

    def check_availability(self) -> SeniorStatus:
        return self.availability

    def analyze(self, task: Task, context: Any) -> SeniorAnalysisResult:
        summary = (
            f"[MockSeniorProvider] Analyzed task '{task.title}'. "
            "This is a simulated Senior response for V1 architecture testing; "
            "no real LLM reasoning is involved."
        )
        learning = self.extract_learning(task, None)
        return SeniorAnalysisResult(
            decision=self.canned_decision,
            confidence=self.canned_confidence,
            summary=summary,
            proposed_patch=None,  # V1 never materializes real patches
            learning=learning,
            raw={"mock": True, "task_id": task.id},
        )

    def review(self, task: Task, patch: PatchProposal, context: Any) -> SeniorReviewResult:
        return SeniorReviewResult(
            approved=self.auto_approve_reviews,
            comments="[MockSeniorProvider] simulated review — auto-approved for V1 demo purposes"
            if self.auto_approve_reviews
            else "[MockSeniorProvider] simulated rejection for V1 demo purposes",
        )

    def extract_learning(self, task: Task, result: SeniorAnalysisResult | None) -> LearningPayload:
        """Implements the seção 12 contract with a deterministic, canned
        payload derived from the task — good enough to exercise
        LearningExtractor end-to-end without a real LLM."""
        return LearningPayload(
            lessons=[
                {
                    "problem": task.title,
                    "solution": f"Reviewed via MockSeniorProvider for task #{task.id}",
                    "category": task.category or "general",
                    "files": [],
                }
            ],
            rules=[],
            patterns=[],
            affected_modules=[],
            risks=[],
            important_files=[],
        )
