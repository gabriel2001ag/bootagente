#!/usr/bin/env python3
"""
Auto-submit para Project Brain - Solução Genérica

Este script automatiza o fluxo de ensino do Brain para QUALQUER agente
(Claude Code, Codex, ou outro). Não depende de hooks específicos de IDE.

Funcionamento:
1. Detecta arquivos modificados no Git
2. Cria ou usa uma tarefa existente no Brain
3. Monta JSON com evidências reais (arquivos modificados)
4. Submete ao Brain automaticamente

Uso:
    cd project-brain
    python -m tools.auto_submit "Título da tarefa" [--description "Descrição"] [--task-id N]

Exemplo:
    python -m tools.auto_submit "Corrigir erro de etiqueta FrutaG" --description "HTTP 500 ao baixar PDF"
"""

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

# Adicionar o diretório pai ao path para importar cli.main
sys.path.insert(0, str(Path(__file__).parent.parent))

from cli.main import BrainApp
from core.task import Task, TaskRepository
from senior.codex_workspace_bridge import CodexWorkspaceBridge


def get_git_changes(project_path: str) -> list[str]:
    """Retorna lista de arquivos modificados no Git."""
    try:
        result = subprocess.run(
            ["git", "diff", "--name-only", "HEAD"],
            cwd=project_path,
            capture_output=True,
            text=True,
            check=True,
        )
        files = [f.strip() for f in result.stdout.strip().split("\n") if f.strip()]
        return files
    except subprocess.CalledProcessError:
        return []


def get_git_status(project_path: str) -> dict[str, Any]:
    """Retorna status detalhado do Git."""
    try:
        # Branch atual
        branch_result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=project_path,
            capture_output=True,
            text=True,
            check=True,
        )
        branch = branch_result.stdout.strip()

        # Commit atual
        commit_result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=project_path,
            capture_output=True,
            text=True,
            check=True,
        )
        commit = commit_result.stdout.strip()

        # Arquivos modificados
        modified = get_git_changes(project_path)

        # Dirty flag
        dirty_result = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=project_path,
            capture_output=True,
            text=True,
            check=True,
        )
        dirty = bool(dirty_result.stdout.strip())

        return {
            "is_repo": True,
            "branch": branch,
            "commit": commit,
            "dirty": dirty,
            "changed_files": modified,
            "untracked_files": [],
        }
    except subprocess.CalledProcessError:
        return {
            "is_repo": False,
            "branch": None,
            "commit": None,
            "dirty": False,
            "changed_files": [],
            "untracked_files": [],
        }


def build_evidence(app: BrainApp, project_id: int, changed_files: list[str]) -> list[dict[str, Any]]:
    """Constroi lista de evidências com arquivos modificados."""
    evidence = []
    for file_path in changed_files:
        # Verificar se o arquivo está indexado no Brain
        row = app.db.query_one(
            "SELECT path FROM files WHERE project_id=? AND path=?",
            (project_id, file_path),
        )
        if row:
            evidence.append({"path": file_path})
    return evidence


def auto_submit(title: str, description: str = "", task_id: int | None = None) -> int:
    """Executa o fluxo automático de submissão."""
    app = BrainApp()
    project = app.resolve_project(None)

    if not project:
        print("Erro: nenhum projeto ativo encontrado. Rode 'brain init <path>' primeiro.")
        return 1

    print(f"Projeto: {project.name} ({project.path})")

    # Obter status do Git
    git_status = get_git_status(project.path)
    print(f"Git: branch={git_status.get('branch')}, dirty={git_status.get('dirty')}")
    print(f"Arquivos modificados: {len(git_status.get('changed_files', []))}")

    # Criar ou usar tarefa existente
    if task_id:
        task = TaskRepository(app.db).get(task_id)
        if not task or task.project_id != project.id:
            print(f"Erro: tarefa #{task_id} não encontrada ou não pertence a este projeto.")
            app.close()
            return 1
        print(f"Usando tarefa existente: #{task.id} - {task.title}")
    else:
        # Criar nova tarefa diretamente (sem Orchestrator.run_task que é lento)
        from core.enums import TaskStatus
        
        task = TaskRepository(app.db).create(
            project_id=project.id,
            title=title,
            description=description,
            source="cli",
        )
        # Atualizar status para SENIOR_REQUIRED e adicionar commit Git
        task = TaskRepository(app.db).update_status(
            task.id,
            TaskStatus.SENIOR_REQUIRED,
        )
        TaskRepository(app.db).set_git_commits(
            task.id,
            git_status.get("commit"),
            None,
        )
        print(f"Criada tarefa: #{task.id} - {task.title}")

    # Obter contexto da tarefa
    bridge = CodexWorkspaceBridge(app.db, app.paths, app.config)
    context = bridge.context(task.id)

    # Montar evidências
    changed_files = git_status.get("changed_files", [])
    evidence = build_evidence(app, project.id, changed_files)

    # Montar resultado
    result = {
        "status": "SUCCESS",
        "summary": f"Tarefa concluída automaticamente. {len(evidence)} arquivos modificados.",
        "decision": "AUTO_EXECUTE_ALLOWED" if evidence else "REQUIRES_SENIOR",
        "confidence": 0.9 if evidence else 0.5,
        "requires_human_review": False,
        "approved_for_learning": bool(evidence),
        "important_files": changed_files[:5],
        "affected_modules": [],
        "risks": [],
        "rules_discovered": [],
        "patterns_used": [],
        "lessons": [],
        "evidence": evidence,
    }

    # Salvar JSON temporário
    temp_file = app.paths.home / f"auto-submit-{task.id}.json"
    with open(temp_file, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)

    print(f"Resultado salvo em: {temp_file}")

    # Submeter
    print("Submetendo ao Brain...")
    bridge.submit(task.id, temp_file)

    # Limpar
    temp_file.unlink()

    print(f"✓ Tarefa #{task.id} submetida com sucesso.")
    app.close()
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Auto-submit genérico para Project Brain")
    parser.add_argument("title", help="Título da tarefa")
    parser.add_argument("--description", default="", help="Descrição da tarefa")
    parser.add_argument("--task-id", type=int, default=None, help="ID de tarefa existente (opcional)")
    
    args = parser.parse_args()
    
    return auto_submit(args.title, args.description, args.task_id)


if __name__ == "__main__":
    sys.exit(main())
