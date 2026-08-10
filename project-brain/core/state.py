"""Tracks the "active project" pointer across CLI invocations.

`brain init <path>` sets it; subsequent commands (`brain status`,
`brain task ...`) default to it unless `--project` overrides it. See
ARCHITECTURE.md section 2 for the reasoning behind a central multi-project
database + this small pointer file, instead of a single project path in
config.yaml.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass
class BrainState:
    active_project_id: int | None = None

    @classmethod
    def load(cls, path: Path) -> "BrainState":
        if not path.exists():
            return cls()
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return cls()
        return cls(active_project_id=data.get("active_project_id"))

    def save(self, path: Path) -> None:
        path.write_text(json.dumps({"active_project_id": self.active_project_id}), encoding="utf-8")
