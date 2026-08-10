"""Project Brain HTTP Bridge for VS Code Sidebar (stdlib only, no deps).

Endpoints (all JSON, bind 127.0.0.1 only):
  GET  /health                       -> liveness + brain status
  GET  /api/status                   -> project + git + senior + counts
  GET  /api/session                  -> current chat session
  POST /api/session/new              -> create new chat session (body: {senior_mode?})
  POST /api/chat                     -> {message, verbose?, senior_mode?}
                                          -> {text, technical?, task_id, session_id}
  POST /api/verbose                  -> {on: bool}
  POST /api/senior-mode              -> {mode: "ONLINE"|"OFFLINE"}
  GET  /api/tasks?limit=10           -> recent tasks
  GET  /api/memory?query=q           -> rules/patterns/lessons summary
  GET  /api/session/history?limit=50 -> chat messages
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import threading
from dataclasses import asdict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

_SCRIPT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_SCRIPT_DIR))

from brain.models import Project  # noqa: E402
from brain.projects import ProjectRepository  # noqa: E402
from chat.service import ChatReply, ChatService  # noqa: E402
from cli.main import BrainApp  # noqa: E402
from core.task import TaskRepository  # noqa: E402
from git.git_service import GitService  # noqa: E402
from senior.senior_service import SeniorService  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    stream=sys.stderr,
)
log = logging.getLogger("brain.http")

_TECHNICAL_MARKER = "--- detalhes técnicos"


def _split_natural_technical(full_text: str) -> tuple[str, str | None]:
    """Split verbose output into user-friendly paragraph + technical block."""
    if _TECHNICAL_MARKER in full_text:
        natural, _, technical = full_text.partition(_TECHNICAL_MARKER)
        technical = technical.split("---", 1)[-1] if "---" in technical else technical
        return natural.strip(), technical.strip() or None
    return full_text.strip(), None


class BridgeRuntime:
    """Holds active BrainApp + ChatService for the process."""

    _lock = threading.Lock()

    def __init__(self, project_path_override: str | None = None):
        self.app = BrainApp(check_same_thread=False)
        self.project = self._resolve_project(project_path_override)
        self.app.set_active(self.project)
        self.service = ChatService(
            self.app.db, self.app.config, self.app.paths, self.project
        )

    def _resolve_project(self, override: str | None) -> Project:
        if override:
            resolved = str(Path(override).resolve())
            existing = self.app.project_repo.get_by_path(resolved)
            if existing:
                return existing
            raise RuntimeError(
                f"Project not registered: {resolved}. Run `brain init {resolved}` first."
            )
        return self.app.resolve_project()

    # --- Rebuild ChatService for a new session (keeps memory + db intact) ---
    def new_session(self, senior_mode: str | None = None) -> None:
        with self._lock:
            if senior_mode:
                self.service.session = self.service.sessions.set_senior_mode(
                    self.service.session.id, senior_mode
                )
            self.service = ChatService(
                self.app.db, self.app.config, self.app.paths, self.project
            )
            if senior_mode:
                self.service.session = self.service.sessions.set_senior_mode(
                    self.service.session.id, senior_mode
                )

    def set_verbose(self, on: bool) -> None:
        with self._lock:
            self.service.verbose = bool(on)

    def set_senior_mode(self, mode: str) -> None:
        mode_upper = mode.upper()
        if mode_upper not in {"ONLINE", "OFFLINE"}:
            raise ValueError("senior mode must be ONLINE or OFFLINE")
        with self._lock:
            self.service.session = self.service.sessions.set_senior_mode(
                self.service.session.id, mode_upper
            )
            self.service.sessions.get(self.service.session.id)

    # --- Status (git + project + counts) ---
    def build_status(self) -> dict[str, Any]:
        with self._lock:
            return self._build_status_locked()

    def _build_status_locked(self) -> dict[str, Any]:
        counts = {
            table: self.app.db.query_one(
                f"SELECT COUNT(*) n FROM {table} WHERE approved=1 AND "
                "(project_id IS NULL OR project_id=?)",
                (self.project.id,),
            )["n"]
            for table in ("rules", "patterns", "lessons")
        }
        task_counts = self.app.db.query_one(
            "SELECT COUNT(*) total, "
            "SUM(CASE WHEN status='SENIOR_REQUIRED' THEN 1 ELSE 0 END) pending "
            "FROM tasks WHERE project_id=?",
            (self.project.id,),
        )

        git_status = {"is_repo": False}
        if GitService.is_git_available():
            gs = GitService(Path(self.project.path))
            g = gs.status()
            git_status = {
                "is_repo": g.is_repo,
                "branch": g.branch,
                "commit": g.commit[:12] if g.commit else None,
                "dirty": g.dirty,
                "changed_files": len(g.changed_files),
                "untracked_files": len(g.untracked_files),
                "error": g.error,
            }

        try:
            senior_status = SeniorService(
                self.app.db, self.app.config
            ).check_availability().value
        except Exception:
            senior_status = "UNKNOWN"

        return {
            "project": {
                "id": self.project.id,
                "name": self.project.name,
                "path": self.project.path,
                "primary_language": self.project.primary_language,
                "last_indexed_at": self.project.last_indexed_at,
            },
            "git": git_status,
            "session": {
                "id": self.service.session.id,
                "status": self.service.session.status,
                "senior_mode": self.service.session.senior_mode,
                "verbose": self.service.verbose,
                "created_at": self.service.session.created_at,
            },
            "senior": {
                "provider": self.app.config.senior.provider,
                "enabled": self.app.config.senior.enabled,
                "status": senior_status,
            },
            "knowledge": {
                "rules": counts["rules"],
                "patterns": counts["patterns"],
                "lessons": counts["lessons"],
            },
            "tasks": {
                "total": task_counts["total"],
                "pending_senior": task_counts["pending"] or 0,
            },
        }

    def list_tasks(self, limit: int = 10) -> list[dict[str, Any]]:
        with self._lock:
            rows = TaskRepository(self.app.db).list_for_project(
                self.project.id, limit=limit
            )
            return [
                {
                    "id": t.id,
                    "title": t.title,
                    "status": t.status,
                    "decision": t.decision,
                    "confidence": t.confidence,
                    "source": t.source,
                    "created_at": t.created_at,
                    "updated_at": t.updated_at,
                }
                for t in rows
            ]

    def memory_search(self, query: str) -> dict[str, Any]:
        with self._lock:
            from brain.similarity import tokenize
            from brain.lessons import LessonRepository
            from brain.patterns import PatternRepository
            from brain.rules import RuleRepository

            keywords = sorted(tokenize(query))
            rules = RuleRepository(self.app.db).search(keywords, project_id=self.project.id)
            lessons = LessonRepository(self.app.db).search(keywords, project_id=self.project.id)
            patterns = [
                p
                for p in PatternRepository(self.app.db).list_approved(project_id=self.project.id)
                if set(keywords) & {p.category.lower(), (p.trigger or "").lower()}
            ]
            return {
                "query": query,
                "keywords": keywords,
                "rules": [
                    {"code": r.rule_code, "text": r.rule_text}
                    for r in rules
                ],
                "patterns": [
                    {"code": p.pattern_code, "category": p.category, "trigger": p.trigger}
                    for p in patterns
                ],
                "lessons": [
                    {"code": l.lesson_code, "problem": l.problem, "solution": l.solution}
                    for l in lessons
                ],
            }

    def chat(self, message: str, verbose: bool | None = None,
             senior_mode: str | None = None) -> dict[str, Any]:
        with self._lock:
            if senior_mode:
                self.set_senior_mode(senior_mode)
            prev_verbose = self.service.verbose
            if verbose is not None:
                self.service.verbose = bool(verbose)
            internal_verbose = self.service.verbose
            self.service.verbose = True
            try:
                reply: ChatReply = self.service.handle(message)
            finally:
                self.service.verbose = prev_verbose if verbose is None else bool(verbose)
        natural, technical = _split_natural_technical(reply.text)
        if not internal_verbose:
            technical = None
        return {
            "session_id": self.service.session.id,
            "task_id": reply.task_id,
            "exit_requested": reply.exit_requested,
            "text": natural if technical is None else reply.text if internal_verbose else natural,
            "natural": natural,
            "technical": technical,
            "verbose_mode": internal_verbose,
            "senior_mode": self.service.session.senior_mode,
        }

    def history(self, limit: int = 50) -> list[dict[str, Any]]:
        with self._lock:
            msgs = self.service.sessions.recent(self.service.session.id, limit=limit)
            return [asdict(m) for m in msgs]

    def close(self) -> None:
        self.app.close()


_RUNTIME: BridgeRuntime | None = None
_RUNTIME_LOCK = threading.Lock()


def get_runtime(project_path: str | None = None) -> BridgeRuntime:
    global _RUNTIME
    with _RUNTIME_LOCK:
        if _RUNTIME is None:
            _RUNTIME = BridgeRuntime(project_path)
        return _RUNTIME


class Handler(BaseHTTPRequestHandler):
    server_version = "ProjectBrainBridge/1.0"

    # --- helpers ---
    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
        log.info("%s - %s", self.address_string(), format % args)

    def _send_json(self, status: int, payload: Any) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET,POST,OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _read_json_body(self) -> Any:
        length = int(self.headers.get("Content-Length", "0") or "0")
        if length <= 0:
            return {}
        raw = self.rfile.read(length)
        if not raw:
            return {}
        return json.loads(raw.decode("utf-8"))

    def _query(self) -> dict[str, list[str]]:
        return parse_qs(urlparse(self.path).query)

    # --- verbs ---
    def do_OPTIONS(self) -> None:  # noqa: N802
        self._send_json(204, {})

    def do_GET(self) -> None:  # noqa: N802
        try:
            parsed = urlparse(self.path)
            path = parsed.path.rstrip("/") or "/"
            if path == "/health":
                rt = get_runtime()
                self._send_json(200, {
                    "ok": True,
                    "project": rt.project.name,
                    "session_id": rt.service.session.id,
                })
                return
            if path == "/api/status":
                self._send_json(200, get_runtime().build_status())
                return
            if path == "/api/session":
                rt = get_runtime()
                s = rt.service.session
                self._send_json(200, {
                    "id": s.id, "status": s.status,
                    "senior_mode": s.senior_mode, "verbose": rt.service.verbose,
                })
                return
            if path == "/api/tasks":
                q = self._query()
                limit = int((q.get("limit", ["10"])[0]))
                self._send_json(200, get_runtime().list_tasks(limit))
                return
            if path == "/api/memory":
                q = self._query()
                query = (q.get("query", [""])[0]).strip()
                if not query:
                    self._send_json(400, {"error": "missing query parameter"})
                    return
                self._send_json(200, get_runtime().memory_search(query))
                return
            if path == "/api/session/history":
                q = self._query()
                limit = int((q.get("limit", ["50"])[0]))
                self._send_json(200, get_runtime().history(limit))
                return
            self._send_json(404, {"error": "not found", "path": path})
        except Exception as exc:  # pragma: no cover - defensive
            log.exception("GET %s failed", self.path)
            self._send_json(500, {"error": f"Não consegui atender a requisição: {type(exc).__name__}"})

    def do_POST(self) -> None:  # noqa: N802
        try:
            parsed = urlparse(self.path)
            path = parsed.path.rstrip("/") or "/"
            body = self._read_json_body()

            if path == "/api/chat":
                message = (body.get("message") or "").strip()
                if not message:
                    self._send_json(400, {"error": "message is required"})
                    return
                result = get_runtime().chat(
                    message,
                    verbose=body.get("verbose"),
                    senior_mode=body.get("senior_mode"),
                )
                self._send_json(200, result)
                return

            if path == "/api/session/new":
                rt = get_runtime()
                rt.new_session(senior_mode=body.get("senior_mode"))
                s = rt.service.session
                self._send_json(200, {
                    "ok": True,
                    "session_id": s.id,
                    "senior_mode": s.senior_mode,
                    "verbose": rt.service.verbose,
                })
                return

            if path == "/api/verbose":
                on = bool(body.get("on", True))
                rt = get_runtime()
                rt.set_verbose(on)
                self._send_json(200, {"ok": True, "verbose": rt.service.verbose})
                return

            if path == "/api/senior-mode":
                mode = (body.get("mode") or "").strip().upper()
                if mode not in {"ONLINE", "OFFLINE"}:
                    self._send_json(400, {"error": "mode must be ONLINE or OFFLINE"})
                    return
                rt = get_runtime()
                rt.set_senior_mode(mode)
                self._send_json(200, {"ok": True, "senior_mode": rt.service.session.senior_mode})
                return

            self._send_json(404, {"error": "not found", "path": path})
        except json.JSONDecodeError:
            self._send_json(400, {"error": "invalid JSON body"})
        except Exception as exc:  # pragma: no cover - defensive
            log.exception("POST %s failed", self.path)
            self._send_json(500, {
                "error": "Não consegui acessar o Project Brain.",
                "detail": f"{type(exc).__name__}: {exc}",
            })


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="brain-bridge", description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=int(__import__("os").environ.get("BRAIN_BRIDGE_PORT", "8765")))
    parser.add_argument("--project", default=None, help="Optional project path to auto-resolve")
    args = parser.parse_args(argv)

    if args.host != "127.0.0.1":
        log.warning("Binding to non-loopback %s is NOT recommended (exposes Brain).", args.host)

    # Primeiro acesso ao runtime: falha cedo se projeto não estiver registrado.
    try:
        get_runtime(args.project)
    except Exception as exc:
        print(f"[brain-bridge] ERRO ao inicializar: {exc}", file=sys.stderr)
        return 1

    server = ThreadingHTTPServer((args.host, args.port), Handler)
    log.info("Project Brain Bridge ouvindo em http://%s:%d", args.host, args.port)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        log.info("Encerrando bridge por interrupção.")
    finally:
        server.server_close()
        with _RUNTIME_LOCK:
            if _RUNTIME:
                _RUNTIME.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
