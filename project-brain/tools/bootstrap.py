#!/usr/bin/env python3
"""Auto-bootstrap do Project Brain para o workspace do agente (ERP).

Localiza project-brain, registra o ERP como projeto ativo e indexa
incrementalmente quando necessario.
"""
from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parent.parent))

from analysis.project_indexer import ProjectIndexer  # noqa: E402
from brain.projects import ProjectRepository  # noqa: E402
from core.paths import BrainPaths  # noqa: E402


@dataclass
class BootstrapResult:
    ok: bool
    workspace: Path | None = None
    brain_home: Path | None = None
    project_id: int | None = None
    project_name: str | None = None
    indexed: bool = False
    files_indexed: int = 0
    error: str | None = None
    detail: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "workspace": str(self.workspace) if self.workspace else None,
            "brain_home": str(self.brain_home) if self.brain_home else None,
            "project_id": self.project_id,
            "project_name": self.project_name,
            "indexed": self.indexed,
            "files_indexed": self.files_indexed,
            "error": self.error,
            "detail": self.detail,
        }


def resolve_workspace_root(data: dict[str, Any] | None = None) -> Path:
    """Descobre a raiz do workspace (ERP) onde o agente esta rodando."""
    if data:
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
    """Localiza a pasta project-brain a partir do workspace do ERP."""
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


def brain_paths_for(home: Path) -> BrainPaths:
    return BrainPaths(
        home=home,
        db_path=home / "project_brain.db",
        config_path=home / "config.yaml",
        state_path=home / "state.json",
        task_data_dir=home / "task-data",
        migrations_dir=home / "migrations",
        templates_dir=home / "templates",
    )


def bootstrap(
    workspace: Path | None = None,
    hook_data: dict[str, Any] | None = None,
    *,
    index: bool = False,
) -> BootstrapResult:
    """Registra o ERP no Brain e define como projeto ativo."""
    workspace = workspace or resolve_workspace_root(hook_data)
    brain_home = resolve_brain_home(workspace)
    if not brain_home:
        return BootstrapResult(
            ok=False,
            workspace=workspace,
            error="brain_not_found",
            detail=(
                "Crie .brain-path na raiz do ERP apontando para project-brain "
                "ou defina PROJECT_BRAIN_HOME."
            ),
        )

    from cli.main import BrainApp

    paths = brain_paths_for(brain_home)
    app = BrainApp(paths=paths)
    try:
        resolved = str(workspace.resolve())
        project = ProjectRepository(app.db).get_or_create(resolved, name=workspace.name)
        app.set_active(project)

        files_indexed = 0
        did_index = False
        if index:
            indexer = ProjectIndexer(app.db, app.config.indexing)
            stats = indexer.index(project.id, workspace)
            app.project_repo.touch_indexed(project.id, stats.primary_language)
            files_indexed = stats.files_indexed
            did_index = True

        return BootstrapResult(
            ok=True,
            workspace=workspace,
            brain_home=brain_home,
            project_id=project.id,
            project_name=project.name,
            indexed=did_index,
            files_indexed=files_indexed,
        )
    finally:
        app.close()


def format_bootstrap_brief(result: BootstrapResult) -> str:
    if not result.ok:
        return (
            "## Project Brain — nao iniciado\n"
            f"Workspace: `{result.workspace}`\n"
            f"Motivo: {result.detail or result.error}\n\n"
            "Configure `.brain-path` na raiz do ERP com o caminho para `project-brain`."
        )
    lines = [
        "## Project Brain — ativo",
        f"ERP: `{result.workspace}` (projeto **{result.project_name}**, id={result.project_id})",
        f"Brain: `{result.brain_home}`",
    ]
    if result.indexed:
        lines.append(f"Indice atualizado: {result.files_indexed} arquivo(s) novo(s)/alterado(s).")
    lines.append("")
    lines.append("Rules, patterns e lessons deste ERP serao carregados automaticamente.")
    return "\n".join(lines)


def main() -> int:
    import argparse
    import json

    parser = argparse.ArgumentParser(description="Bootstrap Project Brain para o workspace atual")
    parser.add_argument("--index", action="store_true", help="Rodar indexacao incremental")
    parser.add_argument("--json", action="store_true", help="Saida JSON")
    args = parser.parse_args()

    result = bootstrap(index=args.index)
    if args.json:
        print(json.dumps(result.to_dict(), indent=2, ensure_ascii=False))
    elif result.ok:
        print(format_bootstrap_brief(result))
    else:
        print(f"Erro: {result.detail or result.error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
