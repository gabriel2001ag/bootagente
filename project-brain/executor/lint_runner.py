"""LintRunner: `php -l` on candidate files (seção 17, QAAgent).

Detects the `php` binary before attempting anything; never raises for a
missing tool, returns a SKIPPED-style result instead.
"""
from __future__ import annotations

import shutil
from dataclasses import dataclass

from executor.command_runner import CommandRunner


@dataclass
class LintResult:
    tool_available: bool
    file: str
    passed: bool
    message: str


class LintRunner:
    def __init__(self, runner: CommandRunner | None = None):
        self.runner = runner or CommandRunner()

    @staticmethod
    def php_available() -> bool:
        return shutil.which("php") is not None

    def lint_php_file(self, file_path: str) -> LintResult:
        if not self.php_available():
            return LintResult(
                tool_available=False,
                file=file_path,
                passed=False,
                message="php binary not found in PATH; lint skipped",
            )
        result = self.runner.run(["php", "-l", file_path], timeout=15)
        return LintResult(
            tool_available=True,
            file=file_path,
            passed=result.ok,
            message=(result.stdout + result.stderr).strip(),
        )

    def lint_files(self, file_paths: list[str]) -> list[LintResult]:
        return [self.lint_php_file(f) for f in file_paths if f.endswith(".php")]
