"""Parses `git diff --numstat` and unified diff text into structured data.

Used by ReviewerAgent (seção 17) to evaluate diff size / scope without
re-implementing a full diff parser.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class FileChange:
    path: str
    added: int
    removed: int

    @property
    def total(self) -> int:
        return self.added + self.removed


@dataclass
class DiffSummary:
    files: list[FileChange]

    @property
    def files_changed(self) -> int:
        return len(self.files)

    @property
    def total_lines_changed(self) -> int:
        return sum(f.total for f in self.files)


def parse_numstat(numstat_text: str) -> DiffSummary:
    files: list[FileChange] = []
    for line in numstat_text.splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split("\t")
        if len(parts) != 3:
            continue
        added_raw, removed_raw, path = parts
        added = 0 if added_raw == "-" else int(added_raw)
        removed = 0 if removed_raw == "-" else int(removed_raw)
        files.append(FileChange(path=path, added=added, removed=removed))
    return DiffSummary(files=files)


def parse_unified_diff_paths(diff_text: str) -> list[str]:
    """Extract touched file paths from a unified diff (`diff --git a/x b/x`)."""
    paths: list[str] = []
    for line in diff_text.splitlines():
        if line.startswith("diff --git "):
            rest = line[len("diff --git ") :]
            parts = rest.split(" b/")
            if len(parts) == 2:
                a_path = parts[0][2:] if parts[0].startswith("a/") else parts[0]
                paths.append(a_path)
    return paths
