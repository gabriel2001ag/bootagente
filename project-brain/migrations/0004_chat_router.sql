BEGIN IMMEDIATE;

CREATE TABLE IF NOT EXISTS chat_sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL REFERENCES projects(id),
    status TEXT NOT NULL DEFAULT 'ACTIVE',
    senior_mode TEXT NOT NULL DEFAULT 'ONLINE',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS chat_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id INTEGER NOT NULL REFERENCES chat_sessions(id),
    role TEXT NOT NULL,
    message TEXT NOT NULL,
    task_id INTEGER REFERENCES tasks(id),
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_chat_messages_session
    ON chat_messages(session_id, id);

CREATE TABLE IF NOT EXISTS knowledge_usage (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL REFERENCES projects(id),
    task_id INTEGER REFERENCES tasks(id),
    knowledge_type TEXT NOT NULL,
    knowledge_code TEXT NOT NULL,
    result TEXT NOT NULL DEFAULT 'SELECTED',
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_knowledge_usage_task
    ON knowledge_usage(task_id, knowledge_type);

CREATE TABLE IF NOT EXISTS concepts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER REFERENCES projects(id),
    name TEXT NOT NULL,
    aliases_json TEXT NOT NULL DEFAULT '[]',
    approved INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    UNIQUE(project_id, name)
);

CREATE TABLE IF NOT EXISTS concept_relationships (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER REFERENCES projects(id),
    from_concept TEXT NOT NULL,
    relation TEXT NOT NULL,
    to_concept TEXT NOT NULL,
    weight REAL NOT NULL DEFAULT 0.5,
    approved INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    UNIQUE(project_id, from_concept, relation, to_concept)
);

ALTER TABLE rules ADD COLUMN last_validated_at TEXT;
ALTER TABLE rules ADD COLUMN times_used INTEGER NOT NULL DEFAULT 0;
ALTER TABLE rules ADD COLUMN times_successful INTEGER NOT NULL DEFAULT 0;
ALTER TABLE rules ADD COLUMN times_rejected INTEGER NOT NULL DEFAULT 0;
ALTER TABLE rules ADD COLUMN deprecated INTEGER NOT NULL DEFAULT 0;
ALTER TABLE rules ADD COLUMN superseded_by TEXT;

ALTER TABLE patterns ADD COLUMN last_validated_at TEXT;
ALTER TABLE patterns ADD COLUMN times_used INTEGER NOT NULL DEFAULT 0;
ALTER TABLE patterns ADD COLUMN times_successful INTEGER NOT NULL DEFAULT 0;
ALTER TABLE patterns ADD COLUMN times_rejected INTEGER NOT NULL DEFAULT 0;
ALTER TABLE patterns ADD COLUMN deprecated INTEGER NOT NULL DEFAULT 0;
ALTER TABLE patterns ADD COLUMN superseded_by TEXT;

ALTER TABLE lessons ADD COLUMN last_validated_at TEXT;
ALTER TABLE lessons ADD COLUMN times_used INTEGER NOT NULL DEFAULT 0;
ALTER TABLE lessons ADD COLUMN times_successful INTEGER NOT NULL DEFAULT 0;
ALTER TABLE lessons ADD COLUMN times_rejected INTEGER NOT NULL DEFAULT 0;
ALTER TABLE lessons ADD COLUMN deprecated INTEGER NOT NULL DEFAULT 0;
ALTER TABLE lessons ADD COLUMN superseded_by TEXT;

COMMIT;
