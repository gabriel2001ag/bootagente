"""Project Brain CLI entrypoint (seção 5).

Each subcommand gets its own small `argparse.ArgumentParser` instead of one
giant nested-subparser tree — this keeps `brain task "title"` and
`brain task history` unambiguous without fighting argparse, and keeps each
command's code easy to read in isolation (seção 32: funções pequenas,
baixo acoplamento).

Priority implemented per seção 5/29: init, inspect, task, status, memory.
Lower-priority commands (`task history`, `senior status`, `learn`) are
implemented in a minimal, honest form.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from analysis.project_indexer import ProjectIndexer  # noqa: E402
from brain.database import Database  # noqa: E402
from brain.lessons import LessonRepository  # noqa: E402
from brain.models import Project  # noqa: E402
from brain.patterns import PatternRepository  # noqa: E402
from brain.projects import ProjectRepository  # noqa: E402
from brain.rules import RuleRepository  # noqa: E402
from brain.similarity import tokenize  # noqa: E402
from core.config import BrainConfig  # noqa: E402
from core.orchestrator import Orchestrator  # noqa: E402
from core.paths import BrainPaths  # noqa: E402
from core.state import BrainState  # noqa: E402
from core.task import TaskRepository  # noqa: E402
from git.git_service import GitService  # noqa: E402
from senior.senior_service import SeniorService  # noqa: E402
from senior.codex_workspace_bridge import (  # noqa: E402
    BridgeValidationError,
    CodexWorkspaceBridge,
)
from chat.service import ChatService, run_interactive_chat  # noqa: E402


class CliError(Exception):
    pass


class BrainApp:
    """Bootstraps config/db/state; resolves the active project."""

    def __init__(self, paths: BrainPaths | None = None, **sqlite_kwargs):
        self.paths = paths or BrainPaths.default()
        self.config = BrainConfig.load(self.paths.config_path)
        self.db = Database(self.paths.db_path, self.paths.migrations_dir, **sqlite_kwargs)
        self.project_repo = ProjectRepository(self.db)
        self.state = BrainState.load(self.paths.state_path)

    def resolve_project(self, project_arg: str | None = None) -> Project:
        if project_arg:
            if project_arg.isdigit():
                return self.project_repo.get_by_id(int(project_arg))
            resolved_path = str(Path(project_arg).resolve())
            project = self.project_repo.get_by_path(resolved_path)
            if project:
                return project
            raise CliError(f"Project not registered: {project_arg}. Run `brain init {project_arg}` first.")
        if self.state.active_project_id is None:
            raise CliError("No active project. Run `brain init <path>` first.")
        return self.project_repo.get_by_id(self.state.active_project_id)

    def set_active(self, project: Project) -> None:
        self.state.active_project_id = project.id
        self.state.save(self.paths.state_path)

    def close(self) -> None:
        self.db.close()


# ---------------------------------------------------------------- init ----
def cmd_init(rest: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="brain init")
    parser.add_argument("path", help="Path to the target project to register/index")
    parser.add_argument("--name", default=None, help="Friendly project name (default: folder name)")
    args = parser.parse_args(rest)

    target = Path(args.path)
    if not target.exists():
        raise CliError(f"Path does not exist: {target}")

    app = BrainApp()
    try:
        resolved = str(target.resolve())
        project = app.project_repo.get_or_create(resolved, name=args.name)
        indexer = ProjectIndexer(app.db, app.config.indexing)
        stats = indexer.index(project.id, Path(resolved))
        app.project_repo.touch_indexed(project.id, stats.primary_language)
        app.set_active(project)

        print(f"Initialized project '{project.name}' (id={project.id}) at {resolved}")
        print(
            f"Indexed {stats.files_indexed} new/changed file(s), {stats.files_unchanged} unchanged, "
            f"{stats.symbols_indexed} symbol(s), {stats.relationships_indexed} relationship(s)."
        )
        print(f"Primary language detected: {stats.primary_language or 'unknown'}")
        print(f"This project is now the active project for subsequent `brain` commands.")
    finally:
        app.close()
    return 0


# --------------------------------------------------------------- index ---
def cmd_index(rest: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="brain index")
    parser.add_argument("--project", default=None)
    parser.add_argument("--rebuild", action="store_true", help="Atomically clear derived index first")
    args = parser.parse_args(rest)

    app = BrainApp()
    try:
        project = app.resolve_project(args.project)
        indexer = ProjectIndexer(app.db, app.config.indexing)
        if args.rebuild:
            stats = indexer.rebuild(project.id, Path(project.path))
        else:
            stats = indexer.index(project.id, Path(project.path))
        app.project_repo.touch_indexed(project.id, stats.primary_language)
        mode = "Rebuilt" if args.rebuild else "Updated"
        print(
            f"{mode} project '{project.name}' (id={project.id}): "
            f"{stats.files_scanned} scanned, {stats.files_indexed} new/changed, "
            f"{stats.files_unchanged} unchanged, {stats.files_skipped} skipped."
        )
    finally:
        app.close()
    return 0


# -------------------------------------------------------------- inspect ---
def cmd_inspect(rest: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="brain inspect")
    parser.add_argument("target_type", nargs="?", choices=["file", "module"], default=None)
    parser.add_argument("target_value", nargs="?", default=None)
    parser.add_argument("--project", default=None)
    args = parser.parse_args(rest)

    app = BrainApp()
    try:
        project = app.resolve_project(args.project)
        if args.target_type == "file":
            if not args.target_value:
                raise CliError("Usage: brain inspect file <path>")
            _inspect_file(app, project, args.target_value)
        elif args.target_type == "module":
            if not args.target_value:
                raise CliError("Usage: brain inspect module <name>")
            _inspect_module(app, project, args.target_value)
        else:
            _inspect_project(app, project)
    finally:
        app.close()
    return 0


def _inspect_project(app: BrainApp, project: Project) -> None:
    files_n = app.db.query_one("SELECT COUNT(*) n FROM files WHERE project_id=?", (project.id,))["n"]
    symbols_n = app.db.query_one(
        "SELECT COUNT(*) n FROM symbols s JOIN files f ON f.id = s.file_id WHERE f.project_id=?",
        (project.id,),
    )["n"]
    tasks_n = app.db.query_one("SELECT COUNT(*) n FROM tasks WHERE project_id=?", (project.id,))["n"]

    print(f"Project: {project.name} ({project.path})")
    print(f"Primary language: {project.primary_language or 'unknown'}")
    print(f"Last indexed: {project.last_indexed_at or 'never'}")
    print(f"Files indexed: {files_n}")
    print(f"Symbols indexed: {symbols_n}")
    print(f"Tasks recorded: {tasks_n}")

    if GitService.is_git_available():
        status = GitService(Path(project.path)).status()
        if status.is_repo:
            print(f"Git branch: {status.branch}  commit: {status.commit}")
            print(f"Git dirty: {status.dirty}  untracked files: {len(status.untracked_files)}")
        else:
            print(f"Git: {status.error}")
    else:
        print("Git: git binary not found in PATH")


def _inspect_file(app: BrainApp, project: Project, file_path: str) -> None:
    normalized = file_path.replace("\\", "/")
    row = app.db.query_one("SELECT * FROM files WHERE project_id=? AND path=?", (project.id, normalized))
    if not row:
        print(f"File not indexed: {normalized}")
        print("(run `brain init <path>` again if the project changed since last index)")
        return
    print(f"File: {row['path']}")
    print(f"Language: {row['language']}  Size: {row['size']} bytes  Hash: {(row['hash'] or '')[:12]}")
    symbols = app.db.query("SELECT * FROM symbols WHERE file_id=? ORDER BY line_start", (row["id"],))
    print(f"Symbols ({len(symbols)}):")
    for s in symbols:
        prefix = f"{s['class_name']}::" if s["class_name"] else ""
        print(f"  L{s['line_start']}: {s['symbol_type']} {prefix}{s['name']}")


def _inspect_module(app: BrainApp, project: Project, module_name: str) -> None:
    rows = app.db.query(
        "SELECT * FROM files WHERE project_id=? AND path LIKE ? ORDER BY path",
        (project.id, f"%{module_name}%"),
    )
    print(f"Module '{module_name}': {len(rows)} matching file(s)")
    for row in rows:
        print(f"  {row['path']} ({row['language']})")


# ----------------------------------------------------------------- task ---
def cmd_task(rest: list[str]) -> int:
    if rest and rest[0] == "history":
        return _cmd_task_history(rest[1:])
    if rest and rest[0] == "refresh":
        return _cmd_task_refresh(rest[1:])

    parser = argparse.ArgumentParser(prog="brain task")
    parser.add_argument("title", help="Task title/description in natural language")
    parser.add_argument("--description", default="", help="Optional extended description")
    parser.add_argument("--project", default=None)
    args = parser.parse_args(rest)

    app = BrainApp()
    try:
        project = app.resolve_project(args.project)
        orchestrator = Orchestrator(app.db, app.config, app.paths, project)
        summary = orchestrator.run_task(args.title, description=args.description)
        _print_task_summary(summary)
    finally:
        app.close()
    return 0


def _cmd_task_refresh(rest: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="brain task refresh")
    parser.add_argument("task_id", type=int)
    parser.add_argument("--project", default=None)
    parser.add_argument("--title", default=None, help="Optional corrected title")
    parser.add_argument("--description", default=None, help="Optional corrected description")
    args = parser.parse_args(rest)
    app = BrainApp()
    try:
        project = app.resolve_project(args.project)
        summary = Orchestrator(app.db, app.config, app.paths, project).refresh_task(
            args.task_id, title=args.title, description=args.description
        )
        _print_task_summary(summary)
    except ValueError as exc:
        raise CliError(str(exc)) from exc
    finally:
        app.close()
    return 0


def _print_task_summary(summary) -> None:
    print(f"Task #{summary.task.id}: {summary.task.title}")
    print(f"Mode: {summary.mode.value}")
    print(f"Senior: {summary.senior_status.value}")
    print(f"Category: {summary.category}")
    print(f"Confidence: {summary.confidence}")
    print(f"Decision: {summary.decision.value}")
    print(f"Status: {summary.task.status}")
    print(f"Message: {summary.message}")
    if summary.warnings:
        print("Warnings:")
        for warning in summary.warnings:
            print(f"  - {warning}")
    files = ", ".join(summary.context.candidate_files) or "(none found)"
    print(f"Candidate files: {files}")
    print("No files were modified (Project Brain V1 is analysis/decision-only).")
    print(f"Audit trail: {summary.audit_dir}")


def _cmd_task_history(rest: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="brain task history")
    parser.add_argument("--project", default=None)
    parser.add_argument("--limit", type=int, default=10)
    args = parser.parse_args(rest)

    app = BrainApp()
    try:
        project = app.resolve_project(args.project)
        tasks = TaskRepository(app.db).list_for_project(project.id, limit=args.limit)
        if not tasks:
            print("No tasks recorded yet.")
            return 0
        for task in tasks:
            print(
                f"#{task.id} [{task.status}] ({task.created_at}) {task.title} "
                f"— decision={task.decision} confidence={task.confidence}"
            )
    finally:
        app.close()
    return 0


# --------------------------------------------------------------- status ---
def cmd_status(rest: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="brain status")
    parser.add_argument("--project", default=None)
    args = parser.parse_args(rest)

    app = BrainApp()
    try:
        project = app.resolve_project(args.project)
        senior_service = SeniorService(app.db, app.config)
        senior_status = senior_service.check_availability()

        print(f"Project: {project.name} ({project.path})")
        print(f"Senior provider: {app.config.senior.provider}  Status: {senior_status.value}")
        print(f"Fallback enabled: {app.config.fallback.enabled}")
        print(
            "Confidence thresholds: "
            f"auto_execute>={app.config.confidence.auto_execute} "
            f"requires_review>={app.config.confidence.requires_review} "
            f"analysis_only>={app.config.confidence.analysis_only}"
        )

        tasks = TaskRepository(app.db).list_for_project(project.id, limit=5)
        print(f"Recent tasks ({len(tasks)}):")
        for task in tasks:
            print(f"  #{task.id} [{task.status}] {task.title} (confidence={task.confidence})")

        rules_n = app.db.query_one("SELECT COUNT(*) n FROM rules WHERE approved=1")["n"]
        patterns_n = app.db.query_one("SELECT COUNT(*) n FROM patterns WHERE approved=1")["n"]
        lessons_n = app.db.query_one("SELECT COUNT(*) n FROM lessons WHERE approved=1")["n"]
        print(f"Knowledge base: {rules_n} rule(s), {patterns_n} pattern(s), {lessons_n} lesson(s)")
    finally:
        app.close()
    return 0


# --------------------------------------------------------------- memory ---
def cmd_memory(rest: list[str]) -> int:
    if not rest or rest[0] != "search":
        print('Usage: brain memory search "<query>" [--project P]')
        return 2
    parser = argparse.ArgumentParser(prog="brain memory search")
    parser.add_argument("query")
    parser.add_argument("--project", default=None)
    args = parser.parse_args(rest[1:])

    app = BrainApp()
    try:
        project = app.resolve_project(args.project)
        keywords = sorted(tokenize(args.query))
        rules = RuleRepository(app.db).search(keywords, project_id=project.id)
        lessons = LessonRepository(app.db).search(keywords, project_id=project.id)
        patterns = [
            p for p in PatternRepository(app.db).list_approved(project_id=project.id)
            if set(keywords) & {p.category.lower(), (p.trigger or "").lower()}
        ]

        print(f"Search: '{args.query}'  (keywords: {', '.join(keywords) or '(none)'})")
        print(f"Rules ({len(rules)}):")
        for rule in rules:
            print(f"  {rule.rule_code}: {rule.rule_text}")
        print(f"Lessons ({len(lessons)}):")
        for lesson in lessons:
            print(f"  {lesson.lesson_code}: {lesson.problem} -> {lesson.solution}")
        print(f"Patterns ({len(patterns)}):")
        for pattern in patterns:
            print(f"  {pattern.pattern_code}: {pattern.category}/{pattern.trigger}")
    finally:
        app.close()
    return 0


# --------------------------------------------------------------- senior ---
def cmd_senior(rest: list[str]) -> int:
    if not rest or rest[0] not in ("status", "pending", "context", "submit"):
        print("Usage: brain senior <status|pending|context TASK_ID|submit TASK_ID --file RESULT.json>")
        return 2
    action = rest[0]
    app = BrainApp()
    try:
        bridge = CodexWorkspaceBridge(app.db, app.paths, app.config)
        if action == "status":
            extension = bridge.discover_extension()
            print("Integration: codex-vscode-inverted")
            print("Programmatic extension API: not assumed")
            print(f"Extension: {extension['id']}@{extension['version']}" if extension else "Extension: not found")
            print(f"Pending tasks: {len(bridge.pending())}")
        elif action == "pending":
            for task in bridge.pending():
                print(f"#{task.id} [{task.status}] {task.title}")
        elif action == "context":
            parser = argparse.ArgumentParser(prog="brain senior context")
            parser.add_argument("task_id", type=int)
            args = parser.parse_args(rest[1:])
            print(json.dumps(bridge.context(args.task_id), indent=2, ensure_ascii=False))
        else:
            parser = argparse.ArgumentParser(prog="brain senior submit")
            parser.add_argument("task_id", type=int)
            parser.add_argument("--file", required=True)
            args = parser.parse_args(rest[1:])
            payload = json.loads(Path(args.file).read_text(encoding="utf-8"))
            result = bridge.submit(args.task_id, payload)
            print(f"Task #{result.task.id}: {result.task.status}")
            if result.learning:
                print(
                    f"Learning: {len(result.learning.rules_created)} rule(s), "
                    f"{len(result.learning.patterns_created)} pattern(s), "
                    f"{len(result.learning.lessons_created)} lesson(s)"
                )
    except (BridgeValidationError, json.JSONDecodeError, OSError) as exc:
        raise CliError(str(exc)) from exc
    finally:
        app.close()
    return 0


# ----------------------------------------------------------------- learn --
def cmd_learn(rest: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="brain learn")
    parser.add_argument("--project", default=None)
    args = parser.parse_args(rest)

    app = BrainApp()
    try:
        project = app.resolve_project(args.project)
        print(
            "In V1, `brain learn` reflects knowledge already captured automatically "
            "after Senior-reviewed tasks (seção 12/24). Manual extraction from an "
            "arbitrary diff without a Senior/mock structured output is a V2 feature."
        )
        lessons = LessonRepository(app.db).list_approved(project_id=project.id)
        print(f"Lessons recorded for this project: {len(lessons)}")
        for lesson in lessons[-5:]:
            print(f"  {lesson.lesson_code}: {lesson.problem}")
    finally:
        app.close()
    return 0


# ------------------------------------------------------------------ chat --
def cmd_chat(rest: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="brain chat")
    parser.add_argument("--project", default=None)
    args = parser.parse_args(rest)
    app = BrainApp()
    try:
        project = app.resolve_project(args.project)
        run_interactive_chat(ChatService(app.db, app.config, app.paths, project))
    finally:
        app.close()
    return 0


# ------------------------------------------------------------------ main --
COMMANDS = {
    "init": cmd_init,
    "index": cmd_index,
    "inspect": cmd_inspect,
    "task": cmd_task,
    "status": cmd_status,
    "memory": cmd_memory,
    "senior": cmd_senior,
    "learn": cmd_learn,
    "chat": cmd_chat,
}


def print_help() -> None:
    print("Project Brain CLI")
    print("Usage: brain <command> [args]")
    print("Commands:")
    print('  init <path>                    Register and index a target project')
    print("  index [--rebuild]              Update or rebuild only the derived index")
    print("  inspect [file <path>|module <name>]   Inspect project/file/module")
    print('  task "<title>" [--description]  Submit a task')
    print("  task history [--limit N]       List recent tasks")
    print("  task refresh <id>              Safely rebuild context for an existing task")
    print("  status                         Show project + Senior + knowledge base status")
    print('  memory search "<query>"         Search rules/patterns/lessons')
    print("  senior status|pending          Inspect the inverted Codex workspace bridge")
    print("  senior context <task-id>       Print prepared context for Codex")
    print("  senior submit <id> --file JSON Validate and record Codex result")
    print("  learn                          Show captured learning for the active project")
    print("  chat                           Start the Project Brain interactive chat")


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] in ("-h", "--help", "help"):
        print_help()
        return 0 if argv else 2

    command, rest = argv[0], argv[1:]
    handler = COMMANDS.get(command)
    if handler is None:
        print(f"Unknown command: {command}")
        print_help()
        return 2

    try:
        return handler(rest)
    except CliError as exc:
        print(f"Error: {exc}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
