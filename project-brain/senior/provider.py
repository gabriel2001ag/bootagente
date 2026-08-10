"""SeniorProvider abstraction (seção 13/14).

The rest of the system (Orchestrator, CLI) only ever talks to this
interface — never to a concrete LLM SDK — so `CodexProvider`,
`ClaudeProvider`, `OpenAIProvider`, etc. can be added later (V2) without
touching Orchestrator code.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from core.enums import Decision, SeniorStatus
from core.task import Task


@dataclass
class PatchProposal:
    """A proposed change. V1 never materializes a real diff (see
    ARCHITECTURE.md — patch automation is a V2 feature); this exists so the
    `review()` contract is stable when V2 adds real patches."""

    files: list[str] = field(default_factory=list)
    diff: str | None = None
    description: str = ""


@dataclass
class SeniorAnalysisResult:
    decision: Decision
    confidence: float
    summary: str
    proposed_patch: PatchProposal | None = None
    learning: "LearningPayload | None" = None
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass
class SeniorReviewResult:
    approved: bool
    comments: str
    learning: "LearningPayload | None" = None


@dataclass
class LearningPayload:
    """The structured-output contract from seção 12."""

    lessons: list[dict] = field(default_factory=list)
    rules: list[dict] = field(default_factory=list)
    patterns: list[dict] = field(default_factory=list)
    affected_modules: list[str] = field(default_factory=list)
    risks: list[str] = field(default_factory=list)
    important_files: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "lessons": self.lessons,
            "rules": self.rules,
            "patterns": self.patterns,
            "affected_modules": self.affected_modules,
            "risks": self.risks,
            "important_files": self.important_files,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "LearningPayload":
        return cls(
            lessons=data.get("lessons", []),
            rules=data.get("rules", []),
            patterns=data.get("patterns", []),
            affected_modules=data.get("affected_modules", []),
            risks=data.get("risks", []),
            important_files=data.get("important_files", []),
        )


class SeniorProvider(ABC):
    name: str = "provider"

    @abstractmethod
    def check_availability(self) -> SeniorStatus:
        """Never assume "internet available" == "senior available" (seção 14)."""

    @abstractmethod
    def analyze(self, task: Task, context: Any) -> SeniorAnalysisResult:
        ...

    @abstractmethod
    def review(self, task: Task, patch: PatchProposal, context: Any) -> SeniorReviewResult:
        ...

    @abstractmethod
    def extract_learning(self, task: Task, result: SeniorAnalysisResult) -> LearningPayload:
        ...
