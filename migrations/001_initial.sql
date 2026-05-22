-- Migration: 001_initial
-- Sprint1 SQLite schema — idempotent, repeatable execution
-- Created by: developer (kanban t_dc037eee)

PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

-- ── roles ─────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS roles (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    name         TEXT    NOT NULL,
    description  TEXT,
    created_at   TIMESTAMP DEFAULT (datetime('now')),
    updated_at   TIMESTAMP DEFAULT (datetime('now'))
);

-- ── tasks ─────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS tasks (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    title           TEXT    NOT NULL,
    description     TEXT,
    status          TEXT    DEFAULT 'PENDING'   CHECK(status IN ('PENDING','IN_PROGRESS','DONE','CANCELLED')),
    priority        TEXT    DEFAULT 'MEDIUM'   CHECK(priority IN ('LOW','MEDIUM','HIGH','URGENT')),
    estimated_hours REAL,
    created_at      TIMESTAMP DEFAULT (datetime('now')),
    updated_at      TIMESTAMP DEFAULT (datetime('now'))
);

-- ── role_tasks (many-to-many junction) ────────────────────────────────────────
CREATE TABLE IF NOT EXISTS role_tasks (
    role_id     INTEGER NOT NULL,
    task_id     INTEGER NOT NULL,
    assigned_at TIMESTAMP DEFAULT (datetime('now')),
    PRIMARY KEY (role_id, task_id),
    FOREIGN KEY (role_id) REFERENCES roles(id) ON DELETE CASCADE,
    FOREIGN KEY (task_id) REFERENCES tasks(id) ON DELETE CASCADE
);

-- ── indexes (idempotent — only created if not exist) ─────────────────────────
CREATE INDEX IF NOT EXISTS idx_tasks_status      ON tasks(status);
CREATE INDEX IF NOT EXISTS idx_tasks_priority     ON tasks(priority);
CREATE INDEX IF NOT EXISTS idx_role_tasks_role   ON role_tasks(role_id);
CREATE INDEX IF NOT EXISTS idx_role_tasks_task   ON role_tasks(task_id);
