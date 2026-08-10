"""ValidationAgent: recognizes known validation-related task patterns
(seção 17).

Only ever reports a match + confidence; never edits code by itself (that is
explicitly out of scope for V1 — see ARCHITECTURE.md "Adiado para V2").
"""
from __future__ import annotations

from dataclasses import dataclass

from agents.base_agent import Agent, AgentResult
from core.enums import AgentResultStatus
from core.task import Task

# trigger -> keywords that hint at it, in task title/description (pt-BR + en)
KNOWN_TRIGGERS: dict[str, list[str]] = {
    "required": ["obrigatorio", "obrigatório", "required", "campo vazio"],
    "numeric_range": [
        "limitar", "limite", "maximo", "máximo", "minimo", "mínimo",
        "intervalo", "range", "no maximo", "no máximo",
    ],
    "greater_than": ["maior que", "greater than", "acima de"],
    "less_than": ["menor que", "less than", "abaixo de"],
    "duplicate_prevention": ["duplicado", "duplicidade", "duplicate", "nao repetir", "não repetir"],
}


@dataclass
class ValidationMatch:
    trigger: str
    matched_keywords: list[str]


class ValidationAgent(Agent):
    name = "validation_agent"

    def detect(self, task: Task) -> list[ValidationMatch]:
        haystack = f"{task.title} {task.description}".lower()
        matches: list[ValidationMatch] = []
        for trigger, keywords in KNOWN_TRIGGERS.items():
            hit = [kw for kw in keywords if kw in haystack]
            if hit:
                matches.append(ValidationMatch(trigger=trigger, matched_keywords=hit))
        return matches

    def run(self, task: Task, context) -> AgentResult:
        matches = self.detect(task)
        if not matches:
            return AgentResult(
                AgentResultStatus.NO_MATCH, 0.0,
                "no known validation trigger recognized in task text",
            )
        # More matched triggers / keywords => higher confidence, capped.
        strength = sum(len(m.matched_keywords) for m in matches)
        confidence = min(0.9, 0.5 + 0.1 * strength)
        return AgentResult(
            AgentResultStatus.OK,
            confidence=confidence,
            message=f"recognized validation trigger(s): {', '.join(m.trigger for m in matches)}",
            data={"triggers": [m.trigger for m in matches]},
        )
