"""Deterministic similarity engine (seção 16).

Explicitly NOT embeddings/neural — a small, auditable, swappable interface.
`KeywordSimilarityEngine` scores overlap of tokens (title+description),
category and touched-file basenames, using fixed weights. Future engines
can implement the same `SimilarityEngine` interface without touching the
rest of the system.
"""
from __future__ import annotations

import re
from abc import ABC, abstractmethod

from core.task import Task

_STOPWORDS = {
    "a", "o", "os", "as", "de", "da", "do", "das", "dos", "para", "com",
    "em", "no", "na", "nos", "nas", "um", "uma", "e", "ou", "que", "se",
    "the", "a", "an", "of", "to", "for", "in", "on", "and", "or",
}

_TOKEN_RE = re.compile(r"[a-zA-Z0-9_À-ÿ]+")


def tokenize(text: str) -> set[str]:
    tokens = {t.lower() for t in _TOKEN_RE.findall(text or "")}
    return {t for t in tokens if t not in _STOPWORDS and len(t) > 2}


class SimilarityEngine(ABC):
    @abstractmethod
    def compare(self, task: Task, previous_task: Task) -> float:
        """Return a deterministic similarity score in [0, 1]."""


class KeywordSimilarityEngine(SimilarityEngine):
    """Bag-of-tokens overlap with category boost, per seção 16 exemplo."""

    def __init__(
        self,
        text_weight: float = 0.6,
        category_weight: float = 0.3,
        source_weight: float = 0.1,
        concept_expander=None,
    ):
        self.text_weight = text_weight
        self.category_weight = category_weight
        self.source_weight = source_weight
        self.concept_expander = concept_expander

    def compare(self, task: Task, previous_task: Task) -> float:
        tokens_a = tokenize(f"{task.title} {task.description}")
        tokens_b = tokenize(f"{previous_task.title} {previous_task.description}")
        if self.concept_expander is not None:
            tokens_a = set(self.concept_expander.expand(
                f"{task.title} {task.description}"
            ).expanded_tokens)
            tokens_b = set(self.concept_expander.expand(
                f"{previous_task.title} {previous_task.description}"
            ).expanded_tokens)
        text_score = self._jaccard(tokens_a, tokens_b)

        category_score = 1.0 if task.category == previous_task.category and task.category != "unknown" else 0.0
        source_score = 1.0 if task.source == previous_task.source else 0.0
        # Provenance is only a tie-breaker; it cannot create similarity alone.
        if text_score == 0.0 and category_score == 0.0:
            source_score = 0.0

        score = (
            text_score * self.text_weight
            + category_score * self.category_weight
            + source_score * self.source_weight
        )
        return round(min(1.0, max(0.0, score)), 4)

    @staticmethod
    def _jaccard(a: set[str], b: set[str]) -> float:
        if not a and not b:
            return 0.0
        intersection = len(a & b)
        union = len(a | b)
        return intersection / union if union else 0.0
