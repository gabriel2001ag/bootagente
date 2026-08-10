"""Local fallback pipeline: CLASSIFY -> SEARCH MEMORY -> SIMILAR TASKS ->
PATTERNS -> CALCULATE CONFIDENCE -> DECISION (seção 15).

This is what runs when the Senior is unavailable. It never writes to the
target project; it produces a decision + supporting analysis. If confidence
is too low, it returns REQUIRES_SENIOR and touches nothing, per seção 2 and
seção 26 ("No files were modified.").
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from agents.database_agent import DatabaseAgent
from agents.php_agent import PHPAgent
from agents.qa_agent import QAAgent
from agents.validation_agent import ValidationAgent
from brain.database import Database
from core.config import BrainConfig
from core.context_builder import TaskContext
from core.enums import Decision, TaskCategory
from core.task import Task
from core.concepts import ConceptExpander
from core.routing import ConfidenceEngine, SmartRouter, TaskClassifier
from core.enums import SeniorStatus

_DB_KEYWORDS = ("tabela", "table", "migration", "migração", "banco de dados", "coluna", "campo fk", "foreign key")


@dataclass
class LocalExecutionResult:
    category: str
    confidence: float
    decision: Decision
    message: str
    signals: dict = field(default_factory=dict)
    agent_findings: dict = field(default_factory=dict)
    files_modified: list[str] = field(default_factory=list)  # always empty in V1


def classify(task: Task, validation_hit: bool, config: BrainConfig | None = None) -> str:
    haystack = f"{task.title} {task.description}".lower()
    if validation_hit:
        return TaskCategory.VALIDATION.value
    if any(k in haystack for k in _DB_KEYWORDS):
        return TaskCategory.DATABASE.value
    if any(k in haystack for k in ("tela", "view", "layout", "botao", "botão", "ui")):
        return TaskCategory.UI.value
    if any(k in haystack for k in ("bug", "erro", "corrigir", "fix")):
        return TaskCategory.BUGFIX.value
    cfg = config or BrainConfig()
    expander = ConceptExpander(
        cfg.concepts.groups, cfg.concepts.aliases, cfg.concepts.relationships
    )
    return TaskClassifier(expander).classify(task, validation_hit).category


def calculate_confidence(
    context: TaskContext, validation_confidence: float, config: BrainConfig | None = None
) -> dict:
    cfg = config or BrainConfig()
    expander = ConceptExpander(
        cfg.concepts.groups, cfg.concepts.aliases, cfg.concepts.relationships
    )
    concept_count = len(expander.expand(
        f"{context.task.title} {context.task.description}"
    ).concepts)
    result = ConfidenceEngine().calculate(context, validation_confidence, concept_count)
    return {
        "confidence": result.confidence,
        "best_similar_task_score": result.signals["similarity"],
        "rules_signal": result.signals["rules"],
        "patterns_signal": result.signals["patterns"],
        "lessons_signal": result.signals["lessons"],
        "validation_confidence": result.signals["validation"],
        "concepts_signal": result.signals["concepts"],
        "reasons": list(result.reasons),
    }


def try_execute(
    task: Task,
    context: TaskContext,
    config: BrainConfig,
    db: Database,
    project_id: int,
    project_root: Path,
) -> LocalExecutionResult:
    validation_agent = ValidationAgent()
    validation_result = validation_agent.run(task, context)
    validation_hit = validation_result.status.value == "OK"

    category = classify(task, validation_hit, config)
    signals = calculate_confidence(context, validation_result.confidence, config)
    confidence = signals["confidence"]
    decision = config.decision_for_confidence(confidence)
    expander = ConceptExpander(
        config.concepts.groups, config.concepts.aliases, config.concepts.relationships
    )
    classification = TaskClassifier(expander).classify(task, validation_hit)
    route = SmartRouter().route(classification, confidence, SeniorStatus.UNAVAILABLE)
    signals["classification"] = {
        "category": classification.category,
        "intent": classification.intent,
        "concepts": list(classification.concepts),
        "reasons": list(classification.reasons),
    }
    signals["route"] = {"mode": route.mode.value, "reason": route.reason}

    findings: dict = {"validation_agent": validation_result.__dict__}

    if decision == Decision.REQUIRES_SENIOR:
        return LocalExecutionResult(
            category=category,
            confidence=confidence,
            decision=decision,
            message=(
                "Local confidence too low for autonomous action. "
                "No files were modified. REQUIRES_SENIOR."
            ),
            signals=signals,
            agent_findings=findings,
        )

    # Confidence is high enough to at least analyze in depth (never edit).
    php_agent = PHPAgent(db, project_id)
    php_result = php_agent.run(task, context)
    findings["php_agent"] = php_result.__dict__

    db_agent = DatabaseAgent(project_root)
    if category == TaskCategory.DATABASE.value:
        db_result = db_agent.run(task, context)
        findings["database_agent"] = db_result.__dict__

    qa_agent = QAAgent(
        project_root,
        run_composer_test=config.qa.run_composer_test,
        run_phpunit=config.qa.run_phpunit,
    )
    if config.qa.run_php_lint and context.candidate_files:
        qa_result = qa_agent.run(task, context)
        findings["qa_agent"] = qa_result.__dict__

    message = {
        Decision.AUTO_EXECUTE_ALLOWED: "High local confidence. In V1, no automatic edit is performed "
                                        "(patch automation is a V2 feature) — recommendation only.",
        Decision.PATCH_REQUIRES_REVIEW: "Local agents found a plausible match; a human/Senior review "
                                         "is required before any patch would be applied.",
        Decision.ANALYSIS_ONLY: "Confidence is moderate: analysis only, no patch suggested.",
    }[decision]

    return LocalExecutionResult(
        category=category,
        confidence=confidence,
        decision=decision,
        message=message,
        signals=signals,
        agent_findings=findings,
    )
