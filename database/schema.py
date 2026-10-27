"""Schema migrations. `PRAGMA user_version` records the applied version; each
migration runs once inside a transaction so upgrades never lose data."""
from __future__ import annotations

import logging

from .connection import Database

log = logging.getLogger(__name__)

MIGRATIONS: list[str] = [
    # --- version 1 -----------------------------------------------------
    """
    CREATE TABLE settings (
        key   TEXT PRIMARY KEY,
        value TEXT NOT NULL
    );

    CREATE TABLE launcher_items (
        id         INTEGER PRIMARY KEY AUTOINCREMENT,
        label      TEXT NOT NULL CHECK (length(trim(label)) BETWEEN 1 AND 60),
        kind       TEXT NOT NULL CHECK (kind IN ('folder', 'app')),
        path       TEXT NOT NULL CHECK (length(path) > 0),
        icon       TEXT NOT NULL DEFAULT 'folder',
        position   INTEGER NOT NULL DEFAULT 0,
        created_at TEXT NOT NULL
    );

    CREATE TABLE tasks (
        id               INTEGER PRIMARY KEY AUTOINCREMENT,
        title            TEXT NOT NULL CHECK (length(trim(title)) > 0),
        priority         INTEGER NOT NULL DEFAULT 0 CHECK (priority BETWEEN 0 AND 3),
        estimate_minutes INTEGER CHECK (estimate_minutes IS NULL OR estimate_minutes >= 0),
        due_date         TEXT,
        category         TEXT,
        position         INTEGER NOT NULL DEFAULT 0,
        created_at       TEXT NOT NULL,
        completed_at     TEXT
    );
    CREATE INDEX idx_tasks_completed ON tasks(completed_at);

    CREATE TABLE task_completions (
        id           INTEGER PRIMARY KEY AUTOINCREMENT,
        task_id      INTEGER NOT NULL UNIQUE REFERENCES tasks(id) ON DELETE CASCADE,
        day          TEXT NOT NULL,
        completed_at TEXT NOT NULL
    );
    CREATE INDEX idx_task_completions_day ON task_completions(day);

    CREATE TABLE habits (
        id                   INTEGER PRIMARY KEY AUTOINCREMENT,
        name                 TEXT NOT NULL UNIQUE COLLATE NOCASE CHECK (length(trim(name)) > 0),
        counts_toward_streak INTEGER NOT NULL DEFAULT 1 CHECK (counts_toward_streak IN (0, 1)),
        active               INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0, 1)),
        position             INTEGER NOT NULL DEFAULT 0,
        created_at           TEXT NOT NULL
    );

    CREATE TABLE habit_completions (
        id           INTEGER PRIMARY KEY AUTOINCREMENT,
        habit_id     INTEGER NOT NULL REFERENCES habits(id) ON DELETE CASCADE,
        day          TEXT NOT NULL,
        completed_at TEXT NOT NULL,
        UNIQUE (habit_id, day)
    );
    CREATE INDEX idx_habit_completions_day ON habit_completions(day);

    CREATE TABLE focus_sessions (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        session_uid     TEXT NOT NULL UNIQUE,
        task_id         INTEGER REFERENCES tasks(id) ON DELETE SET NULL,
        kind            TEXT NOT NULL CHECK (kind IN ('focus', 'break')),
        planned_seconds INTEGER NOT NULL CHECK (planned_seconds > 0),
        actual_seconds  INTEGER NOT NULL CHECK (actual_seconds >= 0),
        status          TEXT NOT NULL CHECK (status IN ('completed', 'cancelled')),
        started_at      TEXT NOT NULL,
        ended_at        TEXT NOT NULL,
        day             TEXT NOT NULL
    );
    CREATE INDEX idx_focus_day ON focus_sessions(day);
    CREATE INDEX idx_focus_task ON focus_sessions(task_id);

    CREATE TABLE app_meta (
        exe          TEXT PRIMARY KEY,
        display_name TEXT NOT NULL,
        exe_path     TEXT,
        category     TEXT NOT NULL DEFAULT 'other'
                     CHECK (category IN ('productive', 'learning', 'communication', 'entertainment', 'other')),
        first_seen   TEXT NOT NULL
    );

    CREATE TABLE app_usage (
        day     TEXT NOT NULL,
        exe     TEXT NOT NULL REFERENCES app_meta(exe) ON DELETE CASCADE,
        seconds REAL NOT NULL DEFAULT 0 CHECK (seconds >= 0),
        PRIMARY KEY (day, exe)
    );

    CREATE TABLE usage_hourly (
        day            TEXT NOT NULL,
        hour           INTEGER NOT NULL CHECK (hour BETWEEN 0 AND 23),
        active_seconds REAL NOT NULL DEFAULT 0,
        idle_seconds   REAL NOT NULL DEFAULT 0,
        PRIMARY KEY (day, hour)
    );

    CREATE TABLE daily_usage (
        day            TEXT PRIMARY KEY,
        active_seconds REAL NOT NULL DEFAULT 0,
        idle_seconds   REAL NOT NULL DEFAULT 0,
        first_observed TEXT,
        last_observed  TEXT
    );

    CREATE TABLE water_entries (
        id        INTEGER PRIMARY KEY AUTOINCREMENT,
        day       TEXT NOT NULL,
        amount_ml INTEGER NOT NULL CHECK (amount_ml > 0),
        logged_at TEXT NOT NULL
    );
    CREATE INDEX idx_water_day ON water_entries(day);

    CREATE TABLE movement_breaks (
        id                  INTEGER PRIMARY KEY AUTOINCREMENT,
        day                 TEXT NOT NULL,
        started_at          TEXT NOT NULL,
        ended_at            TEXT,
        planned_seconds     INTEGER NOT NULL CHECK (planned_seconds > 0),
        status              TEXT NOT NULL CHECK (status IN ('in_progress', 'completed', 'cancelled')),
        desk_seconds_before INTEGER
    );
    CREATE INDEX idx_movement_day ON movement_breaks(day);

    CREATE TABLE xp_transactions (
        id         INTEGER PRIMARY KEY AUTOINCREMENT,
        source_key TEXT NOT NULL UNIQUE,
        amount     INTEGER NOT NULL,
        reason     TEXT NOT NULL,
        day        TEXT NOT NULL,
        created_at TEXT NOT NULL
    );

    CREATE TABLE achievements (
        key         TEXT PRIMARY KEY,
        unlocked_at TEXT NOT NULL
    );
    """,
]

SCHEMA_VERSION = len(MIGRATIONS)


def _split_statements(script: str) -> list[str]:
    return [s.strip() for s in script.split(";") if s.strip()]


def migrate(db: Database) -> int:
    current = db.user_version
    if current > SCHEMA_VERSION:
        raise RuntimeError(
            f"Database schema v{current} is newer than this Pixel Desk (v{SCHEMA_VERSION}). "
            "Please update the application."
        )
    for index in range(current, SCHEMA_VERSION):
        version = index + 1
        log.info("Applying database migration v%d", version)
        with db.transaction() as conn:
            for statement in _split_statements(MIGRATIONS[index]):
                conn.execute(statement)
            conn.execute(f"PRAGMA user_version = {version}")
    return SCHEMA_VERSION
