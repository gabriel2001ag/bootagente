#!/usr/bin/env python3
"""Retroalimentação Agente ↔ Project Brain.

Abre tarefa (Brain → Agente) e fecha tarefa (Agente → Brain) sem o
Orchestrator completo — rápido o suficiente para hooks e uso manual.
"""
from __future__ import annotations

import dataclasses
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parent.parent))

from analysis.project_indexer import ProjectIndexer  # noqa: E402
from brain.memory import MemoryStore  # noqa: E402
from brain.similarity import KeywordSimilarityEngine  # noqa: E402
from cli.main import BrainApp  # noqa: E402
from core.concepts import ConceptExpander  # noqa: E402
from core.context_builder import ContextBuilder, TaskContext  # noqa: E402
from core.enums import TaskStatus  # noqa: E402
from core.paths import slugify  # noqa: E402
from core.state import BrainState  # noqa: E402
from core.task import Task, TaskRepository  # noqa: E402
from git.git_service import GitService  # noqa: E402
from senior.provider import LearningPayload  # noqa: E402
from tools.bootstrap import bootstrap as run_bootstrap  # noqa: E402


CASUAL_PROMPT = re.compile(
    r"^\s*(oi|olá|ola|obrigado|obrigada|valeu|ok|okay|sim|não|nao|thanks|hello|hi)\s*[!.?]*\s*$",
    re.IGNORECASE,
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _bootstrap_workspace(hook_data: dict[str, Any] | None = None) -> None:
    """Ativa no Brain o projeto do workspace atual antes do fluxo automático.

    Sem isso, `BrainApp().resolve_project(None)` usa o `active_project_id`
    global de `state.json`, que pode apontar para outro ERP se o mesmo Brain
    for compartilhado entre repositórios — misturando tarefas/evidências de
    um workspace com o commit/arquivos de outro. Best-effort: se o Brain não
    for localizável a partir do workspace, mantém o projeto ativo atual.
    """
    try:
        run_bootstrap(hook_data=hook_data)
    except Exception:
        pass


def get_git_changes(project_path: str) -> list[str]:
    try:
        result = subprocess.run(
            ["git", "diff", "--name-only", "HEAD"],
            cwd=project_path,
            capture_output=True,
            text=True,
            check=True,
        )
        return [f.strip() for f in result.stdout.strip().split("\n") if f.strip()]
    except subprocess.CalledProcessError:
        return []


def get_git_status(project_path: str) -> dict[str, Any]:
    try:
        branch = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=project_path,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        commit = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=project_path,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        changed = get_git_changes(project_path)
        dirty = bool(
            subprocess.run(
                ["git", "status", "--porcelain"],
                cwd=project_path,
                capture_output=True,
                text=True,
                check=True,
            ).stdout.strip()
        )
        return {
            "is_repo": True,
            "branch": branch,
            "commit": commit,
            "dirty": dirty,
            "changed_files": changed,
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


def context_to_dict(context: TaskContext) -> dict[str, Any]:
    return {
        "task": dataclasses.asdict(context.task),
        "rules": [dataclasses.asdict(r) for r in context.rules],
        "patterns": [dataclasses.asdict(p) for p in context.patterns],
        "lessons": [dataclasses.asdict(l) for l in context.lessons],
        "similar_tasks": [
            {"task_id": s.task.id, "title": s.task.title, "score": s.score}
            for s in context.similar_tasks
        ],
        "candidate_files": context.candidate_files,
        "keywords": context.keywords,
        "git_status": dataclasses.asdict(context.git_status) if context.git_status else None,
        "known_risks": context.known_risks,
    }


def format_agent_brief(context: dict[str, Any], task_id: int) -> str:
    """Texto compacto para injeção no agente (hook ou AGENTS.md)."""
    lines = [
        "## Project Brain — contexto da tarefa ativa",
        f"Task #{task_id}: {context['task']['title']}",
        "",
    ]
    if context.get("rules"):
        lines.append("### Rules confirmadas")
        for rule in context["rules"][:5]:
            lines.append(f"- [{rule.get('rule_code', '?')}] {rule.get('rule_text', '')}")
        lines.append("")
    if context.get("patterns"):
        lines.append("### Patterns aprovados")
        for pat in context["patterns"][:5]:
            proc = pat.get("procedure") or []
            preview = proc[0] if proc else pat.get("trigger", "")
            lines.append(f"- [{pat.get('pattern_code', '?')}] {preview}")
        lines.append("")
    if context.get("lessons"):
        lines.append("### Lessons aprendidas")
        for lesson in context["lessons"][:5]:
            lines.append(f"- [{lesson.get('lesson_code', '?')}] {lesson.get('problem', '')}")
        lines.append("")
    if context.get("similar_tasks"):
        lines.append("### Tarefas similares")
        for item in context["similar_tasks"][:3]:
            lines.append(f"- #{item['task_id']} {item['title']} (score={item['score']})")
        lines.append("")
    files = context.get("candidate_files") or []
    if files:
        lines.append(f"### Arquivos candidatos\n{', '.join(files[:8])}")
        lines.append("")
    risks = context.get("known_risks") or []
    if risks:
        lines.append("### Riscos conhecidos")
        for risk in risks:
            lines.append(f"- {risk}")
        lines.append("")
    git = context.get("git_status") or {}
    if git.get("is_repo"):
        lines.append(
            f"Git: branch={git.get('branch')} dirty={git.get('dirty')} "
            f"changed={len(git.get('changed_files') or [])}"
        )
    lines.append("")
    lines.append(
        f"Ao concluir, registre aprendizado: "
        f"`cd project-brain && python -m tools.auto_submit --task-id {task_id}`"
    )
    return "\n".join(lines)


def _memory_store(app: BrainApp) -> MemoryStore:
    expander = ConceptExpander(
        app.config.concepts.groups,
        app.config.concepts.aliases,
        app.config.concepts.relationships,
    )
    return MemoryStore(
        app.db,
        KeywordSimilarityEngine(concept_expander=expander),
        concept_expander=expander,
    )


def _context_builder(app: BrainApp, project) -> ContextBuilder:
    return ContextBuilder(
        _memory_store(app),
        Path(project.path),
        app.config.indexing,
        project.id,
        app.config.retrieval,
    )


def _write_audit(task_dir: Path, task: Task, context: dict[str, Any]) -> None:
    task_dir.mkdir(parents=True, exist_ok=True)
    request_json = {
        "id": task.id,
        "project_id": task.project_id,
        "title": task.title,
        "description": task.description,
        "category": task.category,
        "status": task.status,
        "source": task.source,
    }
    (task_dir / "request.json").write_text(
        json.dumps(request_json, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    (task_dir / "context.json").write_text(
        json.dumps(context, indent=2, ensure_ascii=False), encoding="utf-8"
    )


def set_active_task(app: BrainApp, task: Task) -> None:
    state = BrainState.load(app.paths.state_path)
    state.active_project_id = task.project_id
    state.active_task_id = task.id
    state.active_task_title = task.title
    state.save(app.paths.state_path)


def clear_active_task(app: BrainApp) -> None:
    state = BrainState.load(app.paths.state_path)
    state.active_task_id = None
    state.active_task_title = None
    state.save(app.paths.state_path)


def get_active_task(app: BrainApp) -> tuple[int | None, str | None]:
    state = BrainState.load(app.paths.state_path)
    return state.active_task_id, state.active_task_title


def _task_still_open(app: BrainApp, task_id: int) -> bool:
    task = TaskRepository(app.db).get(task_id)
    if not task:
        return False
    closed = {
        TaskStatus.WAITING_REVIEW.value,
        TaskStatus.COMPLETED.value,
        TaskStatus.FAILED.value,
    }
    return task.status not in closed


def open_task(
    title: str,
    description: str = "",
    task_id: int | None = None,
) -> dict[str, Any]:
    """Brain → Agente: cria/reusa tarefa e devolve contexto."""
    app = BrainApp()
    try:
        try:
            project = app.resolve_project(None)
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

        repo = TaskRepository(app.db)
        if task_id:
            task = repo.get(task_id)
            if not task or task.project_id != project.id:
                return {"ok": False, "error": f"Tarefa #{task_id} não encontrada."}
        else:
            task = repo.create(
                project_id=project.id,
                title=title[:200],
                description=description,
                source="brain-loop",
            )

        git_commit = None
        if GitService.is_git_available():
            git_commit = GitService(Path(project.path)).status().commit

        task = repo.update_status(task.id, TaskStatus.SENIOR_REQUIRED)
        if git_commit:
            repo.set_git_commits(task.id, git_commit, None)

        ctx_obj = _context_builder(app, project).build(task, project.id)
        ctx = context_to_dict(ctx_obj)
        task_dir = app.paths.task_dir(slugify(project.name), task.id)
        _write_audit(task_dir, task, ctx)
        set_active_task(app, task)

        return {
            "ok": True,
            "task_id": task.id,
            "title": task.title,
            "context": ctx,
            "brief": format_agent_brief(ctx, task.id),
            "audit_dir": str(task_dir),
        }
    finally:
        app.close()


def build_evidence(app: BrainApp, project_id: int, changed_files: list[str]) -> list[dict[str, str]]:
    evidence = []
    for file_path in changed_files:
        row = app.db.query_one(
            "SELECT path FROM files WHERE project_id=? AND path=?",
            (project_id, file_path),
        )
        if row:
            evidence.append({"path": file_path})
    return evidence


def index_project(app: BrainApp, project) -> None:
    indexer = ProjectIndexer(app.db, app.config.indexing)
    indexer.index(project.id, Path(project.path))


def close_task(
    title: str | None = None,
    description: str = "",
    task_id: int | None = None,
    learning_file: Path | None = None,
    summary: str | None = None,
) -> dict[str, Any]:
    """Agente → Brain: submete tarefa e aplica learning."""
    app = BrainApp()
    try:
        try:
            project = app.resolve_project(None)
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

        active_id, active_title = get_active_task(app)
        task_id = task_id or active_id
        title = title or active_title or "Tarefa concluída"

        git_status = get_git_status(project.path)
        changed_files = git_status.get("changed_files", [])

        if changed_files:
            index_project(app, project)

        repo = TaskRepository(app.db)
        if task_id:
            task = repo.get(task_id)
            if not task or task.project_id != project.id:
                return {"ok": False, "error": f"Tarefa #{task_id} não encontrada."}
        else:
            task = repo.create(
                project_id=project.id,
                title=title[:200],
                description=description,
                source="brain-loop",
            )
            task_id = task.id
            repo.set_git_commits(task.id, git_status.get("commit"), None)

        task_dir = app.paths.task_dir(slugify(project.name), task.id)
        task_dir.mkdir(parents=True, exist_ok=True)

        extra: dict[str, Any] = {}
        if learning_file and learning_file.exists():
            extra = json.loads(learning_file.read_text(encoding="utf-8"))

        evidence = build_evidence(app, project.id, changed_files)
        result = {
            "status": "SUCCESS",
            "summary": summary or extra.get("summary") or f"Tarefa concluída. {len(evidence)} arquivo(s) com evidência.",
            "decision": "AUTO_EXECUTE_ALLOWED" if evidence else "REQUIRES_SENIOR",
            "confidence": 0.9 if evidence else 0.5,
            "requires_human_review": False,
            "approved_for_learning": bool(evidence or extra.get("rules_discovered") or extra.get("lessons")),
            "important_files": extra.get("important_files") or changed_files[:5],
            "affected_modules": extra.get("affected_modules") or [],
            "risks": extra.get("risks") or [],
            "rules_discovered": extra.get("rules_discovered") or [],
            "patterns_used": extra.get("patterns_used") or [],
            "lessons": extra.get("lessons") or [],
            "evidence": extra.get("evidence") or evidence,
        }

        (task_dir / "senior-response.json").write_text(
            json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        (task_dir / "evidence.json").write_text(
            json.dumps({"evidence": result["evidence"]}, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

        now = _now()
        app.db.execute(
            "UPDATE tasks SET status=?, updated_at=? WHERE id=?",
            (TaskStatus.WAITING_REVIEW.value, now, task.id),
        )
        app.db.execute(
            "INSERT INTO senior_sessions(task_id, provider, status, request_json, response_json, created_at)"
            " VALUES (?,?,?,?,?,?)",
            (
                task.id,
                "brain-loop",
                "SUCCESS",
                json.dumps({"contract_version": 1}),
                json.dumps(result, ensure_ascii=False),
                now,
            ),
        )

        learning_summary = None
        if result["approved_for_learning"] and app.config.learning.automatic_after_approval:
            from brain.learning_extractor import LearningExtractor

            learning = LearningPayload(
                rules=result["rules_discovered"],
                patterns=result["patterns_used"],
                lessons=result["lessons"],
                affected_modules=result["affected_modules"],
                risks=result["risks"],
                important_files=result["important_files"],
            )
            learning_summary = LearningExtractor(app.db).apply(learning, task.id, project.id)

        clear_active_task(app)

        out: dict[str, Any] = {"ok": True, "task_id": task.id, "evidence_count": len(result["evidence"])}
        if learning_summary:
            out["learning"] = {
                "rules": len(learning_summary.rules_created),
                "patterns": len(learning_summary.patterns_created),
                "lessons": len(learning_summary.lessons_created),
            }
        return out
    finally:
        app.close()


def inject_context_for_prompt(prompt: str, hook_data: dict[str, Any] | None = None) -> str | None:
    """Hook beforeSubmitPrompt/UserPromptSubmit: abre tarefa na 1ª mensagem técnica ou reutiliza ativa."""
    text = (prompt or "").strip()
    if not text or CASUAL_PROMPT.match(text):
        return None

    _bootstrap_workspace(hook_data)

    app = BrainApp()
    try:
        try:
            app.resolve_project(None)
        except Exception:
            return None

        active_id, _ = get_active_task(app)
        if active_id and _task_still_open(app, active_id):
            task_dir = None
            project = app.resolve_project(None)
            task_dir = app.paths.task_dir(slugify(project.name), active_id)
            ctx_path = task_dir / "context.json"
            if ctx_path.exists():
                ctx = json.loads(ctx_path.read_text(encoding="utf-8"))
                return format_agent_brief(ctx, active_id)

        title = text.split("\n", 1)[0][:200]
        result = open_task(title=title, description=text[:2000])
        if result.get("ok"):
            return result.get("brief")
        return None
    finally:
        app.close()


def submit_on_stop(hook_data: dict[str, Any] | None = None) -> dict[str, Any]:
    """Hook stop/Stop: fecha tarefa ativa se houver mudanças Git ou learning pendente."""
    _bootstrap_workspace(hook_data)

    app = BrainApp()
    try:
        try:
            project = app.resolve_project(None)
        except Exception:
            return {"ok": False, "skipped": True, "reason": "no_project"}

        active_id, active_title = get_active_task(app)
        if not active_id or not _task_still_open(app, active_id):
            return {"ok": False, "skipped": True, "reason": "no_active_task"}

        changed = get_git_changes(project.path)
        if not changed:
            return {"ok": False, "skipped": True, "reason": "no_git_changes", "task_id": active_id}

        return close_task(task_id=active_id, title=active_title)
    finally:
        app.close()
