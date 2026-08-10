"""Explainable deterministic classification, confidence, and routing."""
from __future__ import annotations

from dataclasses import dataclass, field

from core.concepts import ConceptExpander
from core.enums import RoutingMode, SeniorStatus, TaskCategory
from core.task import Task


@dataclass(frozen=True)
class Classification:
    category: str
    concepts: tuple[str, ...]
    intent: str
    reasons: tuple[str, ...] = ()


class TaskClassifier:
    def __init__(self, expander: ConceptExpander):
        self.expander = expander

    def classify(self, task: Task, validation_hit: bool = False) -> Classification:
        match = self.expander.expand(f"{task.title} {task.description}")
        concepts = set(match.concepts)
        if validation_hit:
            category = TaskCategory.VALIDATION.value
        elif "finance" in concepts or "inventory" in concepts or "fiscal" in concepts:
            category = "business_flow"
        elif "orders" in concepts:
            category = "orders"
        else:
            category = TaskCategory.UNKNOWN.value
        intent = "analysis" if "analysis" in concepts else (
            "change" if "change" in concepts else "unknown"
        )
        reasons = tuple([f"concept:{item}" for item in sorted(concepts)])
        return Classification(category, tuple(sorted(concepts)), intent, reasons)


@dataclass(frozen=True)
class ConfidenceResult:
    confidence: float
    signals: dict[str, float] = field(default_factory=dict)
    reasons: tuple[str, ...] = ()


class ConfidenceEngine:
    weights = {
        "similarity": 0.30,
        "rules": 0.15,
        "patterns": 0.15,
        "lessons": 0.15,
        "validation": 0.15,
        "concepts": 0.10,
    }

    def calculate(self, context, validation_confidence: float, concept_count: int) -> ConfidenceResult:
        values = {
            "similarity": max((item.score for item in context.similar_tasks), default=0.0),
            "rules": min(1.0, len(context.rules) / 3),
            "patterns": min(1.0, len(context.patterns) / 2),
            "lessons": min(1.0, len(context.lessons) / 2),
            "validation": validation_confidence,
            "concepts": min(1.0, concept_count / 2),
        }
        confidence = round(sum(values[key] * weight for key, weight in self.weights.items()), 4)
        reasons = tuple(f"{key}={value:.4f} weight={self.weights[key]:.2f}" for key, value in values.items())
        return ConfidenceResult(confidence, values, reasons)


@dataclass(frozen=True)
class Route:
    mode: RoutingMode
    reason: str


class SmartRouter:
    def route(
        self, classification: Classification, confidence: float, senior_status: SeniorStatus
    ) -> Route:
        senior_available = senior_status in {
            SeniorStatus.AVAILABLE,
            SeniorStatus.MANUAL_HANDOFF,
        }
        if classification.intent == "analysis" and confidence >= 0.40:
            return Route(RoutingMode.ANALYSIS_ONLY, "analysis intent with sufficient local evidence")
        if confidence >= 0.80:
            return Route(
                RoutingMode.HYBRID if senior_available else RoutingMode.LOCAL,
                "strong deterministic evidence",
            )
        if senior_available:
            return Route(RoutingMode.SENIOR, "local confidence requires senior judgment")
        return Route(RoutingMode.WAITING_FOR_SENIOR, "senior unavailable and local confidence is low")
