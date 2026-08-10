"""CommandRunner: the only place allowed to call `subprocess` for external
tools on behalf of agents (seção 23).

Design decision (documented per ARCHITECTURE.md risk #6): the denylist
inspects the **parsed argv** (never `shell=True`, never a raw string), so a
git commit message that happens to contain the word "drop" does not trigger
a false positive — we look at argv *positions* (binary, subcommand, flags)
for git, and at the DB-CLI binary name for SQL statements.

Per seção 35 ("NUNCA executar comandos destrutivos"), the denylist is a hard
block in V1: `safety.allow_destructive_commands` is read from config and
recorded, but does NOT bypass the denylist in this version — bypassing
destructive operations safely (with explicit human confirmation per command)
is deferred to V2. This is a deliberately conservative reading of an
otherwise ambiguous flag.
"""
from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass


class DestructiveCommandError(Exception):
    """Raised when a command matches the denylist. The command is never run."""


@dataclass
class CommandResult:
    command: list[str]
    returncode: int
    stdout: str
    stderr: str

    @property
    def ok(self) -> bool:
        return self.returncode == 0


_SQL_DB_BINARIES = {"mysql", "mysqladmin", "psql", "sqlite3", "mongo", "mongosh"}
_SQL_DESTRUCTIVE_RE = re.compile(
    r"\bdrop\s+database\b|\bdrop\s+table\b|\btruncate\b", re.IGNORECASE
)
_SQL_DELETE_NO_WHERE_RE = re.compile(r"\bdelete\s+from\s+\S+\s*;?\s*$", re.IGNORECASE)
_RECURSIVE_DELETE_BINARIES = {"rm", "del", "erase", "rd", "rmdir"}


def _is_destructive(argv: list[str]) -> str | None:
    """Return a human-readable reason if `argv` is destructive, else None."""
    if not argv:
        return None
    binary = argv[0].lower().rsplit("\\", 1)[-1].rsplit("/", 1)[-1]
    if binary.endswith(".exe"):
        binary = binary[: -len(".exe")]
    rest = argv[1:]
    rest_lower = [a.lower() for a in rest]

    # --- git ---------------------------------------------------------
    if binary == "git" and rest_lower:
        sub = rest_lower[0]
        flags = rest_lower[1:]
        if sub == "reset" and "--hard" in flags:
            return "git reset --hard is denied (destructive, discards work)"
        if sub == "clean":
            flag_chars = "".join(f[1:] for f in flags if f.startswith("-") and not f.startswith("--"))
            long_flags = {f for f in flags if f.startswith("--")}
            has_force = "f" in flag_chars or "--force" in long_flags
            has_dirs = "d" in flag_chars or "--dirs" in long_flags
            if has_force and has_dirs:
                return "git clean -fd is denied (destructive, deletes untracked files)"
        if sub == "push" and any(f in ("-f", "--force", "--force-with-lease") for f in flags):
            return "git push --force is denied (destructive, rewrites remote history)"

    # --- recursive/forced filesystem deletion -------------------------
    if binary in _RECURSIVE_DELETE_BINARIES:
        has_recursive = any(a in ("-r", "-rf", "-fr", "/s") for a in rest_lower)
        has_force = any(a in ("-f", "-rf", "-fr", "/q") for a in rest_lower)
        if has_recursive and has_force:
            return f"{binary} recursive+force delete is denied (destructive)"

    if binary in ("powershell", "powershell.exe", "pwsh"):
        joined = " ".join(rest_lower)
        if "remove-item" in joined and "-recurse" in joined and "-force" in joined:
            return "PowerShell Remove-Item -Recurse -Force is denied (destructive)"

    # --- SQL destructive statements -----------------------------------
    if binary in _SQL_DB_BINARIES:
        for arg in rest:
            if _SQL_DESTRUCTIVE_RE.search(arg) or _SQL_DELETE_NO_WHERE_RE.search(arg):
                return f"SQL statement passed to {binary} looks destructive: {arg!r}"

    # --- deployment ------------------------------------------------------
    for arg in rest_lower:
        if arg == "deploy" or arg.startswith("deploy:"):
            return "Commands that trigger deployment are denied in V1"

    return None


class CommandRunner:
    def __init__(self, allow_destructive_commands: bool = False):
        # Recorded for audit purposes; does not bypass the hard denylist
        # in V1 (see module docstring).
        self.allow_destructive_commands = allow_destructive_commands

    def run(
        self,
        argv: list[str],
        cwd: str | None = None,
        timeout: int = 60,
        check: bool = False,
    ) -> CommandResult:
        reason = _is_destructive(argv)
        if reason:
            raise DestructiveCommandError(reason)
        result = subprocess.run(
            argv,
            cwd=cwd,
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
        cmd_result = CommandResult(
            command=argv,
            returncode=result.returncode,
            stdout=result.stdout,
            stderr=result.stderr,
        )
        if check and not cmd_result.ok:
            raise subprocess.CalledProcessError(result.returncode, argv, result.stdout, result.stderr)
        return cmd_result
