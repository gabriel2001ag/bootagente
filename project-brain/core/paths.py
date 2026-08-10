"""Resolution of Project Brain's own storage locations.

Project Brain never writes inside the analyzed (target) project except for
future, explicitly-approved patches (not implemented in V1 — see
ARCHITECTURE.md). Everything Project Brain owns (its SQLite database,
per-task audit trail, "active project" pointer) lives under this package's
own directory, by default `project-brain/` itself, matching the tree in
spec section 4. All of it is overridable via `config.yaml` (`storage.*`).
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


def brain_home() -> Path:
    """Root directory of the Project Brain tool itself (this package)."""
    return Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class BrainPaths:
    home: Path
    db_path: Path
    config_path: Path
    state_path: Path
    task_data_dir: Path
    migrations_dir: Path
    templates_dir: Path

    @classmethod
    def default(cls) -> "BrainPaths":
        home = brain_home()
        return cls(
            home=home,
            db_path=home / "project_brain.db",
            config_path=home / "config.yaml",
            state_path=home / "state.json",
            task_data_dir=home / "task-data",
            migrations_dir=home / "migrations",
            templates_dir=home / "templates",
        )

    def task_dir(self, project_slug: str, task_id: int) -> Path:
        return self.task_data_dir / project_slug / f"TASK-{task_id:05d}"


def slugify(text: str) -> str:
    """Small deterministic slugifier for project names used in path names."""
    keep = []
    for ch in text.strip().lower():
        if ch.isalnum():
            keep.append(ch)
        elif ch in (" ", "_", "-", "/", "\\", ":"):
            keep.append("-")
    slug = "".join(keep)
    while "--" in slug:
        slug = slug.replace("--", "-")
    return slug.strip("-") or "project"
