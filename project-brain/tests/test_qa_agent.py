import pytest

from agents.qa_agent import QAAgent
from executor.lint_runner import LintRunner


def test_lint_passes_for_valid_php(php_project):
    agent = QAAgent(php_project)
    if not agent.lint_runner.php_available():
        pytest.skip("php binary not available in PATH")
    result = agent.lint(["app/Controllers/Pedido.php"])
    assert result.status.value == "OK"


def test_lint_fails_for_invalid_php(php_project):
    agent = QAAgent(php_project)
    if not agent.lint_runner.php_available():
        pytest.skip("php binary not available in PATH")
    broken = php_project / "app" / "Controllers" / "Broken.php"
    broken.write_text("<?php\nclass Broken {\n  public function foo( {\n", encoding="utf-8")
    result = agent.lint(["app/Controllers/Broken.php"])
    assert result.status.value == "ERROR"


def test_lint_skips_gracefully_when_php_missing(php_project, monkeypatch):
    monkeypatch.setattr(LintRunner, "php_available", staticmethod(lambda: False))
    agent = QAAgent(php_project)
    result = agent.lint(["app/Controllers/Pedido.php"])
    assert result.status.value == "SKIPPED"


def test_lint_skips_when_no_files():
    agent = QAAgent(".")
    result = agent.lint([])
    assert result.status.value == "SKIPPED"
