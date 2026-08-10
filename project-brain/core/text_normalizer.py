"""Deterministic, conservative Portuguese text normalization (PLN layer).

Used only for free-form chat messages, never for code identifiers, file
paths, table names or class names — those are never routed through this
normalizer, so `tab_pedido` / `NfeInutilizacaoRegra` style tokens are safe
by construction, not by a special-casing rule here.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

_PUNCT_RE = re.compile(r"[^\w\s]")
_SPACE_RE = re.compile(r"\s+")
# Conservative, explicit collapse of hyphenated Brazilian fiscal document
# codes (NF-e, NFC-e, CT-e, CF-e, MDF-e, BP-e) to their concatenated form.
# Scoped to this known whitelist only — never a generic hyphen stripper.
_DOCUMENT_CODE_RE = re.compile(r"\b(nfc|nf|ct|cf|mdf|bp)-e\b")

DEFAULT_REPLACEMENTS: dict[str, str] = {
    "vc": "voce",
    "vcs": "voces",
    "oq": "o que",
    "pq": "porque",
    "analize": "analise",
    "analizar": "analisar",
    "concerte": "conserte",
    "ero": "erro",
    "brench": "branch",
}


def strip_accents(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text)
    return "".join(char for char in normalized if not unicodedata.combining(char))


@dataclass(frozen=True)
class NormalizationResult:
    raw_text: str
    normalized_text: str


class PortugueseTextNormalizer:
    """Lowercase + accent-strip + conservative whole-token replacement.

    Replacements only ever match a *whole* token, never a substring, so a
    token like "vc" is rewritten but "svc" or "vc_config" are left intact.
    """

    def __init__(self, replacements: dict[str, str] | None = None):
        table = DEFAULT_REPLACEMENTS if replacements is None else replacements
        self.replacements = {key.lower(): value.lower() for key, value in table.items()}

    def normalize(self, text: str) -> str:
        lowered = strip_accents(text.lower())
        lowered = _DOCUMENT_CODE_RE.sub(lambda m: f"{m.group(1)}e", lowered)
        cleaned = _PUNCT_RE.sub(" ", lowered)
        tokens = [t for t in _SPACE_RE.sub(" ", cleaned).strip().split(" ") if t]
        expanded: list[str] = []
        for token in tokens:
            expanded.extend(self.replacements.get(token, token).split(" "))
        return " ".join(expanded)

    def interpret(self, text: str) -> NormalizationResult:
        return NormalizationResult(raw_text=text, normalized_text=self.normalize(text))
