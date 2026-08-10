"""Portuguese understanding layer (seção PLN).

Deterministic intent/action/domain/scope extraction, kept explicitly
separate from *knowledge* confidence (whether the Brain has rules/patterns/
lessons for the request). `Understanding.intent_confidence` answers "did I
parse what you asked?"; `ConfidenceEngine`'s existing blended score
(unchanged by this module) still answers "do I have evidence to act on it?".
Mixing the two was the root cause of low-confidence-looking-like-not-understood
responses this layer fixes.
"""
from __future__ import annotations

from dataclasses import dataclass

from core.concepts import ConceptExpander
from core.text_normalizer import PortugueseTextNormalizer

ACTION_ANALYZE = "ANALYZE"
ACTION_SHOW_STATUS = "SHOW_STATUS"
ACTION_FIX = "FIX"
ACTION_IMPLEMENT = "IMPLEMENT"

# Also reused by ChatService to inherit a prior turn's domain into a
# follow-up message ("e o que falta?") — each value is itself a literal
# member of that concept's vocabulary in config.yaml, so re-injecting it
# is guaranteed to re-trigger the same concept on expansion.
DOMAIN_TRIGGER_WORDS = {
    "fiscal": "fiscal",
    "finance": "financeiro",
    "inventory": "estoque",
    "orders": "pedidos",
}

_INTENT_BY_ACTION = {
    ACTION_ANALYZE: "ANALYSIS_TASK",
    ACTION_SHOW_STATUS: "ANALYSIS_TASK",
    ACTION_FIX: "IMPLEMENTATION_TASK",
    ACTION_IMPLEMENT: "IMPLEMENTATION_TASK",
}

_SCOPE_TOKENS = {"branch", "aqui"}


@dataclass(frozen=True)
class Understanding:
    raw_text: str
    normalized_text: str
    concepts: tuple[str, ...]
    domain: str | None
    action: str | None
    intent: str | None
    scope: tuple[str, ...]
    intent_confidence: float


class PortugueseNLP:
    def __init__(
        self,
        expander: ConceptExpander,
        normalizer: PortugueseTextNormalizer | None = None,
        actions: dict[str, list[str]] | None = None,
    ):
        self.expander = expander
        self.normalizer = normalizer or PortugueseTextNormalizer()
        self.actions = {
            name: sorted({phrase.lower() for phrase in phrases}, key=len, reverse=True)
            for name, phrases in (actions or {}).items()
        }

    def interpret(self, raw_text: str) -> Understanding:
        normalized = self.normalizer.normalize(raw_text)
        match = self.expander.expand(normalized)
        concepts = tuple(sorted(match.concepts))
        domain = next((DOMAIN_TRIGGER_WORDS[c] for c in concepts if c in DOMAIN_TRIGGER_WORDS), None)
        action = self._detect_action(normalized)
        intent = _INTENT_BY_ACTION.get(action) if action else None
        scope = ("CURRENT_BRANCH",) if set(normalized.split()) & _SCOPE_TOKENS else ()
        intent_confidence = self._confidence(concepts, action, scope)
        return Understanding(
            raw_text=raw_text,
            normalized_text=normalized,
            concepts=concepts,
            domain=domain,
            action=action,
            intent=intent,
            scope=scope,
            intent_confidence=intent_confidence,
        )

    def _detect_action(self, normalized: str) -> str | None:
        padded = f" {normalized} "
        best: tuple[int, str] | None = None
        for name, phrases in self.actions.items():
            for phrase in phrases:
                if f" {phrase} " in padded:
                    candidate = (len(phrase), name)
                    if best is None or candidate[0] > best[0]:
                        best = candidate
                    break
        return best[1] if best else None

    @staticmethod
    def _confidence(concepts: tuple[str, ...], action: str | None, scope: tuple[str, ...]) -> float:
        score = 0.0
        if concepts:
            score += 0.5
        if action:
            score += 0.4
        if scope:
            score += 0.1
        return round(min(1.0, score), 2)
