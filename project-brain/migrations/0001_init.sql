-- Project Brain V1 initial schema (seção 6).
-- All *_json columns store JSON-encoded text (SQLite has no native JSON
-- type without extensions; kept dependency-free per seção 33/35).

CREATE TABLE IF NOT EXISTS projects (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    path TEXT NOT NULL UNIQUE,
    vcs TEXT NOT NULL DEFAULT 'git',
    primary_language TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    last_indexed_at TEXT
);

CREATE TABLE IF NOT EXISTS tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL REFERENCES projects(id),
    external_id TEXT,
    title TEXT NOT NULL,
    description TEXT,
    category TEXT NOT NULL DEFAULT 'unknown',
    status TEXT NOT NULL DEFAULT 'NEW',
    confidence REAL,
    decision TEXT,
    source TEXT NOT NULL DEFAULT 'cli',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    completed_at TEXT,
    git_commit_before TEXT,
    git_commit_after TEXT
);

CREATE TABLE IF NOT EXISTS rules (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    rule_code TEXT NOT NULL UNIQUE,
    project_id INTEGER REFERENCES projects(id),
    category TEXT NOT NULL,
    condition_text TEXT,
    rule_text TEXT NOT NULL,
    dont_json TEXT,
    confidence REAL NOT NULL DEFAULT 1.0,
    source TEXT NOT NULL DEFAULT 'manual',
    approved INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS patterns (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    pattern_code TEXT NOT NULL UNIQUE,
    project_id INTEGER REFERENCES projects(id),
    category TEXT NOT NULL,
    framework TEXT,
    trigger TEXT,
    procedure_json TEXT,
    approved INTEGER NOT NULL DEFAULT 0,
    confidence REAL NOT NULL DEFAULT 1.0,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS lessons (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    lesson_code TEXT NOT NULL UNIQUE,
    project_id INTEGER REFERENCES projects(id),
    task_id INTEGER REFERENCES tasks(id),
    problem TEXT,
    solution TEXT,
    files_json TEXT,
    category TEXT NOT NULL DEFAULT 'general',
    approved INTEGER NOT NULL DEFAULT 0,
    validated_by TEXT,
    confidence REAL NOT NULL DEFAULT 1.0,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS files (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL REFERENCES projects(id),
    path TEXT NOT NULL,
    language TEXT,
    size INTEGER NOT NULL DEFAULT 0,
    hash TEXT,
    last_modified TEXT,
    indexed_at TEXT NOT NULL,
    UNIQUE(project_id, path)
);

CREATE TABLE IF NOT EXISTS symbols (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    file_id INTEGER NOT NULL REFERENCES files(id),
    symbol_type TEXT NOT NULL,
    name TEXT NOT NULL,
    class_name TEXT,
    line_start INTEGER,
    line_end INTEGER
);

CREATE TABLE IF NOT EXISTS relationships (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL REFERENCES projects(id),
    from_type TEXT NOT NULL,
    from_name TEXT NOT NULL,
    relation TEXT NOT NULL,
    to_type TEXT NOT NULL,
    to_name TEXT NOT NULL,
    meta_json TEXT
);

CREATE TABLE IF NOT EXISTS patches (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id INTEGER NOT NULL REFERENCES tasks(id),
    commit_before TEXT,
    commit_after TEXT,
    diff TEXT,
    metadata_json TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS reviews (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id INTEGER NOT NULL REFERENCES tasks(id),
    patch_id INTEGER REFERENCES patches(id),
    reviewer TEXT NOT NULL,
    decision TEXT NOT NULL,
    comments TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS test_results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id INTEGER NOT NULL REFERENCES tasks(id),
    tool TEXT NOT NULL,
    command TEXT,
    exit_code INTEGER,
    passed INTEGER NOT NULL DEFAULT 0,
    output TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS senior_sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id INTEGER REFERENCES tasks(id),
    provider TEXT NOT NULL,
    status TEXT NOT NULL,
    request_json TEXT,
    response_json TEXT,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_tasks_project ON tasks(project_id);
CREATE INDEX IF NOT EXISTS idx_files_project ON files(project_id);
CREATE INDEX IF NOT EXISTS idx_symbols_file ON symbols(file_id);
CREATE INDEX IF NOT EXISTS idx_relationships_project ON relationships(project_id);
CREATE INDEX IF NOT EXISTS idx_rules_category ON rules(category);
CREATE INDEX IF NOT EXISTS idx_patterns_category ON patterns(category);
CREATE INDEX IF NOT EXISTS idx_lessons_category ON lessons(category);
