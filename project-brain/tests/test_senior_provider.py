import pytest

from core.enums import Decision, SeniorStatus
from core.task import Task
from senior.codex_provider import CodexProvider
from senior.mock_provider import MockSeniorProvider
from senior.senior_service import SeniorService, build_provider


def _task():
    return Task(id=1, project_id=1, title="limitar intervalo de pedidos", description="", category="validation")


def test_mock_provider_available_by_default():
    provider = MockSeniorProvider()
    assert provider.check_availability() == SeniorStatus.AVAILABLE


def test_mock_provider_can_simulate_unavailable():
    provider = MockSeniorProvider(availability=SeniorStatus.UNAVAILABLE)
    assert provider.check_availability() == SeniorStatus.UNAVAILABLE


@pytest.mark.parametrize(
    "status",
    [
        SeniorStatus.RATE_LIMITED,
        SeniorStatus.AUTH_ERROR,
        SeniorStatus.QUOTA_EXCEEDED,
        SeniorStatus.TIMEOUT,
        SeniorStatus.UNKNOWN_ERROR,
    ],
)
def test_mock_provider_supports_all_status_values(status):
    provider = MockSeniorProvider(availability=status)
    assert provider.check_availability() == status


def test_mock_provider_analyze_returns_learning_payload():
    provider = MockSeniorProvider()
    task = _task()
    result = provider.analyze(task, context=None)
    assert result.decision in Decision
    assert result.learning is not None
    assert len(result.learning.lessons) == 1


def test_codex_provider_is_unavailable_without_api_key():
    provider = CodexProvider()
    assert provider.check_availability() in (SeniorStatus.AUTH_ERROR, SeniorStatus.UNAVAILABLE)


def test_codex_provider_analyze_not_implemented():
    provider = CodexProvider(api_key="fake")
    with pytest.raises(NotImplementedError):
        provider.analyze(_task(), context=None)


def test_build_provider_from_config(config):
    config.senior.provider = "mock"
    provider = build_provider(config)
    assert isinstance(provider, MockSeniorProvider)

    config.senior.provider = "codex"
    provider2 = build_provider(config)
    assert isinstance(provider2, CodexProvider)

    config.senior.provider = "unknown"
    with pytest.raises(ValueError):
        build_provider(config)


def test_senior_service_records_session(db, config):
    from brain.projects import ProjectRepository
    from core.task import TaskRepository

    config.senior.provider = "mock"
    config.senior.mock_availability = "AVAILABLE"
    service = SeniorService(db, config)
    assert service.check_availability() == SeniorStatus.AVAILABLE

    project = ProjectRepository(db).get_or_create("/tmp/p", name="p")
    task = TaskRepository(db).create(project.id, title="limitar intervalo de pedidos")
    result = service.analyze(task, context=None)
    assert result.decision in Decision

    sessions = db.query("SELECT * FROM senior_sessions")
    assert len(sessions) == 1
    assert sessions[0]["provider"] == "mock"


def test_senior_service_disabled_in_config_reports_unavailable(db, config):
    config.senior.enabled = False
    service = SeniorService(db, config)
    assert service.check_availability() == SeniorStatus.UNAVAILABLE
