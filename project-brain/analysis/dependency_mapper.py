"""DependencyMapper: simple, best-effort relationship extraction (seção 19).

Deliberately narrow scope for V1: `extends`, `implements`, `new X(`
(USES), and CodeIgniter4-ish `$this->table = 'x'` (REFERENCES_TABLE).
The goal is reliable infrastructure over completeness — more relation
types can be added later without touching the schema.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from analysis.code_scanner import ScannedFile

_EXTENDS_RE = re.compile(r"class\s+(\w+)\s+extends\s+(\w+)")
_IMPLEMENTS_RE = re.compile(r"class\s+(\w+)\s+(?:extends\s+\w+\s+)?implements\s+([\w,\s]+)")
_NEW_RE = re.compile(r"\bnew\s+(\w+)\s*\(")
_TABLE_RE = re.compile(r"\$table\s*=\s*['\"](\w+)['\"]")
_TABLE_PROP_RE = re.compile(r"protected\s+\$table\s*=\s*['\"](\w+)['\"]")


@dataclass
class RawRelationship:
    from_type: str
    from_name: str
    relation: str
    to_type: str
    to_name: str
    meta: dict


def _class_name_of(scanned: ScannedFile) -> str | None:
    for symbol in scanned.symbols:
        if symbol.symbol_type == "class":
            return symbol.name
    return None


def map_relationships(scanned: ScannedFile, text: str) -> list[RawRelationship]:
    relationships: list[RawRelationship] = []
    class_name = _class_name_of(scanned)

    for match in _EXTENDS_RE.finditer(text):
        relationships.append(
            RawRelationship("class", match.group(1), "EXTENDS", "class", match.group(2), {"file": scanned.path})
        )

    for match in _IMPLEMENTS_RE.finditer(text):
        interfaces = [i.strip() for i in match.group(2).split(",") if i.strip()]
        for interface in interfaces:
            relationships.append(
                RawRelationship("class", match.group(1), "IMPLEMENTS", "interface", interface, {"file": scanned.path})
            )

    if class_name:
        for match in _NEW_RE.finditer(text):
            target = match.group(1)
            if target == class_name:
                continue
            relationships.append(
                RawRelationship("class", class_name, "USES", "class", target, {"file": scanned.path})
            )

        for pattern in (_TABLE_RE, _TABLE_PROP_RE):
            for match in pattern.finditer(text):
                relationships.append(
                    RawRelationship(
                        "class", class_name, "REFERENCES_TABLE", "table", match.group(1), {"file": scanned.path}
                    )
                )

    return relationships
