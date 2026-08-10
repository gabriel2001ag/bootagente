"""TestRunner: `composer test` / `vendor/bin/phpunit` when present (seção 17).

Detects whether the tools/config exist in the target project before running
anything; never runs tests that were not explicitly detected/opted-in.
"""
from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from pathlib import Path

from executor.command_runner import CommandRunner


@dataclass
class TestRunResult:
    tool: str
    ran: bool
    passed: bool
    command: str
    output: str


class TestRunner:
    def __init__(self, project_path: Path, runner: CommandRunner | None = None):
        self.project_path = Path(project_path)
        self.runner = runner or CommandRunner()

    def detect(self) -> str | None:
        """Return 'composer', 'phpunit' or None, in priority order."""
        composer_json = self.project_path / "composer.json"
        if composer_json.exists() and shutil.which("composer"):
            try:
                data = json.loads(composer_json.read_text(encoding="utf-8"))
                if "test" in data.get("scripts", {}):
                    return "composer"
            except (json.JSONDecodeError, OSError):
                pass
        phpunit_bin = self.project_path / "vendor" / "bin" / "phpunit"
        phpunit_bin_win = self.project_path / "vendor" / "bin" / "phpunit.bat"
        if phpunit_bin.exists() or phpunit_bin_win.exists():
            return "phpunit"
        return None

    def run(self, enabled_composer: bool = False, enabled_phpunit: bool = False) -> TestRunResult:
        tool = self.detect()
        if tool == "composer" and enabled_composer:
            result = self.runner.run(["composer", "test"], cwd=str(self.project_path), timeout=300)
            return TestRunResult("composer", True, result.ok, "composer test", result.stdout + result.stderr)
        if tool == "phpunit" and enabled_phpunit:
            bin_path = str(self.project_path / "vendor" / "bin" / "phpunit")
            result = self.runner.run([bin_path], cwd=str(self.project_path), timeout=300)
            return TestRunResult("phpunit", True, result.ok, bin_path, result.stdout + result.stderr)
        return TestRunResult(tool or "none", False, False, "", "no test tool ran (not detected or not enabled)")
