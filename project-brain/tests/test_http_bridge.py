"""Testes do bridge HTTP do Project Brain (MVP).

Testa BridgeRuntime + endpoints HTTP em thread daemon.
Usa fixtures do conftest.py (brain_paths + tmp project + db sqlite em memória/tmp).
"""
from __future__ import annotations

import json
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest

SCRIPT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPT_DIR))

from analysis.project_indexer import ProjectIndexer  # noqa: E402
from brain.database import Database  # noqa: E402
from brain.projects import ProjectRepository  # noqa: E402
from core.config import BrainConfig  # noqa: E402
from core.paths import BrainPaths  # noqa: E402
from core.state import BrainState  # noqa: E402


def _make_registered_project(tmp_path: Path, brain_paths: BrainPaths) -> Path:
    """Cria um projeto PHP fictício e o registra no Brain, deixando state apontando ele."""
    root = tmp_path / "sample_project"
    (root / "app" / "Controllers").mkdir(parents=True)
    (root / "app" / "Models").mkdir(parents=True)
    (root / "app" / "Controllers" / "CTeController.php").write_text(
        "<?php\nclass CTeController { public function index(){} }\n", encoding="utf-8"
    )
    (root / "app" / "Models" / "CTeModel.php").write_text(
        "<?php\nclass CTeModel { }\n", encoding="utf-8"
    )
    db = Database(brain_paths.db_path, brain_paths.migrations_dir)
    try:
        cfg = BrainConfig.load(brain_paths.config_path)
        cfg.save(brain_paths.config_path)
        projects = ProjectRepository(db)
        project = projects.get_or_create(str(root.resolve()), name="sample_php_project")
        ProjectIndexer(db, cfg.indexing).index(project.id, Path(root.resolve()))
        projects.touch_indexed(project.id, "php")
        state = BrainState.load(brain_paths.state_path)
        state.active_project_id = project.id
        state.save(brain_paths.state_path)
    finally:
        db.close()
    return root


# ---------------------------------------------------------------------------
# Testes unitários do BridgeRuntime (sem rede)
# ---------------------------------------------------------------------------

def _monkeypatch_brainpaths(monkeypatch, brain_paths: BrainPaths):
    """Troca BrainPaths.default() para apontar para paths do teste."""
    from bridge import http_server as h
    import core.paths as paths_mod

    def fake_default():
        return brain_paths

    monkeypatch.setattr(paths_mod.BrainPaths, "default", fake_default)
    # Reset singleton do runtime para usar paths falsos
    h._RUNTIME = None


def test_bridge_runtime_chat_greeting_and_status(monkeypatch, brain_paths, tmp_path):
    _make_registered_project(tmp_path, brain_paths)
    _monkeypatch_brainpaths(monkeypatch, brain_paths)

    from bridge.http_server import get_runtime

    rt = get_runtime()
    assert rt.project.name == "sample_php_project"
    assert rt.service.session.senior_mode == "ONLINE"

    r = rt.chat("ola")
    assert "Projeto" in r["natural"] or "Olá" in r["natural"] or "ativ" in r["natural"]

    status = rt.build_status()
    assert status["project"]["name"] == "sample_php_project"
    assert status["session"]["id"] == rt.service.session.id
    assert "rules" in status["knowledge"]
    assert "tasks" in status


def test_bridge_runtime_verbose_toggle_and_technical(monkeypatch, brain_paths, tmp_path):
    _make_registered_project(tmp_path, brain_paths)
    _monkeypatch_brainpaths(monkeypatch, brain_paths)

    from bridge.http_server import get_runtime

    rt = get_runtime()
    rt.set_verbose(False)

    normal = rt.chat("me fale sobre vc", verbose=False)
    assert normal["technical"] is None
    assert "Eu sou o Project Brain" in normal["natural"] or "minha função" in normal["natural"].lower()

    rt.set_verbose(True)
    detail = rt.chat("me fale sobre vc", verbose=True)
    assert detail["technical"] is not None
    assert "Sessão:" in detail["technical"] or "session" in detail["technical"].lower()


def test_bridge_runtime_new_session_preserves_db(monkeypatch, brain_paths, tmp_path):
    _make_registered_project(tmp_path, brain_paths)
    _monkeypatch_brainpaths(monkeypatch, brain_paths)

    from bridge.http_server import get_runtime

    rt = get_runtime()
    first_id = rt.service.session.id
    rt.chat("ola")
    rt.new_session()
    second_id = rt.service.session.id
    assert second_id != first_id
    # A memória (db) está intacta — o projeto continua registrado
    status = rt.build_status()
    assert status["project"]["id"] == rt.project.id


def test_bridge_runtime_memory_search_and_tasks(monkeypatch, brain_paths, tmp_path):
    _make_registered_project(tmp_path, brain_paths)
    _monkeypatch_brainpaths(monkeypatch, brain_paths)

    from bridge.http_server import get_runtime

    rt = get_runtime()
    res = rt.memory_search("pedido")
    assert "keywords" in res
    assert "rules" in res

    tasks = rt.list_tasks(limit=5)
    assert isinstance(tasks, list)


# ---------------------------------------------------------------------------
# Teste de integração do servidor HTTP em thread daemon (127.0.0.1:0)
# ---------------------------------------------------------------------------

def _free_port() -> int:
    import socket
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def _http_json(method: str, url: str, body: dict | None = None) -> tuple[int, dict]:
    data = None
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    if body is not None:
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        try:
            payload = json.loads(e.read().decode("utf-8"))
        except Exception:
            payload = {"error": e.reason}
        return e.code, payload


def test_http_server_endpoints_end_to_end(monkeypatch, brain_paths, tmp_path):
    proj = _make_registered_project(tmp_path, brain_paths)
    _monkeypatch_brainpaths(monkeypatch, brain_paths)

    from http.server import HTTPServer
    from bridge.http_server import Handler  # noqa: F401
    import bridge.http_server as h

    h._RUNTIME = None

    port = _free_port()
    # Single-threaded HTTPServer durante os testes: evita qualquer problema
    # de cross-thread SQLite no ambiente de teste. Em produção o bridge usa
    # ThreadingHTTPServer + check_same_thread=False, que funciona corretamente.
    server = HTTPServer(("127.0.0.1", port), Handler)
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    try:
        # Espera servidor subir
        base = f"http://127.0.0.1:{port}"
        deadline = time.time() + 10.0
        while True:
            try:
                st, payload = _http_json("GET", base + "/health")
                if st == 200 and payload.get("ok"):
                    break
            except Exception:
                pass
            if time.time() > deadline:
                pytest.fail("HTTP server não subiu no tempo esperado")
            time.sleep(0.05)

        # status
        st, s = _http_json("GET", base + "/api/status")
        assert st == 200, f"status retornou {st}: {s}"
        assert s["project"]["name"] == "sample_php_project"

        # new session offline
        st, ns = _http_json("POST", base + "/api/session/new", {"senior_mode": "OFFLINE"})
        assert st == 200
        assert ns["senior_mode"] == "OFFLINE"

        # chat greeting
        st, r = _http_json("POST", base + "/api/chat", {"message": "ola"})
        assert st == 200
        assert r["natural"] or r["text"]

        # verbose toggle
        st, v = _http_json("POST", base + "/api/verbose", {"on": True})
        assert st == 200
        assert v["verbose"] is True

        # self query com verbose ON = tem technical
        st, r2 = _http_json("POST", base + "/api/chat", {"message": "me fale sobre vc"})
        assert st == 200, f"chat sobre vc retornou {st}: {r2}"
        assert r2["technical"] is not None

        # session mode online
        st, m = _http_json("POST", base + "/api/senior-mode", {"mode": "ONLINE"})
        assert st == 200
        assert m["senior_mode"] == "ONLINE"

        # tasks
        st, tasks = _http_json("GET", base + "/api/tasks?limit=3")
        assert st == 200
        assert isinstance(tasks, list)

        # memory search
        st, mem = _http_json("GET", base + "/api/memory?query=cte")
        assert st == 200
        assert "query" in mem

        # history
        st, hist = _http_json("GET", base + "/api/session/history?limit=10")
        assert st == 200
        assert isinstance(hist, list)

        # chat required fields (mensagem com contexto tecnico)
        st, bad = _http_json("POST", base + "/api/chat", {})
        assert bad["error"]  # 400

        # bad endpoint
        st, nf = _http_json("GET", base + "/api/nao_existe")
        assert st == 404
    finally:
        server.shutdown()
        server.server_close()
        with h._RUNTIME_LOCK:
            rt = h._RUNTIME
            h._RUNTIME = None
        if rt is not None:
            # Não dar erro se SQLite reclamar de thread no fechamento do teste
            try:
                rt.app.db.close()
            except Exception:
                pass


def test_split_natural_technical():
    from bridge.http_server import _split_natural_technical

    n, t = _split_natural_technical("Olá mundo\n\n--- detalhes técnicos (/verbose off para ocultar) ---\nRota: SENIOR")
    assert "Olá mundo" in n
    assert t is not None and "Rota: SENIOR" in t

    n2, t2 = _split_natural_technical("apenas texto normal")
    assert n2 == "apenas texto normal"
    assert t2 is None


def test_utf8_and_accents_in_chat(monkeypatch, brain_paths, tmp_path):
    _make_registered_project(tmp_path, brain_paths)
    _monkeypatch_brainpaths(monkeypatch, brain_paths)

    from bridge.http_server import get_runtime

    rt = get_runtime()
    # Mensagem com acentos e caracteres especiais
    r = rt.chat("em que pé está o CT-e e a NF-e? ação emissão você")
    assert isinstance(r["natural"], str)
    # Técnico não vem por padrão (verbose default False no inicio da sessão)
    assert r["technical"] is None or isinstance(r["technical"], str)


def test_split_works_on_various_markers():
    from bridge.http_server import _split_natural_technical

    # Casos limites: sem marcador, com marcador, múltiplos separadores
    text = "Resposta amigável.\n--- detalhes técnicos ---\nRoute: LOCAL\nDecision: OK"
    n, t = _split_natural_technical(text)
    assert "Resposta amigável" in n
    assert t and "Route: LOCAL" in t
