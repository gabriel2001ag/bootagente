"""Tests for brain_loop retro-feed cycle."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from brain.projects import ProjectRepository
from core.enums import TaskStatus
from core.paths import BrainPaths, slugify
from core.state import BrainState
from core.task import TaskRepository
import tools.brain_loop as brain_loop
from tools.brain_loop import (
    clear_active_task,
    close_task,
    format_agent_brief,
    get_active_task,
    inject_context_for_prompt,
    open_task,
    set_active_task,
    submit_on_stop,
)


@pytest.fixture
def loop_app(db, brain_paths, config, php_project, monkeypatch):
    from cli.main import BrainApp
    from core.paths import BrainPaths

    config.save(brain_paths.config_path)
    monkeypatch.setattr(BrainPaths, "default", staticmethod(lambda: brain_paths))

    app = BrainApp(paths=brain_paths)
    project = ProjectRepository(app.db).get_or_create(str(php_project.resolve()), name="sample")
    app.set_active(project)
    yield app, project
    app.close()


def test_open_task_sets_active_and_writes_context(loop_app):
    app, project = loop_app
    result = open_task("Corrigir filtro de pedidos", description="HTTP 500 no index")
    assert result["ok"] is True
    assert result["task_id"] > 0
    assert "Project Brain" in result["brief"]

    task_id, title = get_active_task(app)
    assert task_id == result["task_id"]
    assert title == "Corrigir filtro de pedidos"

    ctx_path = app.paths.task_dir(slugify(project.name), task_id) / "context.json"
    assert ctx_path.exists()
    ctx = json.loads(ctx_path.read_text(encoding="utf-8"))
    assert ctx["task"]["title"] == "Corrigir filtro de pedidos"


def test_close_task_clears_active(loop_app):
    app, _ = loop_app
    opened = open_task("Tarefa de teste")
    assert opened["ok"]

    closed = close_task(task_id=opened["task_id"], summary="Concluído nos testes")
    assert closed["ok"] is True

    task_id, title = get_active_task(app)
    assert task_id is None
    assert title is None

    task = TaskRepository(app.db).get(opened["task_id"])
    assert task.status == TaskStatus.WAITING_REVIEW.value


def test_inject_context_for_prompt_bootstraps_workspace(loop_app, monkeypatch):
    """UserPromptSubmit/beforeSubmitPrompt must self-heal the active project first.

    Without this, a Brain shared across repos keeps whatever project was last
    active in state.json — a prompt typed in one ERP could silently open a
    task (and later attach git evidence) against a *different* project.
    """
    _, project = loop_app
    calls: list[dict | None] = []
    monkeypatch.setattr(brain_loop, "run_bootstrap", lambda hook_data=None: calls.append(hook_data))

    hook_data = {"cwd": str(project.path)}
    brief = inject_context_for_prompt("Corrigir bug no relatorio de vendas", hook_data=hook_data)

    assert calls == [hook_data]
    assert brief is not None


def test_submit_on_stop_bootstraps_workspace(loop_app, monkeypatch):
    """Stop/stop hook must also self-heal the active project before closing."""
    _, project = loop_app
    calls: list[dict | None] = []
    monkeypatch.setattr(brain_loop, "run_bootstrap", lambda hook_data=None: calls.append(hook_data))

    opened = open_task("Tarefa para stop hook")
    assert opened["ok"]

    hook_data = {"cwd": str(project.path)}
    submit_on_stop(hook_data=hook_data)

    assert calls == [hook_data]


def test_brain_state_roundtrip(brain_paths):
    state = BrainState(active_project_id=1, active_task_id=42, active_task_title="Demo")
    state.save(brain_paths.state_path)
    loaded = BrainState.load(brain_paths.state_path)
    assert loaded.active_task_id == 42
    assert loaded.active_task_title == "Demo"


def test_format_agent_brief_includes_sections():
    ctx = {
        "task": {"title": "Demo"},
        "rules": [{"rule_code": "R-1", "rule_text": "Sempre validar CSRF"}],
        "patterns": [{"pattern_code": "P-1", "procedure": ["Usar filter seguro"]}],
        "lessons": [{"lesson_code": "L-1", "problem": "Evitar N+1"}],
        "similar_tasks": [{"task_id": 1, "title": "Outra", "score": 0.5}],
        "candidate_files": ["app/Controllers/Pedido.php"],
        "known_risks": [],
        "git_status": {"is_repo": True, "branch": "main", "dirty": False, "changed_files": []},
    }
    brief = format_agent_brief(ctx, 99)
    assert "Task #99" in brief
    assert "R-1" in brief
    assert "auto_submit" in brief
