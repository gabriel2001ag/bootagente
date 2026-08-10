import json

import pytest

from analysis.project_indexer import ProjectIndexer
from brain.projects import ProjectRepository
from core.enums import TaskStatus
from core.orchestrator import Orchestrator
from core.paths import slugify
from core.task import TaskRepository
from senior.codex_workspace_bridge import BridgeValidationError, CodexWorkspaceBridge


def _pending_task(db, brain_paths, php_project):
    project = ProjectRepository(db).get_or_create(str(php_project), name="sample")
    task = TaskRepository(db).create(project.id, "Corrigir validação")
    task = TaskRepository(db).update_status(task.id, TaskStatus.SENIOR_REQUIRED)
    audit_dir = brain_paths.task_dir(slugify(project.name), task.id)
    audit_dir.mkdir(parents=True)
    (audit_dir / "request.json").write_text(
        json.dumps({"title": task.title, "description": ""}), encoding="utf-8"
    )
    (audit_dir / "context.json").write_text(
        json.dumps({"candidate_files": ["app/Controllers/Pedido.php"]}), encoding="utf-8"
    )
    return project, task


def test_bridge_lists_and_returns_prepared_context(db, brain_paths, php_project):
    project, task = _pending_task(db, brain_paths, php_project)
    bridge = CodexWorkspaceBridge(db, brain_paths)

    assert [item.id for item in bridge.pending(project.id)] == [task.id]
    handoff = bridge.context(task.id)
    assert handoff["integration"] == "codex-vscode-inverted"
    assert handoff["context"]["candidate_files"] == ["app/Controllers/Pedido.php"]


def test_orchestrator_prepares_workspace_handoff_end_to_end(
    db, brain_paths, php_project, config
):
    project = ProjectRepository(db).get_or_create(str(php_project), name="sample")
    config.senior.provider = "codex-vscode"

    summary = Orchestrator(db, config, brain_paths, project).run_task(
        "Corrigir validação do pedido"
    )

    assert summary.mode.value == "WORKSPACE_HANDOFF"
    assert summary.task.status == TaskStatus.SENIOR_REQUIRED.value
    bridge = CodexWorkspaceBridge(db, brain_paths, config)
    handoff = bridge.context(summary.task.id)
    assert handoff["task"]["title"] == "Corrigir validação do pedido"


def test_orchestrator_refreshes_same_task_and_preserves_artifact_revision(
    db, brain_paths, php_project, config
):
    project = ProjectRepository(db).get_or_create(str(php_project), name="sample")
    config.senior.provider = "codex-vscode"
    orchestrator = Orchestrator(db, config, brain_paths, project)
    first = orchestrator.run_task("Analisar pedido")
    audit_dir = brain_paths.task_dir("sample", first.task.id)
    original_request = (audit_dir / "request.json").read_text(encoding="utf-8")
    db.execute(
        "INSERT INTO test_results(task_id, tool, command, exit_code, passed, output, created_at) "
        "VALUES (?,?,?,?,?,?,?)",
        (first.task.id, "php -l", "php -l old.php", 0, 1, "old result", "2026-01-01"),
    )

    refreshed = orchestrator.refresh_task(
        first.task.id, title="Analyze order flow", description="Analysis only"
    )

    assert refreshed.task.id == first.task.id
    assert refreshed.task.title == "Analyze order flow"
    assert refreshed.task.status == TaskStatus.SENIOR_REQUIRED.value
    assert (audit_dir / "revisions" / "0001" / "request.json").read_text(
        encoding="utf-8"
    ) == original_request
    assert (audit_dir / "senior-request.json").exists()
    archived = db.query_one(
        "SELECT output FROM test_result_revisions "
        "WHERE task_id=? AND revision=1 AND output='old result'",
        (first.task.id,),
    )
    assert archived["output"] == "old result"
    assert db.query(
        "SELECT * FROM test_results WHERE task_id=? AND output='old result'", (first.task.id,)
    ) == []


def test_bridge_rejects_invalid_response_without_changing_task(db, brain_paths, php_project):
    _, task = _pending_task(db, brain_paths, php_project)
    bridge = CodexWorkspaceBridge(db, brain_paths)

    with pytest.raises(BridgeValidationError, match="confidence"):
        bridge.submit(task.id, {"status": "SUCCESS", "summary": "ok", "confidence": 2})

    assert TaskRepository(db).get(task.id).status == TaskStatus.SENIOR_REQUIRED.value
    assert db.query("SELECT * FROM senior_sessions") == []


def test_bridge_rejects_string_boolean_and_invalid_learning_item(db, brain_paths, php_project):
    _, task = _pending_task(db, brain_paths, php_project)
    bridge = CodexWorkspaceBridge(db, brain_paths)
    base = {"status": "SUCCESS", "summary": "ok", "confidence": 0.8}

    with pytest.raises(BridgeValidationError, match="boolean"):
        bridge.submit(task.id, {**base, "approved_for_learning": "false"})
    with pytest.raises(BridgeValidationError, match="must be an object"):
        bridge.submit(task.id, {**base, "lessons": ["invalid"]})

    assert TaskRepository(db).get(task.id).status == TaskStatus.SENIOR_REQUIRED.value


def test_bridge_records_approved_learning_and_rejects_replay(db, brain_paths, php_project):
    _, task = _pending_task(db, brain_paths, php_project)
    bridge = CodexWorkspaceBridge(db, brain_paths)
    payload = {
        "status": "SUCCESS",
        "summary": "Validar também no backend.",
        "decision": "ANALYSIS_ONLY",
        "confidence": 0.94,
        "requires_human_review": True,
        "approved_for_learning": True,
        "rules_discovered": [],
        "patterns_used": [],
        "lessons": [{
            "problem": "Validação somente no frontend",
            "solution": "Validar no backend",
            "category": "validation",
            "approved": True,
        }],
    }

    result = bridge.submit(task.id, payload)

    assert result.task.status == TaskStatus.WAITING_REVIEW.value
    assert len(result.learning.lessons_created) == 1
    assert db.query_one("SELECT provider FROM senior_sessions")["provider"] == "codex-vscode"
    with pytest.raises(BridgeValidationError, match="duplicate"):
        bridge.submit(task.id, payload)


def test_bridge_respects_disabled_automatic_learning(db, brain_paths, php_project, config):
    _, task = _pending_task(db, brain_paths, php_project)
    config.learning.automatic_after_approval = False
    bridge = CodexWorkspaceBridge(db, brain_paths, config)
    result = bridge.submit(task.id, {
        "status": "SUCCESS",
        "summary": "Análise concluída",
        "confidence": 0.9,
        "approved_for_learning": True,
        "lessons": [{"problem": "p", "solution": "s"}],
    })

    assert result.learning is None
    assert db.query("SELECT * FROM lessons") == []


def test_bridge_validates_and_records_optional_evidence(db, brain_paths, php_project):
    project, task = _pending_task(db, brain_paths, php_project)
    ProjectIndexer(db).index(project.id, php_project)
    bridge = CodexWorkspaceBridge(db, brain_paths)
    payload = {
        "status": "SUCCESS",
        "summary": "Analysis only",
        "decision": "ANALYSIS_ONLY",
        "confidence": 0.8,
        "approved_for_learning": False,
        "evidence": [{
            "type": "code",
            "path": "app/Controllers/Pedido.php",
            "line": 12,
            "claim": "Controller handles the request.",
        }],
    }

    bridge.submit(task.id, payload)

    evidence_path = brain_paths.task_dir("sample", task.id) / "evidence.json"
    assert json.loads(evidence_path.read_text(encoding="utf-8"))["evidence"][0]["line"] == 12


@pytest.mark.parametrize("invalid_path", [
    "../secret.php", "/absolute.php", r"C:\erp\secret.php", "missing.php",
])
def test_bridge_rejects_escape_absolute_and_unindexed_evidence(
    db, brain_paths, php_project, invalid_path
):
    project, task = _pending_task(db, brain_paths, php_project)
    ProjectIndexer(db).index(project.id, php_project)
    bridge = CodexWorkspaceBridge(db, brain_paths)
    with pytest.raises(BridgeValidationError, match="evidence path"):
        bridge.submit(task.id, {
            "status": "SUCCESS", "summary": "x", "confidence": 0.5,
            "evidence": [{"path": invalid_path, "line": 1, "claim": "x"}],
        })


def test_bridge_rejects_evidence_line_beyond_file(db, brain_paths, php_project):
    project, task = _pending_task(db, brain_paths, php_project)
    ProjectIndexer(db).index(project.id, php_project)
    bridge = CodexWorkspaceBridge(db, brain_paths)
    with pytest.raises(BridgeValidationError, match="exceeds"):
        bridge.submit(task.id, {
            "status": "SUCCESS", "summary": "x", "confidence": 0.5,
            "evidence": [{
                "path": "app/Controllers/Pedido.php", "line": 99999, "claim": "x"
            }],
        })


def test_bridge_rejects_indexed_but_deleted_evidence_without_line(
    db, brain_paths, php_project
):
    project, task = _pending_task(db, brain_paths, php_project)
    ProjectIndexer(db).index(project.id, php_project)
    indexed_file = php_project / "app" / "Controllers" / "Pedido.php"
    indexed_file.unlink()
    bridge = CodexWorkspaceBridge(db, brain_paths)

    with pytest.raises(BridgeValidationError, match="regular file"):
        bridge.submit(task.id, {
            "status": "SUCCESS",
            "summary": "x",
            "confidence": 0.5,
            "evidence": [{
                "path": "app/Controllers/Pedido.php",
                "claim": "Previously indexed controller.",
            }],
        })

    assert TaskRepository(db).get(task.id).status == TaskStatus.SENIOR_REQUIRED.value


def test_bridge_rejects_invalid_knowledge_before_claim(db, brain_paths, php_project):
    _, task = _pending_task(db, brain_paths, php_project)
    bridge = CodexWorkspaceBridge(db, brain_paths)
    with pytest.raises(BridgeValidationError, match="lesson"):
        bridge.submit(task.id, {
            "status": "SUCCESS", "summary": "x", "confidence": 0.5,
            "approved_for_learning": True,
            "lessons": [{"problem": "missing solution"}],
        })
    assert TaskRepository(db).get(task.id).status == TaskStatus.SENIOR_REQUIRED.value
