CREATE TABLE IF NOT EXISTS index_skips (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL REFERENCES projects(id),
    path TEXT NOT NULL,
    reason TEXT NOT NULL,
    observed_at TEXT NOT NULL,
    UNIQUE(project_id, path)
);

CREATE INDEX IF NOT EXISTS idx_index_skips_project
    ON index_skips(project_id);
