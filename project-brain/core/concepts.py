"""Configurable deterministic concept expansion used by V3 retrieval."""
from __future__ import annotations

from dataclasses import dataclass

from brain.similarity import tokenize


@dataclass(frozen=True)
class ConceptMatch:
    concepts: frozenset[str]
    expanded_tokens: frozenset[str]


class ConceptExpander:
    def __init__(
        self,
        groups: dict[str, list[str]],
        aliases: dict[str, str] | None = None,
        relationships: dict[str, dict[str, float]] | None = None,
        relationship_threshold: float = 0.5,
    ):
        self.groups = {
            name.lower(): {token for value in values for token in tokenize(value)}
            for name, values in groups.items()
        }
        self.aliases = {key.lower(): value.lower() for key, value in (aliases or {}).items()}
        self.relationships = relationships or {}
        self.relationship_threshold = relationship_threshold

    def expand(self, text: str) -> ConceptMatch:
        tokens = set(tokenize(text))
        concepts: set[str] = set()
        for token in tokens:
            alias = self.aliases.get(token)
            if alias:
                concepts.add(alias)
        for name, vocabulary in self.groups.items():
            if tokens & vocabulary:
                concepts.add(name)
        related = {
            target.lower()
            for concept in concepts
            for target, weight in self.relationships.get(concept, {}).items()
            if weight >= self.relationship_threshold
        }
        return ConceptMatch(frozenset(concepts), frozenset(tokens | concepts | related))
