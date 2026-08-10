"""End-to-end CLI tests, exercising `brain init` / `task` / `status` /
`memory search` through the real `cli.main.main()` entrypoint.

Crucially, `BrainPaths.default()` is monkeypatched to a temp directory so
these tests never touch the real `project-brain/project_brain.db`.
"""
from __future__ import annotations

import subprocess

import pytest

import cli.main as cli_main
from core.paths import BrainPaths


@pytest.fixture(autouse=True)
def isolated_brain_home(brain_paths, monkeypatch):
    monkeypatch.setattr(BrainPaths, "default", classmethod(lambda cls: brain_paths))
    yield brain_paths


def _git_init(path):
    subprocess.run(["git", "init"], cwd=str(path), check=True, capture_output=True, encoding="utf-8")
    subprocess.run(["git", "config", "user.email", "t@t.com"], cwd=str(path), check=True, capture_output=True, encoding="utf-8")
    subprocess.run(["git", "config", "user.name", "T"], cwd=str(path), check=True, capture_output=True, encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=str(path), check=True, capture_output=True, encoding="utf-8")
    subprocess.run(["git", "commit", "-m", "initial"], cwd=str(path), check=True, capture_output=True, encoding="utf-8")


def test_cli_init_registers_and_indexes_project(php_project, capsys):
    exit_code = cli_main.main(["init", str(php_project)])
    assert exit_code == 0
    out = capsys.readouterr().out
    assert "Initialized project" in out
    assert "Indexed" in out


def test_cli_status_after_init(php_project, capsys):
    cli_main.main(["init", str(php_project)])
    capsys.readouterr()
    exit_code = cli_main.main(["status"])
    assert exit_code == 0
    out = capsys.readouterr().out
    assert "Senior provider" in out
    assert "Knowledge base" in out


def test_cli_task_offline_mode_shows_no_files_modified(php_project, capsys):
    cli_main.main(["init", str(php_project)])
    capsys.readouterr()
    exit_code = cli_main.main(["task", "Uma tarefa nova sem nenhum histórico prévio"])
    assert exit_code == 0
    out = capsys.readouterr().out
    assert "No files were modified" in out
    assert "Decision:" in out


def test_cli_inspect_project_overview(php_project, capsys):
    cli_main.main(["init", str(php_project)])
    capsys.readouterr()
    exit_code = cli_main.main(["inspect"])
    assert exit_code == 0
    out = capsys.readouterr().out
    assert "Project:" in out
    assert "Files indexed:" in out


def test_cli_inspect_file(php_project, capsys):
    cli_main.main(["init", str(php_project)])
    capsys.readouterr()
    exit_code = cli_main.main(["inspect", "file", "app/Controllers/Pedido.php"])
    assert exit_code == 0
    out = capsys.readouterr().out
    assert "PedidoController" in out


def test_cli_memory_search_returns_empty_gracefully(php_project, capsys):
    cli_main.main(["init", str(php_project)])
    capsys.readouterr()
    exit_code = cli_main.main(["memory", "search", "inexistente"])
    assert exit_code == 0
    out = capsys.readouterr().out
    assert "Rules (0)" in out


def test_cli_requires_init_before_task(tmp_path, capsys):
    exit_code = cli_main.main(["status"])
    assert exit_code == 1
    out = capsys.readouterr().out
    assert "No active project" in out


def test_cli_task_history_empty(php_project, capsys):
    cli_main.main(["init", str(php_project)])
    capsys.readouterr()
    exit_code = cli_main.main(["task", "history"])
    assert exit_code == 0
    out = capsys.readouterr().out
    assert "No tasks recorded yet." in out


def test_cli_rebuild_only_updates_derived_index(php_project, capsys):
    cli_main.main(["init", str(php_project)])
    capsys.readouterr()
    assert cli_main.main(["index", "--rebuild"]) == 0
    assert "Rebuilt project" in capsys.readouterr().out
