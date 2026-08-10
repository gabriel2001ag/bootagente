"""Integration tests for the Orchestrator: Senior available/unavailable,
local fallback, confidence thresholds, and pre-existing git changes
(seção 31)."""
from __future__ import annotations

import subprocess

from agents.local_pipeline import try_execute
from brain.memory import SimilarTask
from brain.patterns import Pattern
from brain.projects import ProjectRepository
from brain.rules import Rule
from core.context_builder import TaskContext
from core.enums import Decision, SeniorStatus, TaskStatus
from core.orchestrator import Orchestrator
from core.task import Task, TaskRepository


def _run(args, cwd):
    subprocess.run(args, cwd=str(cwd), check=True, capture_output=True, encoding="utf-8")


def _git_init(path):
    _run(["git", "init"], path)
    _run(["git", "config", "user.email", "test@example.com"], path)
    _run(["git", "config", "user.name", "Test"], path)
    _run(["git", "add", "."], path)
    _run(["git", "commit", "-m", "initial"], path)


# ---------------------------------------------------------- confidence ----
def test_low_confidence_requires_senior_and_touches_nothing(db, config, php_project):
    projects = ProjectRepository(db)
    project = projects.get_or_create(str(php_project), name="sample")
    task_repo = TaskRepository(db)
    task = task_repo.create(project.id, title="Fazer algo completamente novo e nunca antes visto")

    context = TaskContext(task=task)  # no rules, no patterns, no similar tasks
    result = try_execute(task, context, config, db, project.id, php_project)

    assert result.decision == Decision.REQUIRES_SENIOR
    assert result.files_modified == []
    assert result.confidence < config.confidence.analysis_only


def test_high_confidence_signals_produce_higher_confidence(db, config, php_project):
    projects = ProjectRepository(db)
    project = projects.get_or_create(str(php_project), name="sample")
    task_repo = TaskRepository(db)
    task = task_repo.create(
        project.id,
        title="Limitar o intervalo de notas para no maximo 100",
        description="",
    )
    previous = task_repo.create(project.id, title="tarefa anterior qualquer")

    rich_context = TaskContext(
        task=task,
        rules=[
            Rule(id=1, rule_code="R1", category="validation", rule_text="limitar sempre o intervalo"),
            Rule(id=2, rule_code="R2", category="validation", rule_text="limitar quantidade máxima"),
            Rule(id=3, rule_code="R3", category="validation", rule_text="limitar registros retornados"),
        ],
        patterns=[
            Pattern(id=1, pattern_code="P1", category="validation", framework="CodeIgniter4", trigger="numeric_range"),
        ],
        similar_tasks=[SimilarTask(task=previous, score=0.9)],
        candidate_files=[],
    )
    poor_context = TaskContext(task=task)

    rich_result = try_execute(task, rich_context, config, db, project.id, php_project)
    poor_result = try_execute(task, poor_context, config, db, project.id, php_project)

    assert rich_result.confidence > poor_result.confidence
    assert rich_result.decision != Decision.REQUIRES_SENIOR
    assert rich_result.files_modified == []  # V1 never edits files


def test_confidence_decision_mapping_is_monotonic(config):
    assert config.decision_for_confidence(0.10) == Decision.REQUIRES_SENIOR
    assert config.decision_for_confidence(0.65) == Decision.ANALYSIS_ONLY
    assert config.decision_for_confidence(0.85) == Decision.PATCH_REQUIRES_REVIEW
    assert config.decision_for_confidence(0.99) == Decision.AUTO_EXECUTE_ALLOWED


# --------------------------------------------------------- orchestrator ---
def test_orchestrator_with_senior_available(db, config, php_project, brain_paths):
    _git_init(php_project)
    config.senior.provider = "mock"
    config.senior.mock_availability = "AVAILABLE"

    projects = ProjectRepository(db)
    project = projects.get_or_create(str(php_project), name="sample")

    orchestrator = Orchestrator(db, config, brain_paths, project)
    summary = orchestrator.run_task("Limitar intervalo de pedidos para no maximo 50")

    assert summary.senior_status == SeniorStatus.AVAILABLE
    assert summary.mode.value == "SENIOR"
    assert summary.task.status in (TaskStatus.WAITING_REVIEW.value, TaskStatus.COMPLETED.value)
    # audit trail written
    assert (summary.audit_dir / "request.json").exists()
    assert (summary.audit_dir / "context.json").exists()
    assert (summary.audit_dir / "decision.json").exists()
    # learning captured from the mock senior's structured output (seção 12)
    lessons = db.query("SELECT * FROM lessons WHERE task_id = ?", (summary.task.id,))
    assert len(lessons) == 1


def test_orchestrator_local_fallback_when_senior_unavailable(db, config, php_project, brain_paths):
    _git_init(php_project)
    config.senior.provider = "mock"
    config.senior.mock_availability = "UNAVAILABLE"

    projects = ProjectRepository(db)
    project = projects.get_or_create(str(php_project), name="sample")

    orchestrator = Orchestrator(db, config, brain_paths, project)
    summary = orchestrator.run_task("Uma tarefa totalmente nova sem histórico nenhum")

    assert summary.senior_status == SeniorStatus.UNAVAILABLE
    assert summary.mode.value == "LOCAL_FALLBACK"
    assert summary.decision == Decision.REQUIRES_SENIOR
    assert summary.task.status == TaskStatus.SENIOR_REQUIRED.value
    assert (summary.audit_dir / "local_execution.json").exists()


def test_orchestrator_waits_without_local_pipeline_when_fallback_disabled(
    db, config, php_project, brain_paths
):
    _git_init(php_project)
    config.senior.provider = "mock"
    config.senior.mock_availability = "UNAVAILABLE"
    config.fallback.enabled = False
    project = ProjectRepository(db).get_or_create(str(php_project), name="sample")

    summary = Orchestrator(db, config, brain_paths, project).run_task("Tarefa desconhecida")

    assert summary.mode.value == "WAITING_FOR_SENIOR"
    assert summary.task.status == TaskStatus.SENIOR_REQUIRED.value
    assert summary.decision == Decision.REQUIRES_SENIOR
    assert summary.local_result is None
    assert not (summary.audit_dir / "local_execution.json").exists()
    assert not (summary.audit_dir / "tests.json").exists()


def test_workspace_handoff_always_consults_brain_even_when_fallback_disabled(
    db, config, php_project, brain_paths
):
    _git_init(php_project)
    config.senior.provider = "codex-vscode"
    config.fallback.enabled = False
    project = ProjectRepository(db).get_or_create(str(php_project), name="sample")

    summary = Orchestrator(db, config, brain_paths, project).run_task(
        "Investigar protocolo desconhecido"
    )

    assert summary.mode.value == "WORKSPACE_HANDOFF"
    assert summary.local_result is not None
    assert (summary.audit_dir / "local_execution.json").exists()
    assert summary.local_result.files_modified == []


def test_orchestrator_flags_pre_existing_change(db, config, php_project, brain_paths):
    _git_init(php_project)
    # simulate a developer's uncommitted work before the task starts
    (php_project / "app" / "Controllers" / "Pedido.php").write_text("<?php // dirty\n", encoding="utf-8")

    config.senior.provider = "mock"
    config.senior.mock_availability = "UNAVAILABLE"

    projects = ProjectRepository(db)
    project = projects.get_or_create(str(php_project), name="sample")

    orchestrator = Orchestrator(db, config, brain_paths, project)
    summary = orchestrator.run_task("Qualquer tarefa")

    assert any("PRE_EXISTING_CHANGE" in w for w in summary.warnings)
    assert summary.context.git_status.has_pre_existing_changes is True


def test_orchestrator_hybrid_route_prepares_workspace_handoff(
    db, config, php_project, brain_paths
):
    _git_init(php_project)
    config.senior.provider = "codex-vscode"
    project = ProjectRepository(db).get_or_create(str(php_project), name="sample")
    tasks = TaskRepository(db)
    tasks.create(project.id, "Limitar intervalo de pedidos para no máximo 50")
    from brain.lessons import LessonRepository
    from brain.patterns import PatternRepository
    from brain.rules import RuleRepository

    for index in range(3):
        RuleRepository(db).add(
            f"R{index}", "orders", "limitar intervalo de pedidos", project_id=project.id
        )
    for index in range(2):
        PatternRepository(db).add(
            f"P{index}", "orders", trigger="limitar intervalo de pedidos",
            project_id=project.id,
        )
        LessonRepository(db).add(
            f"L{index}", "intervalo de pedidos sem limite", "limitar no backend",
            project_id=project.id,
        )

    summary = Orchestrator(db, config, brain_paths, project).run_task(
        "Limitar intervalo de pedidos para no máximo 50"
    )

    assert summary.mode.value == "WORKSPACE_HANDOFF"
    assert summary.local_result.signals["route"]["mode"] == "HYBRID"
    assert summary.task.status == TaskStatus.SENIOR_REQUIRED.value
