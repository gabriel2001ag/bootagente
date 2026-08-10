from subprocess import CompletedProcess

from agents.search_agent import SearchAgent
from analysis.code_scanner import IgnoreMatcher


def test_search_text_python_fallback_finds_match(php_project):
    agent = SearchAgent(php_project)
    matches = agent._search_text_python("imprimirLote", max_results=10)
    assert any(m.file.endswith("Pedido.php") for m in matches)


def test_search_text_rg_or_fallback_consistent(php_project):
    agent = SearchAgent(php_project)
    matches = agent.search_text("tab_pedido")
    assert any("PedidoModel.php" in m.file for m in matches)


def test_search_text_rg_parses_windows_drive_path(php_project, monkeypatch):
    source = php_project / "app" / "Controllers" / "Pedido.php"
    output = f"{source}:12:public function imprimirLote(): void\n"

    monkeypatch.setattr(
        "agents.search_agent.subprocess.run",
        lambda *args, **kwargs: CompletedProcess(args=args, returncode=0, stdout=output, stderr=""),
    )

    matches = SearchAgent(php_project)._search_text_rg("imprimirLote", max_results=10)

    assert len(matches) == 1
    assert matches[0].file == "app/Controllers/Pedido.php"
    assert matches[0].line == 12


def test_search_files_by_name(php_project):
    agent = SearchAgent(php_project)
    files = agent.search_files_by_name("Pedido")
    assert any("Pedido.php" in f for f in files)
    assert any("PedidoModel.php" in f for f in files)


def test_search_agent_never_raises_without_rg(php_project, monkeypatch):
    monkeypatch.setattr(SearchAgent, "rg_available", staticmethod(lambda: False))
    agent = SearchAgent(php_project)
    matches = agent.search_text("PedidoController")
    assert isinstance(matches, list)
    assert len(matches) >= 1


class _FakeTask:
    def __init__(self, title, description=""):
        self.title = title
        self.description = description


def test_search_agent_run_returns_candidate_files(php_project):
    agent = SearchAgent(php_project)
    task = _FakeTask("Limitar intervalo de pedidos", "imprimirLote deve limitar o intervalo")
    result = agent.run(task, context=None)
    assert result.status.value in ("OK", "NO_MATCH")
    if result.status.value == "OK":
        assert any("Pedido" in f for f in result.data["candidate_files"])


def test_rg_results_are_post_filtered_with_normalized_windows_path(php_project, monkeypatch):
    ignored = php_project / "writable" / "session.txt"
    ignored.parent.mkdir()
    ignored.write_text("pedido secret", encoding="utf-8")
    included = php_project / "app" / "Controllers" / "Pedido.php"
    output = f"{ignored}:1:pedido secret\n{included}:1:pedido controller\n"
    monkeypatch.setattr(
        "agents.search_agent.subprocess.run",
        lambda *args, **kwargs: CompletedProcess(args=args, returncode=0, stdout=output, stderr=""),
    )
    matcher = IgnoreMatcher.from_config(["writable"], [])

    matches = SearchAgent(php_project, matcher)._search_text_rg("pedido", 10)

    assert [match.file for match in matches] == ["app/Controllers/Pedido.php"]


def test_rg_uses_literal_query_and_option_separator(php_project, monkeypatch):
    captured = {}
    def fake_run(args, **kwargs):
        captured["args"] = args
        return CompletedProcess(args=args, returncode=1, stdout="", stderr="")
    monkeypatch.setattr("agents.search_agent.subprocess.run", fake_run)

    SearchAgent(php_project)._search_text_rg("-pedido[", 10)

    assert "-F" in captured["args"]
    separator = captured["args"].index("--")
    assert captured["args"][separator + 1] == "-pedido["
    assert captured["args"][separator + 2] == str(php_project)


def test_rg_unexpected_return_code_falls_back_to_python(php_project, monkeypatch):
    monkeypatch.setattr(
        "agents.search_agent.subprocess.run",
        lambda *args, **kwargs: CompletedProcess(args=args, returncode=2, stdout="", stderr="bad"),
    )
    matches = SearchAgent(php_project)._search_text_rg("PedidoController", 10)
    assert any(match.file.endswith("Pedido.php") for match in matches)


def test_rg_post_filter_excludes_sensitive_glob(php_project, monkeypatch):
    sensitive = php_project / ".env.local"
    sensitive.write_text("PEDIDO_SECRET=x", encoding="utf-8")
    controller = php_project / "app" / "Controllers" / "Pedido.php"
    output = f"{sensitive}:1:PEDIDO_SECRET=x\n{controller}:1:PedidoController\n"
    monkeypatch.setattr(
        "agents.search_agent.subprocess.run",
        lambda *args, **kwargs: CompletedProcess(
            args=args, returncode=0, stdout=output, stderr=""
        ),
    )
    matcher = IgnoreMatcher.from_config([], [], [".env", ".env.*"])

    matches = SearchAgent(php_project, matcher)._search_text_rg("pedido", 10)

    assert [match.file for match in matches] == ["app/Controllers/Pedido.php"]
