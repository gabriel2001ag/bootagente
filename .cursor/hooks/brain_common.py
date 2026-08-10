"""Utilitarios compartilhados pelos hooks Cursor (sem depender do Brain importado)."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any


def read_hook_input() -> dict[str, Any]:
    try:
        return json.load(sys.stdin)
    except json.JSONDecodeError:
        return {}


def resolve_workspace_root(data: dict[str, Any] | None = None) -> Path:
    data = data or {}
    for key in ("workspace_roots", "workspaceRoot", "rootPath", "cwd", "workspace"):
        val = data.get(key)
        if isinstance(val, list) and val:
            return Path(val[0]).resolve()
        if isinstance(val, str) and val.strip():
            return Path(val.strip()).resolve()

    for env_key in ("CURSOR_WORKSPACE", "VSCODE_CWD", "INIT_CWD", "PWD"):
        env_val = os.environ.get(env_key)
        if env_val and env_val.strip():
            return Path(env_val.strip()).resolve()

    return Path.cwd().resolve()


def resolve_brain_home(workspace: Path) -> Path | None:
    env_home = os.environ.get("PROJECT_BRAIN_HOME", "").strip()
    if env_home:
        candidate = Path(env_home).expanduser().resolve()
        if (candidate / "cli" / "main.py").exists():
            return candidate

    brain_path_file = workspace / ".brain-path"
    if brain_path_file.exists():
        raw = brain_path_file.read_text(encoding="utf-8").strip().splitlines()
        if raw:
            line = raw[0].strip()
            if line and not line.startswith("#"):
                candidate = Path(line).expanduser()
                if not candidate.is_absolute():
                    candidate = (workspace / candidate).resolve()
                else:
                    candidate = candidate.resolve()
                if (candidate / "cli" / "main.py").exists():
                    return candidate

    local = (workspace / "project-brain").resolve()
    if (local / "cli" / "main.py").exists():
        return local

    for parent in [workspace, *list(workspace.parents)[:6]]:
        candidate = (parent / "project-brain").resolve()
        if (candidate / "cli" / "main.py").exists():
            return candidate

    return None


def ensure_brain_import(workspace: Path | None = None, data: dict[str, Any] | None = None):
    """Insere project-brain no sys.path; retorna (workspace, brain_home)."""
    workspace = workspace or resolve_workspace_root(data)
    brain_home = resolve_brain_home(workspace)
    if brain_home and str(brain_home) not in sys.path:
        sys.path.insert(0, str(brain_home))
    return workspace, brain_home
