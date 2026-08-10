from brain.database import Database


def test_migrations_apply_and_create_tables(brain_paths):
    db = Database(brain_paths.db_path, brain_paths.migrations_dir)
    try:
        tables = {
            row["name"]
            for row in db.query("SELECT name FROM sqlite_master WHERE type='table'")
        }
        expected = {
            "projects", "tasks", "rules", "patterns", "lessons", "files",
            "symbols", "relationships", "patches", "reviews", "test_results",
            "senior_sessions", "schema_migrations",
        }
        assert expected.issubset(tables)
    finally:
        db.close()


def test_migrations_are_idempotent(brain_paths):
    db1 = Database(brain_paths.db_path, brain_paths.migrations_dir)
    db1.close()
    # re-opening should not error out or duplicate migration rows
    db2 = Database(brain_paths.db_path, brain_paths.migrations_dir)
    try:
        rows = db2.query("SELECT version FROM schema_migrations")
        versions = [r["version"] for r in rows]
        assert len(versions) == len(set(versions))
        assert "0001_init" in versions
    finally:
        db2.close()


def test_db_path_created_on_disk(brain_paths):
    db = Database(brain_paths.db_path, brain_paths.migrations_dir)
    db.close()
    assert brain_paths.db_path.exists()
