from brain.lessons import LessonRepository
from brain.patterns import PatternRepository
from brain.projects import ProjectRepository
from brain.rules import RuleRepository
from chat.service import ChatService, run_interactive_chat
from chat.classifier import ChatMessageCategory, ChatMessageClassifier
import pytest


def _service(db, config, brain_paths, php_project):
    project = ProjectRepository(db).get_or_create(str(php_project), name="sample")
    for code, text in (
        ("RULE-PEDIDO-001", "Ao alterar itens do pedido preservar estados protegidos."),
        ("RULE-PEDIDO-002", "Ao alterar itens do pedido preservar estoque."),
        ("RULE-PEDIDO-003", "Ao alterar pedido preservar parcelas e boletos."),
    ):
        RuleRepository(db).add(code, "orders", text, project_id=project.id)
    for code, trigger in (
        ("PATTERN-PEDIDO-001", "alterar itens de pedido"),
        ("PATTERN-PEDIDO-002", "recalcular fiscal do item pedido"),
    ):
        PatternRepository(db).add(
            code, "orders", trigger=trigger, procedure=["validar", "persistir"],
            project_id=project.id,
        )
    for code, problem, solution in (
        ("LESSON-PEDIDO-001", "Alterar item como CRUD causa inconsistência.", "Preservar estoque."),
        ("LESSON-PEDIDO-002", "Cálculo fiscal isolado do item do pedido diverge.", "Reutilizar o snapshot fiscal."),
    ):
        LessonRepository(db).add(code, problem, solution, project_id=project.id)
    return ChatService(db, config, brain_paths, project)


def test_chat_task_2_offline_reuses_memory_without_senior(db, config, brain_paths, php_project):
    service = _service(db, config, brain_paths, php_project)
    service.handle("/offline")
    service.handle("/verbose on")
    reply = service.handle(
        "Analisar o que deve ser considerado antes de alterar itens de um pedido existente"
    )

    assert "Rules: 3" in reply.text
    assert "Patterns: 2" in reply.text
    assert "Lessons: 2" in reply.text
    assert "Route: ANALYSIS_ONLY" in reply.text
    assert "Senior handoff ready" not in reply.text
    assert reply.task_id is not None


def test_chat_unknown_request_waits_for_senior_offline(db, config, brain_paths, php_project):
    service = _service(db, config, brain_paths, php_project)
    service.handle("/offline")
    service.handle("/verbose on")
    reply = service.handle("Investigue uma inconsistência inédita no protocolo lunar")

    assert "Route: WAITING_FOR_SENIOR" in reply.text
    assert "REQUIRES_SENIOR" in reply.text
    assert "não tenho conhecimento suficiente" in reply.text
    assert "Codex está indisponível" in reply.text


def test_interactive_chat_startup_help_and_exit(db, config, brain_paths, php_project):
    service = _service(db, config, brain_paths, php_project)
    commands = iter(["/help", "/exit"])
    output: list[str] = []

    run_interactive_chat(service, input_fn=lambda _: next(commands), output_fn=output.append)

    assert output[0] == "Project Brain"
    assert any("/memory <query>" in line for line in output)
    assert service.sessions.get(service.session.id).status == "CLOSED"
    with pytest.raises(RuntimeError, match="closed"):
        service.handle("/status")


def test_chat_online_unknown_request_prepares_gateway_handoff(
    db, config, brain_paths, php_project
):
    service = _service(db, config, brain_paths, php_project)
    service.handle("/verbose on")

    reply = service.handle("Investigue uma inconsistência inédita no protocolo lunar")

    assert "Route: SENIOR" in reply.text
    assert f"Senior handoff ready: brain senior context {reply.task_id}" in reply.text
    assert f"#{reply.task_id}" in service.handle("/pending").text
    assert "Vou precisar do Codex Senior" in reply.text


def test_chat_commands_and_usage_counter(db, config, brain_paths, php_project):
    service = _service(db, config, brain_paths, php_project)

    assert "Project:" in service.handle("/project").text
    assert "Session:" in service.handle("/status").text
    assert "RULE-PEDIDO" in service.handle("/memory pedido").text
    service.handle("/offline")
    assert "ONLINE" in service.handle("/online").text
    service.handle("/offline")
    task_reply = service.handle(
        "Analisar o que considerar antes de alterar itens de um pedido existente"
    )
    assert f"#{task_reply.task_id}" in service.handle("/tasks").text
    assert "TASK:" in service.handle("/context").text
    assert "TASK:" in service.handle("/task").text
    assert "Unknown command" in service.handle("/nao-existe").text
    assert db.query_one(
        "SELECT SUM(times_used) n FROM rules WHERE project_id=?", (service.project.id,)
    )["n"] > 0


@pytest.mark.parametrize("message", ["ola", "oi", "bom dia", "tudo bem?"])
def test_chat_casual_short_circuits_without_task_usage_or_audit(
    db, config, brain_paths, php_project, message
):
    service = _service(db, config, brain_paths, php_project)
    before_tasks = db.query_one("SELECT COUNT(*) n FROM tasks")["n"]
    before_usage = db.query_one("SELECT COUNT(*) n FROM knowledge_usage")["n"]

    reply = service.handle(message)

    assert reply.task_id is None
    assert service.project.name in reply.text
    assert "Senior: Codex VS Code" in reply.text
    assert db.query_one("SELECT COUNT(*) n FROM tasks")["n"] == before_tasks
    assert db.query_one("SELECT COUNT(*) n FROM knowledge_usage")["n"] == before_usage
    assert not brain_paths.task_data_dir.exists()


def test_chat_mixed_greeting_with_analysis_is_technical(
    db, config, brain_paths, php_project
):
    service = _service(db, config, brain_paths, php_project)
    service.handle("/verbose on")

    reply = service.handle("olá, analise os itens do pedido")

    assert reply.task_id is not None
    assert "Memory lookup:" in reply.text
    assert "Code lookup:" in reply.text
    assert "Route:" in reply.text
    assert (brain_paths.task_data_dir / "sample").exists()


def test_chat_message_classifier_exact_categories():
    classifier = ChatMessageClassifier()
    assert classifier.classify("/status") == ChatMessageCategory.COMMAND
    assert classifier.classify("status do projeto") == ChatMessageCategory.STATUS_QUERY
    assert classifier.classify("consulte a memoria") == ChatMessageCategory.MEMORY_QUERY
    assert classifier.classify("qual arquivo contém a classe") == ChatMessageCategory.CODE_QUESTION
    assert classifier.classify("analise o pedido") == ChatMessageCategory.ANALYSIS_TASK
    assert classifier.classify("implemente a correção") == ChatMessageCategory.IMPLEMENTATION_TASK
    assert classifier.classify("protocolo lunar") == ChatMessageCategory.UNKNOWN


@pytest.mark.parametrize(
    "message",
    [
        "quem é você?",
        "qual é o seu Senior?",
        "você está online?",
        "o Brain está offline?",
        "qual sua memória?",
        "do que você é capaz?",
    ],
)
def test_chat_classifier_recognizes_self_queries(message):
    assert ChatMessageClassifier().classify(message) == ChatMessageCategory.SELF_QUERY


@pytest.mark.parametrize(
    "message",
    [
        "me explique como vc funciona",
        "como você funciona?",
        "o que é o Project Brain?",
        "como você aprende?",
        "quem é seu Senior?",
        "o que você sabe?",
        "como funciona seu modo offline?",
        "me fale sobre vc",
        "conte sobre voce",
    ],
)
def test_chat_classifier_recognizes_self_referential_how_it_works_questions(message):
    assert ChatMessageClassifier().classify(message) == ChatMessageCategory.SELF_QUERY


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        ("olá, analise o pedido", ChatMessageCategory.ANALYSIS_TASK),
        ("como você analisa o pedido?", ChatMessageCategory.ANALYSIS_TASK),
        ("implemente uma correção no financeiro", ChatMessageCategory.IMPLEMENTATION_TASK),
        ("qual o status do pedido 123?", ChatMessageCategory.CODE_QUESTION),
        ("qual o status da NF-e?", ChatMessageCategory.CODE_QUESTION),
        ("como está o estoque?", ChatMessageCategory.CODE_QUESTION),
        ("qual o financeiro do pedido?", ChatMessageCategory.CODE_QUESTION),
        ("como funciona o fluxo de pedidos?", ChatMessageCategory.CODE_QUESTION),
        ("como funciona a NF-e?", ChatMessageCategory.CODE_QUESTION),
        ("fale sobre o pedido do cliente", ChatMessageCategory.CODE_QUESTION),
        ("fale sobre seu pedido", ChatMessageCategory.CODE_QUESTION),
    ],
)
def test_chat_classifier_keeps_mixed_and_domain_questions_technical(message, expected):
    assert ChatMessageClassifier().classify(message) == expected


@pytest.mark.parametrize(
    "message",
    [
        "quem é você?",
        "qual é seu Senior?",
        "você está online?",
        "me explique como vc funciona",
        "o que é o Project Brain?",
    ],
)
def test_self_query_is_local_dynamic_and_has_no_technical_side_effects(
    db, config, brain_paths, php_project, message
):
    service = _service(db, config, brain_paths, php_project)
    before = {
        table: db.query_one(f"SELECT COUNT(*) n FROM {table}")["n"]
        for table in ("tasks", "knowledge_usage", "senior_sessions")
    }

    reply = service.handle(message)

    assert reply.task_id is None
    assert "Project Brain" in reply.text
    assert service.project.name in reply.text
    assert "ONLINE" in reply.text
    assert "3 regras, 2 padrões, 2 lições" in reply.text
    # Internal implementation details stay out of the default (verbose off) reply.
    assert config.senior.provider not in reply.text
    assert "handoff invertido/manual" not in reply.text
    assert service.last_summary is None
    assert not brain_paths.task_data_dir.exists()
    for table, count in before.items():
        assert db.query_one(f"SELECT COUNT(*) n FROM {table}")["n"] == count
    history = service.sessions.recent(service.session.id)
    assert [item.role for item in history[-2:]] == ["user", "assistant"]
    assert all(item.task_id is None for item in history[-2:])

    service.handle("/verbose on")
    verbose_reply = service.handle(message)
    assert verbose_reply.task_id is None
    assert config.senior.provider in verbose_reply.text
    assert "handoff invertido/manual" in verbose_reply.text


def test_self_query_reflects_offline_online_and_preserves_last_task(
    db, config, brain_paths, php_project
):
    service = _service(db, config, brain_paths, php_project)
    service.handle("/verbose on")
    technical = service.handle("analise os itens do pedido")
    task_count = db.query_one("SELECT COUNT(*) n FROM tasks")["n"]
    assert technical.task_id is not None

    service.handle("/offline")
    offline = service.handle("você está online?")
    assert "OFFLINE" in offline.text
    assert f"Última task desta sessão: {technical.task_id}" in offline.text
    assert db.query_one("SELECT COUNT(*) n FROM tasks")["n"] == task_count

    service.handle("/online")
    online = service.handle("qual é seu Senior?")
    assert "ONLINE" in online.text
    assert "disponibilidade é verificada por tarefa" in online.text
    assert db.query_one("SELECT COUNT(*) n FROM tasks")["n"] == task_count


def test_self_query_knowledge_counts_are_approved_and_project_scoped(
    db, config, brain_paths, php_project, tmp_path
):
    service = _service(db, config, brain_paths, php_project)
    other = ProjectRepository(db).get_or_create(str(tmp_path / "other"), name="other")
    RuleRepository(db).add("OTHER", "x", "other", project_id=other.id)
    RuleRepository(db).add(
        "UNAPPROVED", "x", "hidden", approved=False, project_id=service.project.id
    )
    RuleRepository(db).add("GLOBAL", "x", "global")

    reply = service.handle("qual sua memória?")

    assert "4 regras, 2 padrões, 2 lições" in reply.text
    assert "OTHER" not in reply.text
    classifier = ChatMessageClassifier()
    assert classifier.classify("qual o status do projeto") == ChatMessageCategory.STATUS_QUERY
    assert classifier.classify("qual o status da NF-e do pedido") == ChatMessageCategory.CODE_QUESTION


def test_natural_status_and_memory_queries_do_not_create_tasks(
    db, config, brain_paths, php_project
):
    service = _service(db, config, brain_paths, php_project)

    status = service.handle("qual o status do projeto?")
    memory = service.handle("consulte a memoria sobre pedido")

    assert status.task_id is None
    assert memory.task_id is None
    assert db.query_one("SELECT COUNT(*) n FROM tasks")["n"] == 0
    assert "Project:" in status.text
    assert "RULE-PEDIDO" in memory.text


def test_casual_offline_reports_senior_unavailable_without_side_effects(
    db, config, brain_paths, php_project
):
    service = _service(db, config, brain_paths, php_project)
    service.handle("/offline")
    before_messages = len(service.sessions.recent(service.session.id))
    prior_summary = service.last_summary

    reply = service.handle("oi")

    assert reply.task_id is None
    assert "Senior: UNAVAILABLE (modo local)" in reply.text
    assert db.query_one("SELECT COUNT(*) n FROM tasks")["n"] == 0
    assert db.query_one("SELECT COUNT(*) n FROM knowledge_usage")["n"] == 0
    assert not brain_paths.task_data_dir.exists()
    assert service.last_summary is prior_summary
    assert len(service.sessions.recent(service.session.id)) == before_messages + 2


def test_technical_status_question_is_not_project_status_query(
    db, config, brain_paths, php_project
):
    service = _service(db, config, brain_paths, php_project)
    service.handle("/verbose on")

    reply = service.handle("qual o status da NF-e do pedido 123?")

    assert reply.task_id is not None
    assert "Memory lookup:" in reply.text
    assert "Code lookup:" in reply.text
    assert "Route:" in reply.text
