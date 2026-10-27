"""Thread-safe SQLite connection wrapper.

One connection is shared by the UI thread and the activity-monitor thread; every
access goes through a re-entrant lock and writes run inside explicit transactions.
"""
from __future__ import annotations

import logging
import shutil
import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator, Sequence

log = logging.getLogger(__name__)


class DatabaseError(RuntimeError):
    pass


class Database:
    def __init__(self, path: Path | str):
        self.path = Path(path) if str(path) != ":memory:" else path
        self._lock = threading.RLock()
        self._depth = 0
        try:
            self._conn = sqlite3.connect(
                str(path), check_same_thread=False, isolation_level=None, timeout=10
            )
        except sqlite3.Error as exc:  # pragma: no cover - depends on filesystem
            raise DatabaseError(f"Could not open database at {path}: {exc}") from exc
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys = ON")
        self._conn.execute("PRAGMA busy_timeout = 5000")
        if str(path) != ":memory:":
            self._conn.execute("PRAGMA journal_mode = WAL")
            self._conn.execute("PRAGMA synchronous = NORMAL")

    # -- basic access -------------------------------------------------
    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        with self._lock:
            outer = self._depth == 0
            if outer:
                self._conn.execute("BEGIN IMMEDIATE")
            self._depth += 1
            try:
                yield self._conn
            except BaseException:
                self._depth -= 1
                if outer:
                    self._conn.execute("ROLLBACK")
                raise
            else:
                self._depth -= 1
                if outer:
                    self._conn.execute("COMMIT")

    def execute(self, sql: str, params: Sequence[Any] | dict = ()) -> sqlite3.Cursor:
        with self._lock:
            return self._conn.execute(sql, params)

    def query(self, sql: str, params: Sequence[Any] | dict = ()) -> list[sqlite3.Row]:
        with self._lock:
            return self._conn.execute(sql, params).fetchall()

    def query_one(self, sql: str, params: Sequence[Any] | dict = ()) -> sqlite3.Row | None:
        with self._lock:
            return self._conn.execute(sql, params).fetchone()

    def scalar(self, sql: str, params: Sequence[Any] | dict = (), default: Any = None) -> Any:
        row = self.query_one(sql, params)
        if row is None or row[0] is None:
            return default
        return row[0]

    @property
    def user_version(self) -> int:
        return int(self.scalar("PRAGMA user_version", default=0))

    # -- maintenance ---------------------------------------------------
    def backup_to(self, destination: Path | str) -> Path:
        destination = Path(destination)
        destination.parent.mkdir(parents=True, exist_ok=True)
        with self._lock:
            target = sqlite3.connect(str(destination))
            try:
                self._conn.backup(target)
            finally:
                target.close()
        log.info("Database backed up to %s", destination)
        return destination

    @staticmethod
    def validate_backup(source: Path | str) -> int:
        """Return the schema version of a backup file, raising if it isn't ours."""
        try:
            conn = sqlite3.connect(f"file:{Path(source).as_posix()}?mode=ro", uri=True)
            try:
                if conn.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                    raise DatabaseError("The backup file failed an integrity check.")
                tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
                version = conn.execute("PRAGMA user_version").fetchone()[0]
            finally:
                conn.close()
        except sqlite3.Error as exc:
            raise DatabaseError(f"Not a valid Pixel Desk backup: {exc}") from exc
        required = {"settings", "tasks", "launcher_items", "app_usage"}
        if not required.issubset(tables) or version < 1:
            raise DatabaseError("This file is not a Pixel Desk backup.")
        return version

    @staticmethod
    def restore_file(source: Path | str, destination: Path | str) -> Path:
        """Copy a validated backup over the database file. The live connection
        must be closed first. A safety copy of the current database is kept."""
        destination = Path(destination)
        Database.validate_backup(source)
        safety = destination.with_suffix(".before-restore.db")
        if destination.exists():
            shutil.copy2(destination, safety)
        for suffix in ("-wal", "-shm"):
            side = Path(str(destination) + suffix)
            if side.exists():
                side.unlink()
        shutil.copy2(source, destination)
        return safety

    def close(self) -> None:
        with self._lock:
            try:
                if str(self.path) != ":memory:":
                    self._conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            except sqlite3.Error:  # pragma: no cover
                pass
            self._conn.close()
