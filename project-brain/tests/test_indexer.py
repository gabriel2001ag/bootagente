from analysis.project_indexer import ProjectIndexer
from analysis.code_scanner import IgnoreMatcher, scan_project
from brain.projects import ProjectRepository
from core.config import IndexingConfig


def test_index_project_creates_files_symbols_relationships(db, php_project):
    projects = ProjectRepository(db)
    project = projects.get_or_create(str(php_project), name="sample")

    stats = ProjectIndexer(db).index(project.id, php_project)

    assert stats.files_scanned >= 3
    assert stats.files_indexed >= 3
    assert stats.primary_language == "php"

    files = db.query("SELECT * FROM files WHERE project_id = ?", (project.id,))
    paths = {f["path"] for f in files}
    assert "app/Controllers/Pedido.php" in paths
    assert "app/Models/PedidoModel.php" in paths

    symbols = db.query(
        "SELECT s.* FROM symbols s JOIN files f ON f.id = s.file_id WHERE f.project_id = ?",
        (project.id,),
    )
    symbol_names = {s["name"] for s in symbols}
    assert "PedidoController" in symbol_names
    assert "imprimirLote" in symbol_names

    relationships = db.query("SELECT * FROM relationships WHERE project_id = ?", (project.id,))
    rel_pairs = {(r["from_name"], r["relation"], r["to_name"]) for r in relationships}
    assert ("PedidoModel", "REFERENCES_TABLE", "tab_pedido") in rel_pairs


def test_reindex_unchanged_files_is_skipped(db, php_project):
    projects = ProjectRepository(db)
    project = projects.get_or_create(str(php_project), name="sample")
    indexer = ProjectIndexer(db)

    first = indexer.index(project.id, php_project)
    second = indexer.index(project.id, php_project)

    assert first.files_indexed >= 3
    assert second.files_indexed == 0
    assert second.files_unchanged == first.files_indexed


def test_reindex_detects_changed_file(db, php_project):
    projects = ProjectRepository(db)
    project = projects.get_or_create(str(php_project), name="sample")
    indexer = ProjectIndexer(db)
    indexer.index(project.id, php_project)

    controller = php_project / "app" / "Controllers" / "Pedido.php"
    controller.write_text(controller.read_text(encoding="utf-8") + "\n// changed\n", encoding="utf-8")

    second = indexer.index(project.id, php_project)
    assert second.files_indexed == 1


def test_index_filters_and_audits_sensitive_paths(db, php_project):
    (php_project / "AGENTS.local.md").write_text("secret operational instructions", encoding="utf-8")
    (php_project / "writable").mkdir()
    (php_project / "writable" / "session.txt").write_text("session secret", encoding="utf-8")
    project = ProjectRepository(db).get_or_create(str(php_project), name="sample")

    stats = ProjectIndexer(db, IndexingConfig()).index(project.id, php_project)

    assert stats.files_skipped == 2
    indexed = {row["path"] for row in db.query("SELECT path FROM files WHERE project_id=?", (project.id,))}
    assert "AGENTS.local.md" not in indexed
    assert "writable/session.txt" not in indexed
    skips = db.query("SELECT path, reason FROM index_skips WHERE project_id=?", (project.id,))
    assert {row["path"] for row in skips} == {"AGENTS.local.md", "writable/session.txt"}
    assert all("secret" not in row["reason"] for row in skips)


def test_clear_preserves_tasks_and_knowledge(db, php_project):
    from brain.rules import RuleRepository
    from core.task import TaskRepository

    project = ProjectRepository(db).get_or_create(str(php_project), name="sample")
    indexer = ProjectIndexer(db)
    indexer.index(project.id, php_project)
    task = TaskRepository(db).create(project.id, "keep me")
    RuleRepository(db).add("KEEP", "general", "keep me", project_id=project.id)

    indexer.clear(project.id)

    assert db.query("SELECT * FROM files WHERE project_id=?", (project.id,)) == []
    assert db.query("SELECT * FROM relationships WHERE project_id=?", (project.id,)) == []
    assert TaskRepository(db).get(task.id).title == "keep me"
    assert RuleRepository(db).get("KEEP").rule_text == "keep me"


def test_rebuild_rolls_back_complete_index_on_failure(db, php_project, monkeypatch):
    project = ProjectRepository(db).get_or_create(str(php_project), name="sample")
    indexer = ProjectIndexer(db)
    indexer.index(project.id, php_project)
    before = {
        row["path"] for row in db.query("SELECT path FROM files WHERE project_id=?", (project.id,))
    }
    monkeypatch.setattr(
        "analysis.project_indexer.map_relationships",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("mapping failed")),
    )

    import pytest
    with pytest.raises(RuntimeError, match="mapping failed"):
        indexer.rebuild(project.id, php_project)

    after = {
        row["path"] for row in db.query("SELECT path FROM files WHERE project_id=?", (project.id,))
    }
    assert after == before


def test_default_matcher_covers_sensitive_and_generated_paths():
    matcher = IgnoreMatcher.from_config(
        IndexingConfig().ignored_dirs,
        IndexingConfig().ignored_globs,
        IndexingConfig().sensitive_globs,
    )
    ignored = [
        "writable/a.txt", "writable_cache/a.txt", "storage/a.txt",
        "logs/a.txt", "log/a.txt", "cache/a.txt", "sessions/a.txt",
        "session/a.txt", "tmp/a.txt", "temp/a.txt", "coverage/a.txt",
        "build/a.js", "dist/a.js", "public/uploads/a.php",
        "public/cache/a.dat", "public/tmp/a.dat", ".env", ".env.local",
        "app/error.log", "data/a.sqlite", "data/a.sqlite3", "data/a.db",
        "data/a.session", "data/a.cache",
        r"C:\erp\writable_session\a.txt", "C:/erp/storage/a.txt",
        r"C:\erp\public\uploads\a.php", "C:/erp/public/cache/a.dat",
        r"C:\erp\.env.production", "C:/erp/logs/error.log",
    ]
    for path in ignored:
        assert matcher.reason(path), path


def test_public_php_sql_and_migrations_remain_indexable(php_project):
    (php_project / "public").mkdir()
    (php_project / "public" / "index.php").write_text("<?php echo 'ok';", encoding="utf-8")
    (php_project / "schema.sql").write_text("SELECT 1;", encoding="utf-8")

    paths = {item.path for item in scan_project(
        php_project,
        matcher=IgnoreMatcher.from_config(
            IndexingConfig().ignored_dirs,
            IndexingConfig().ignored_globs,
            IndexingConfig().sensitive_globs,
        ),
    )}

    assert "public/index.php" in paths
    assert "schema.sql" in paths
    assert "app/Database/Migrations/001_CreateTabPedido.php" in paths


def test_sensitive_skip_reason_contains_only_classification_and_pattern(db, php_project):
    (php_project / ".env.production").write_text("PASSWORD=do-not-audit", encoding="utf-8")
    project = ProjectRepository(db).get_or_create(str(php_project), name="sample")

    ProjectIndexer(db, IndexingConfig()).index(project.id, php_project)

    row = db.query_one(
        "SELECT reason FROM index_skips WHERE project_id=? AND path='.env.production'",
        (project.id,),
    )
    assert row["reason"] == "SKIPPED_SENSITIVE:.env.*"
    assert "PASSWORD" not in row["reason"]
