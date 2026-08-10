"""GitService: read-mostly wrapper around `git` via subprocess (seção 22).

Design rules enforced here:
  - never call destructive git subcommands (reset --hard, clean -fd, push
    --force) — those aren't even exposed as methods on this class;
  - detect pre-existing (uncommitted) changes BEFORE a task starts, so the
    Orchestrator can flag PRE_EXISTING_CHANGE and avoid clobbering the
    developer's own work;
  - never raise on "git not a repo" — return a status object instead, since
    the target project might legitimately not be a git repo yet.
"""
from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class GitStatus:
    is_repo: bool
    branch: str | None = None
    commit: str | None = None
    dirty: bool = False
    changed_files: list[str] = field(default_factory=list)
    untracked_files: list[str] = field(default_factory=list)
    error: str | None = None

    @property
    def has_pre_existing_changes(self) -> bool:
        return self.dirty or bool(self.untracked_files)


@dataclass
class CommandOutput:
    returncode: int
    stdout: str
    stderr: str

    @property
    def ok(self) -> bool:
        return self.returncode == 0


class GitService:
    def __init__(self, project_path: Path):
        self.project_path = Path(project_path)

    @staticmethod
    def is_git_available() -> bool:
        return shutil.which("git") is not None

    def _run(self, args: list[str], timeout: int = 20) -> CommandOutput:
        result = subprocess.run(
            ["git", *args],
            cwd=str(self.project_path),
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
        return CommandOutput(result.returncode, result.stdout, result.stderr)

    def status(self) -> GitStatus:
        if not self.is_git_available():
            return GitStatus(is_repo=False, error="git binary not found in PATH")
        if not (self.project_path / ".git").exists():
            return GitStatus(is_repo=False, error="not a git repository")

        branch_out = self._run(["rev-parse", "--abbrev-ref", "HEAD"])
        commit_out = self._run(["rev-parse", "HEAD"])
        porcelain = self._run(["status", "--porcelain"])

        changed: list[str] = []
        untracked: list[str] = []
        for line in porcelain.stdout.splitlines():
            if not line.strip():
                continue
            code, _, path = line.partition(" ")
            path = line[3:] if len(line) > 3 else path
            if line.startswith("??"):
                untracked.append(path.strip())
            else:
                changed.append(path.strip())

        return GitStatus(
            is_repo=True,
            branch=branch_out.stdout.strip() or None,
            commit=commit_out.stdout.strip() or None,
            dirty=bool(changed),
            changed_files=changed,
            untracked_files=untracked,
        )

    def current_commit(self) -> str | None:
        out = self._run(["rev-parse", "HEAD"])
        return out.stdout.strip() if out.ok else None

    def diff(self, staged: bool = False) -> str:
        args = ["diff"] + (["--cached"] if staged else [])
        out = self._run(args)
        return out.stdout

    def diff_numstat(self) -> str:
        out = self._run(["diff", "--numstat"])
        return out.stdout

    def log(self, limit: int = 5) -> list[str]:
        out = self._run(["log", f"-{limit}", "--oneline"])
        return [line for line in out.stdout.splitlines() if line.strip()]
