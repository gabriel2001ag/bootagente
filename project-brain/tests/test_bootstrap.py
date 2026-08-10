"""Tests for tools.bootstrap — workspace-aware auto-registration for the Brain loop."""
from __future__ import annotations

from pathlib import Path

import pytest

import tools.bootstrap as bootstrap_mod
from core.paths import BrainPaths
from core.state import BrainState

PACKAGE_ROOT = Path(__file__).resolve().parent.parent

ENV_KEYS = ("PROJECT_BRAIN_HOME", "CURSOR_WORKSPACE", "VSCODE_CWD", "INIT_CWD", "PWD")


@pytest.fixture(autouse=True)
def _clear_env(monkeypatch):
    for key in ENV_KEYS:
        monkeypatch.delenv(key, raising=False)


def test_resolve_workspace_root_prefers_hook_data_cwd(tmp_path):
    workspace = tmp_path / "erp"
    workspace.mkdir()
    resolved = bootstrap_mod.resolve_workspace_root({"cwd": str(workspace)})
    assert resolved == workspace.resolve()


def test_resolve_workspace_root_accepts_workspace_roots_list(tmp_path):
    workspace = tmp_path / "erp"
    workspace.mkdir()
    resolved = bootstrap_mod.resolve_workspace_root({"workspace_roots": [str(workspace)]})
    assert resolved == workspace.resolve()


def test_resolve_workspace_root_falls_back_to_cwd_without_data(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    resolved = bootstrap_mod.resolve_workspace_root(None)
    assert resolved == tmp_path.resolve()


def test_resolve_brain_home_finds_local_project_brain_dir(tmp_path):
    workspace = tmp_path / "erp"
    brain = workspace / "project-brain"
    (brain / "cli").mkdir(parents=True)
    (brain / "cli" / "main.py").write_text("", encoding="utf-8")

    assert bootstrap_mod.resolve_brain_home(workspace) == brain.resolve()


def test_resolve_brain_home_follows_brain_path_file(tmp_path):
    workspace = tmp_path / "erp"
    workspace.mkdir()
    real_brain = tmp_path / "shared" / "project-brain"
    (real_brain / "cli").mkdir(parents=True)
    (real_brain / "cli" / "main.py").write_text("", encoding="utf-8")
    (workspace / ".brain-path").write_text(str(real_brain), encoding="utf-8")

    assert bootstrap_mod.resolve_brain_home(workspace) == real_brain.resolve()


def test_resolve_brain_home_searches_parents(tmp_path):
    brain = tmp_path / "project-brain"
    (brain / "cli").mkdir(parents=True)
    (brain / "cli" / "main.py").write_text("", encoding="utf-8")
    nested_workspace = tmp_path / "repos" / "erp"
    nested_workspace.mkdir(parents=True)

    assert bootstrap_mod.resolve_brain_home(nested_workspace) == brain.resolve()


def test_resolve_brain_home_returns_none_when_not_found(tmp_path):
    workspace = tmp_path / "erp"
    workspace.mkdir()
    assert bootstrap_mod.resolve_brain_home(workspace) is None


def test_bootstrap_reports_error_when_brain_not_found(tmp_path):
    workspace = tmp_path / "erp"
    workspace.mkdir()
    result = bootstrap_mod.bootstrap(workspace=workspace)
    assert result.ok is False
    assert result.error == "brain_not_found"


def test_bootstrap_registers_and_activates_workspace_project(tmp_path, monkeypatch):
    workspace = tmp_path / "erp"
    brain_home = workspace / "project-brain"
    (brain_home / "cli").mkdir(parents=True)
    (brain_home / "cli" / "main.py").write_text("", encoding="utf-8")

    isolated_paths = BrainPaths(
        home=brain_home,
        db_path=brain_home / "project_brain.db",
        config_path=brain_home / "config.yaml",
        state_path=brain_home / "state.json",
        task_data_dir=brain_home / "task-data",
        migrations_dir=PACKAGE_ROOT / "migrations",
        templates_dir=PACKAGE_ROOT / "templates",
    )
    monkeypatch.setattr(bootstrap_mod, "brain_paths_for", lambda home: isolated_paths)

    result = bootstrap_mod.bootstrap(hook_data={"cwd": str(workspace)})

    assert result.ok is True
    assert result.project_name == "erp"
    assert result.project_id is not None

    state = BrainState.load(isolated_paths.state_path)
    assert state.active_project_id == result.project_id

    # Idempotent: reusing the same workspace resolves to the same project id.
    again = bootstrap_mod.bootstrap(hook_data={"cwd": str(workspace)})
    assert again.project_id == result.project_id
