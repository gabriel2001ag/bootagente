CREATE TABLE IF NOT EXISTS test_result_revisions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    original_test_result_id INTEGER NOT NULL,
    task_id INTEGER NOT NULL REFERENCES tasks(id),
    revision INTEGER NOT NULL,
    tool TEXT NOT NULL,
    command TEXT,
    exit_code INTEGER,
    passed INTEGER NOT NULL,
    output TEXT,
    created_at TEXT NOT NULL,
    archived_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_test_result_revisions_task
    ON test_result_revisions(task_id, revision);
