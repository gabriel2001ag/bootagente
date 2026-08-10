"""QAAgent: deterministic quality checks (seção 17). No AI involved.

Detects available tooling before running anything (`php`, `composer`,
`phpunit`) and never fails hard when a tool is absent — reports SKIPPED.
"""
from __future__ import annotations

from pathlib import Path

from agents.base_agent import Agent, AgentResult
from core.enums import AgentResultStatus
from core.task import Task
from executor.lint_runner import LintRunner
from executor.test_runner import TestRunner


class QAAgent(Agent):
    name = "qa_agent"

    def __init__(self, project_root: Path, run_composer_test: bool = False, run_phpunit: bool = False):
        self.project_root = Path(project_root)
        self.lint_runner = LintRunner()
        self.test_runner = TestRunner(project_root)
        self.run_composer_test = run_composer_test
        self.run_phpunit = run_phpunit

    def lint(self, php_files: list[str]) -> AgentResult:
        if not php_files:
            return AgentResult(AgentResultStatus.SKIPPED, 0.0, "no PHP files to lint")
        if not self.lint_runner.php_available():
            return AgentResult(AgentResultStatus.SKIPPED, 0.0, "php binary not found in PATH")

        results = self.lint_runner.lint_files(
            [str(self.project_root / f) for f in php_files]
        )
        failures = [r for r in results if not r.passed]
        if failures:
            return AgentResult(
                AgentResultStatus.ERROR, 0.0,
                f"php -l failed for {len(failures)}/{len(results)} file(s)",
                data={"failures": [f.__dict__ for f in failures]},
            )
        return AgentResult(
            AgentResultStatus.OK, 1.0, f"php -l passed for {len(results)} file(s)",
            data={"results": [r.__dict__ for r in results]},
        )

    def run_tests(self) -> AgentResult:
        tool = self.test_runner.detect()
        if not tool:
            return AgentResult(AgentResultStatus.SKIPPED, 0.0, "no composer test / phpunit detected")
        result = self.test_runner.run(
            enabled_composer=self.run_composer_test, enabled_phpunit=self.run_phpunit
        )
        if not result.ran:
            return AgentResult(
                AgentResultStatus.SKIPPED, 0.0,
                f"{tool} detected but not enabled in config.yaml (qa.run_composer_test/run_phpunit)",
            )
        status = AgentResultStatus.OK if result.passed else AgentResultStatus.ERROR
        return AgentResult(status, 1.0 if result.passed else 0.0, f"{tool}: {'passed' if result.passed else 'failed'}",
                            data={"output": result.output[-4000:]})

    def run(self, task: Task, context) -> AgentResult:
        candidate_files = getattr(context, "candidate_files", None) or []
        php_files = [f for f in candidate_files if f.endswith(".php")]
        lint_result = self.lint(php_files)
        return lint_result
