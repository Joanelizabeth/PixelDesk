"""Data-access layer. All SQL lives here; services and UI call these methods."""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any, Iterable, Optional

from app import clock
from app.config import APP_CATEGORIES

from .connection import Database


@dataclass
class LauncherItem:
    id: int
    label: str
    kind: str  # folder | app
    path: str
    icon: str
    position: int


@dataclass
class Task:
    id: int
    title: str
    priority: int
    estimate_minutes: Optional[int]
    due_date: Optional[str]
    category: Optional[str]
    position: int
    created_at: str
    completed_at: Optional[str]
    focus_seconds: int = 0

    @property
    def done(self) -> bool:
        return self.completed_at is not None


@dataclass
class Habit:
    id: int
    name: str
    counts_toward_streak: bool
    active: bool
    position: int


@dataclass
class AppUsage:
    exe: str
    display_name: str
    category: str
    seconds: float
    exe_path: Optional[str]


def _now(now: Optional[datetime]) -> datetime:
    return now or clock.now()


class Repository:
    def __init__(self, db: Database):
        self.db = db

    # ================================================================ settings
    def load_settings(self) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for row in self.db.query("SELECT key, value FROM settings"):
            try:
                out[row["key"]] = json.loads(row["value"])
            except json.JSONDecodeError:
                continue
        return out

    def save_setting(self, key: str, value: Any) -> None:
        self.db.execute(
            "INSERT INTO settings(key, value) VALUES(?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, json.dumps(value)),
        )

    # ================================================================ launcher
    def list_launcher_items(self) -> list[LauncherItem]:
        rows = self.db.query("SELECT * FROM launcher_items ORDER BY position, id")
        return [LauncherItem(r["id"], r["label"], r["kind"], r["path"], r["icon"], r["position"]) for r in rows]

    def add_launcher_item(self, label: str, kind: str, path: str, icon: str = "folder",
                          now: Optional[datetime] = None) -> int:
        with self.db.transaction() as conn:
            pos = conn.execute("SELECT COALESCE(MAX(position), -1) + 1 FROM launcher_items").fetchone()[0]
            cur = conn.execute(
                "INSERT INTO launcher_items(label, kind, path, icon, position, created_at) VALUES(?,?,?,?,?,?)",
                (label.strip(), kind, path, icon, pos, clock.iso_ts(_now(now))),
            )
            return int(cur.lastrowid)

    def update_launcher_item(self, item_id: int, *, label: str, path: str, icon: str, kind: str) -> None:
        self.db.execute(
            "UPDATE launcher_items SET label=?, path=?, icon=?, kind=? WHERE id=?",
            (label.strip(), path, icon, kind, item_id),
        )

    def delete_launcher_item(self, item_id: int) -> None:
        self.db.execute("DELETE FROM launcher_items WHERE id=?", (item_id,))

    def reorder_launcher_items(self, ordered_ids: Iterable[int]) -> None:
        with self.db.transaction() as conn:
            for pos, item_id in enumerate(ordered_ids):
                conn.execute("UPDATE launcher_items SET position=? WHERE id=?", (pos, item_id))

    # ================================================================ tasks
    def _task_from_row(self, r) -> Task:
        return Task(
            r["id"], r["title"], r["priority"], r["estimate_minutes"], r["due_date"], r["category"],
            r["position"], r["created_at"], r["completed_at"],
            int(r["focus_seconds"]) if "focus_seconds" in r.keys() and r["focus_seconds"] else 0,
        )

    _TASK_SELECT = (
        "SELECT t.*, (SELECT COALESCE(SUM(actual_seconds), 0) FROM focus_sessions f "
        " WHERE f.task_id = t.id AND f.kind = 'focus') AS focus_seconds FROM tasks t "
    )

    def add_task(self, title: str, *, priority: int = 0, estimate_minutes: Optional[int] = None,
                 due_date: Optional[str] = None, category: Optional[str] = None,
                 now: Optional[datetime] = None) -> int:
        title = title.strip()
        if not title:
            raise ValueError("Task title cannot be empty")
        with self.db.transaction() as conn:
            pos = conn.execute("SELECT COALESCE(MAX(position), -1) + 1 FROM tasks").fetchone()[0]
            cur = conn.execute(
                "INSERT INTO tasks(title, priority, estimate_minutes, due_date, category, position, created_at) "
                "VALUES(?,?,?,?,?,?,?)",
                (title, priority, estimate_minutes, due_date, (category or None), pos, clock.iso_ts(_now(now))),
            )
            return int(cur.lastrowid)

    def update_task(self, task_id: int, **fields: Any) -> None:
        allowed = {"title", "priority", "estimate_minutes", "due_date", "category"}
        sets = {k: v for k, v in fields.items() if k in allowed}
        if "title" in sets:
            sets["title"] = str(sets["title"]).strip()
            if not sets["title"]:
                raise ValueError("Task title cannot be empty")
        if not sets:
            return
        cols = ", ".join(f"{k}=?" for k in sets)
        self.db.execute(f"UPDATE tasks SET {cols} WHERE id=?", (*sets.values(), task_id))

    def delete_task(self, task_id: int) -> None:
        self.db.execute("DELETE FROM tasks WHERE id=?", (task_id,))

    def get_task(self, task_id: int) -> Optional[Task]:
        row = self.db.query_one(self._TASK_SELECT + "WHERE t.id=?", (task_id,))
        return self._task_from_row(row) if row else None

    def list_all_tasks(self) -> list[Task]:
        rows = self.db.query(self._TASK_SELECT + "ORDER BY t.position, t.id")
        return [self._task_from_row(r) for r in rows]

    def tasks_for_day(self, day: date) -> dict[str, list[Task]]:
        """Split tasks into today's pending, upcoming (due later), completed today
        and completed earlier."""
        today_s = day.isoformat()
        pending, upcoming, done_today, done_before = [], [], [], []
        for t in self.list_all_tasks():
            if t.completed_at:
                (done_today if clock.day_of(clock.parse_ts(t.completed_at)) == today_s else done_before).append(t)
            elif t.due_date and t.due_date > today_s:
                upcoming.append(t)
            else:
                pending.append(t)
        return {"pending": pending, "upcoming": upcoming, "done_today": done_today, "done_before": done_before}

    def set_task_completed(self, task_id: int, completed: bool, now: Optional[datetime] = None) -> bool:
        """Complete or reopen a task. Returns True only if the state changed, so a
        task can be completed exactly once until it is reopened."""
        now = _now(now)
        with self.db.transaction() as conn:
            row = conn.execute("SELECT completed_at FROM tasks WHERE id=?", (task_id,)).fetchone()
            if row is None:
                return False
            if completed and row["completed_at"] is None:
                conn.execute("UPDATE tasks SET completed_at=? WHERE id=?", (clock.iso_ts(now), task_id))
                conn.execute(
                    "INSERT OR IGNORE INTO task_completions(task_id, day, completed_at) VALUES(?,?,?)",
                    (task_id, clock.day_of(now), clock.iso_ts(now)),
                )
                return True
            if not completed and row["completed_at"] is not None:
                conn.execute("UPDATE tasks SET completed_at=NULL WHERE id=?", (task_id,))
                conn.execute("DELETE FROM task_completions WHERE task_id=?", (task_id,))
                return True
            return False

    def reorder_tasks(self, ordered_ids: Iterable[int]) -> None:
        with self.db.transaction() as conn:
            for pos, task_id in enumerate(ordered_ids):
                conn.execute("UPDATE tasks SET position=? WHERE id=?", (pos, task_id))

    def task_completion_counts(self, days: list[date]) -> dict[str, int]:
        if not days:
            return {}
        rows = self.db.query(
            "SELECT day, COUNT(*) AS n FROM task_completions WHERE day BETWEEN ? AND ? GROUP BY day",
            (days[0].isoformat(), days[-1].isoformat()),
        )
        return {r["day"]: r["n"] for r in rows}

    def count_completed_tasks(self) -> int:
        return int(self.db.scalar("SELECT COUNT(*) FROM task_completions", default=0))

    # ================================================================ habits
    def list_habits(self, include_inactive: bool = False) -> list[Habit]:
        sql = "SELECT * FROM habits" + ("" if include_inactive else " WHERE active=1") + " ORDER BY position, id"
        return [Habit(r["id"], r["name"], bool(r["counts_toward_streak"]), bool(r["active"]), r["position"])
                for r in self.db.query(sql)]

    def add_habit(self, name: str, counts_toward_streak: bool = True, now: Optional[datetime] = None) -> int:
        name = name.strip()
        if not name:
            raise ValueError("Habit name cannot be empty")
        with self.db.transaction() as conn:
            pos = conn.execute("SELECT COALESCE(MAX(position), -1) + 1 FROM habits").fetchone()[0]
            cur = conn.execute(
                "INSERT INTO habits(name, counts_toward_streak, position, created_at) VALUES(?,?,?,?)",
                (name, int(counts_toward_streak), pos, clock.iso_ts(_now(now))),
            )
            return int(cur.lastrowid)

    def update_habit(self, habit_id: int, *, name: Optional[str] = None,
                     counts_toward_streak: Optional[bool] = None, active: Optional[bool] = None) -> None:
        sets: dict[str, Any] = {}
        if name is not None:
            if not name.strip():
                raise ValueError("Habit name cannot be empty")
            sets["name"] = name.strip()
        if counts_toward_streak is not None:
            sets["counts_toward_streak"] = int(counts_toward_streak)
        if active is not None:
            sets["active"] = int(active)
        if sets:
            cols = ", ".join(f"{k}=?" for k in sets)
            self.db.execute(f"UPDATE habits SET {cols} WHERE id=?", (*sets.values(), habit_id))

    def delete_habit(self, habit_id: int) -> None:
        self.db.execute("DELETE FROM habits WHERE id=?", (habit_id,))

    def set_habit_done(self, habit_id: int, day: date, done: bool, now: Optional[datetime] = None) -> bool:
        """Mark a habit for a day. Returns True if the state changed."""
        if done:
            cur = self.db.execute(
                "INSERT OR IGNORE INTO habit_completions(habit_id, day, completed_at) VALUES(?,?,?)",
                (habit_id, day.isoformat(), clock.iso_ts(_now(now))),
            )
        else:
            cur = self.db.execute(
                "DELETE FROM habit_completions WHERE habit_id=? AND day=?", (habit_id, day.isoformat())
            )
        return cur.rowcount > 0

    def habit_days(self, habit_id: int) -> set[date]:
        rows = self.db.query("SELECT day FROM habit_completions WHERE habit_id=?", (habit_id,))
        return {clock.parse_day(r["day"]) for r in rows}

    def streak_days(self) -> set[date]:
        """Days on which at least one habit that counts toward the overall streak was done."""
        rows = self.db.query(
            "SELECT DISTINCT hc.day FROM habit_completions hc JOIN habits h ON h.id = hc.habit_id "
            "WHERE h.counts_toward_streak = 1"
        )
        return {clock.parse_day(r["day"]) for r in rows}

    def habits_done_on(self, day: date) -> set[int]:
        rows = self.db.query("SELECT habit_id FROM habit_completions WHERE day=?", (day.isoformat(),))
        return {r["habit_id"] for r in rows}

    # ================================================================ focus
    def record_focus_session(self, *, session_uid: str, kind: str, task_id: Optional[int],
                             planned_seconds: int, actual_seconds: int, status: str,
                             started_at: datetime, ended_at: datetime) -> bool:
        """Insert a session once; duplicates (same uid) are ignored. Returns True if inserted."""
        if task_id is not None and self.db.query_one("SELECT 1 FROM tasks WHERE id=?", (task_id,)) is None:
            task_id = None
        cur = self.db.execute(
            "INSERT OR IGNORE INTO focus_sessions(session_uid, task_id, kind, planned_seconds, actual_seconds, "
            "status, started_at, ended_at, day) VALUES(?,?,?,?,?,?,?,?,?)",
            (session_uid, task_id, kind, int(planned_seconds), int(actual_seconds), status,
             clock.iso_ts(started_at), clock.iso_ts(ended_at), clock.day_of(started_at)),
        )
        return cur.rowcount > 0

    def focus_summary(self, day: date) -> dict[str, int]:
        row = self.db.query_one(
            "SELECT COALESCE(SUM(actual_seconds),0) AS secs, "
            "COALESCE(SUM(CASE WHEN status='completed' THEN 1 ELSE 0 END),0) AS done "
            "FROM focus_sessions WHERE kind='focus' AND day=?",
            (day.isoformat(),),
        )
        return {"seconds": int(row["secs"]), "completed": int(row["done"])}

    def count_completed_focus_sessions(self) -> int:
        return int(self.db.scalar(
            "SELECT COUNT(*) FROM focus_sessions WHERE kind='focus' AND status='completed'", default=0))

    def focus_sessions(self, task_id: Optional[int] = None) -> list[dict]:
        sql = "SELECT * FROM focus_sessions"
        params: tuple = ()
        if task_id is not None:
            sql += " WHERE task_id=?"
            params = (task_id,)
        return [dict(r) for r in self.db.query(sql + " ORDER BY started_at", params)]

    # ================================================================ usage
    def ensure_app(self, exe: str, display_name: str, exe_path: Optional[str], category: str,
                   now: Optional[datetime] = None) -> None:
        if category not in APP_CATEGORIES:
            category = "other"
        self.db.execute(
            "INSERT INTO app_meta(exe, display_name, exe_path, category, first_seen) VALUES(?,?,?,?,?) "
            "ON CONFLICT(exe) DO UPDATE SET exe_path = COALESCE(excluded.exe_path, app_meta.exe_path)",
            (exe, display_name, exe_path, category, clock.iso_ts(_now(now))),
        )

    def app_known(self, exe: str) -> bool:
        return self.db.query_one("SELECT 1 FROM app_meta WHERE exe=?", (exe,)) is not None

    def set_app_category(self, exe: str, category: str) -> None:
        if category not in APP_CATEGORIES:
            raise ValueError(f"Unknown category {category}")
        self.db.execute("UPDATE app_meta SET category=? WHERE exe=?", (category, exe))

    def set_app_display_name(self, exe: str, name: str) -> None:
        if name.strip():
            self.db.execute("UPDATE app_meta SET display_name=? WHERE exe=?", (name.strip(), exe))

    def list_apps(self) -> list[dict]:
        return [dict(r) for r in self.db.query("SELECT * FROM app_meta ORDER BY display_name COLLATE NOCASE")]

    def apply_usage(self, app_seconds: dict[tuple[str, str], float],
                    hourly: dict[tuple[str, int], tuple[float, float]],
                    daily: dict[str, tuple[float, float]],
                    observed: dict[str, tuple[str, str]]) -> None:
        """Add aggregated usage in a single transaction (additive upserts)."""
        with self.db.transaction() as conn:
            for (day, exe), secs in app_seconds.items():
                conn.execute(
                    "INSERT INTO app_usage(day, exe, seconds) VALUES(?,?,?) "
                    "ON CONFLICT(day, exe) DO UPDATE SET seconds = seconds + excluded.seconds",
                    (day, exe, secs),
                )
            for (day, hour), (act, idle) in hourly.items():
                conn.execute(
                    "INSERT INTO usage_hourly(day, hour, active_seconds, idle_seconds) VALUES(?,?,?,?) "
                    "ON CONFLICT(day, hour) DO UPDATE SET active_seconds = active_seconds + excluded.active_seconds, "
                    "idle_seconds = idle_seconds + excluded.idle_seconds",
                    (day, hour, act, idle),
                )
            for day, (act, idle) in daily.items():
                first, last = observed.get(day, (None, None))
                conn.execute(
                    "INSERT INTO daily_usage(day, active_seconds, idle_seconds, first_observed, last_observed) "
                    "VALUES(?,?,?,?,?) ON CONFLICT(day) DO UPDATE SET "
                    "active_seconds = active_seconds + excluded.active_seconds, "
                    "idle_seconds = idle_seconds + excluded.idle_seconds, "
                    "first_observed = COALESCE(daily_usage.first_observed, excluded.first_observed), "
                    "last_observed = COALESCE(excluded.last_observed, daily_usage.last_observed)",
                    (day, act, idle, first, last),
                )

    def app_usage_for(self, start: date, end: Optional[date] = None) -> list[AppUsage]:
        end = end or start
        rows = self.db.query(
            "SELECT u.exe, m.display_name, m.category, m.exe_path, SUM(u.seconds) AS secs "
            "FROM app_usage u JOIN app_meta m ON m.exe = u.exe WHERE u.day BETWEEN ? AND ? "
            "GROUP BY u.exe ORDER BY secs DESC",
            (start.isoformat(), end.isoformat()),
        )
        return [AppUsage(r["exe"], r["display_name"], r["category"], float(r["secs"]), r["exe_path"]) for r in rows]

    def category_totals(self, start: date, end: Optional[date] = None) -> dict[str, float]:
        totals = {c: 0.0 for c in APP_CATEGORIES}
        for app in self.app_usage_for(start, end):
            totals[app.category] = totals.get(app.category, 0.0) + app.seconds
        return totals

    def daily_usage(self, day: date) -> dict[str, Any]:
        row = self.db.query_one("SELECT * FROM daily_usage WHERE day=?", (day.isoformat(),))
        if row is None:
            return {"active_seconds": 0.0, "idle_seconds": 0.0, "first_observed": None, "last_observed": None}
        return dict(row)

    def daily_usage_range(self, days: list[date]) -> dict[str, dict]:
        if not days:
            return {}
        rows = self.db.query(
            "SELECT * FROM daily_usage WHERE day BETWEEN ? AND ?", (days[0].isoformat(), days[-1].isoformat())
        )
        return {r["day"]: dict(r) for r in rows}

    def hourly_usage(self, day: date) -> list[tuple[float, float]]:
        out = [(0.0, 0.0)] * 24
        for r in self.db.query("SELECT * FROM usage_hourly WHERE day=?", (day.isoformat(),)):
            out[r["hour"]] = (float(r["active_seconds"]), float(r["idle_seconds"]))
        return out

    def purge_usage_before(self, cutoff: date) -> int:
        with self.db.transaction() as conn:
            n = conn.execute("DELETE FROM app_usage WHERE day < ?", (cutoff.isoformat(),)).rowcount
            conn.execute("DELETE FROM usage_hourly WHERE day < ?", (cutoff.isoformat(),))
            return n

    # ================================================================ water
    def add_water(self, amount_ml: int, now: Optional[datetime] = None) -> int:
        now = _now(now)
        cur = self.db.execute(
            "INSERT INTO water_entries(day, amount_ml, logged_at) VALUES(?,?,?)",
            (clock.day_of(now), int(amount_ml), clock.iso_ts(now)),
        )
        return int(cur.lastrowid)

    def undo_last_water(self, day: date) -> bool:
        with self.db.transaction() as conn:
            row = conn.execute(
                "SELECT id FROM water_entries WHERE day=? ORDER BY logged_at DESC, id DESC LIMIT 1",
                (day.isoformat(),),
            ).fetchone()
            if row is None:
                return False
            conn.execute("DELETE FROM water_entries WHERE id=?", (row["id"],))
            return True

    def water_total(self, day: date) -> tuple[int, int]:
        row = self.db.query_one(
            "SELECT COALESCE(SUM(amount_ml),0) AS ml, COUNT(*) AS n FROM water_entries WHERE day=?",
            (day.isoformat(),),
        )
        return int(row["ml"]), int(row["n"])

    def water_history(self, days: list[date]) -> dict[str, int]:
        if not days:
            return {}
        rows = self.db.query(
            "SELECT day, SUM(amount_ml) AS ml FROM water_entries WHERE day BETWEEN ? AND ? GROUP BY day",
            (days[0].isoformat(), days[-1].isoformat()),
        )
        return {r["day"]: int(r["ml"]) for r in rows}

    def last_water_time(self) -> Optional[datetime]:
        val = self.db.scalar("SELECT MAX(logged_at) FROM water_entries")
        return clock.parse_ts(val) if val else None

    # ================================================================ movement
    def start_movement_break(self, planned_seconds: int, desk_seconds: int, now: Optional[datetime] = None) -> int:
        now = _now(now)
        with self.db.transaction() as conn:
            conn.execute(
                "UPDATE movement_breaks SET status='cancelled', ended_at=? WHERE status='in_progress'",
                (clock.iso_ts(now),),
            )
            cur = conn.execute(
                "INSERT INTO movement_breaks(day, started_at, planned_seconds, status, desk_seconds_before) "
                "VALUES(?,?,?,?,?)",
                (clock.day_of(now), clock.iso_ts(now), int(planned_seconds), "in_progress", int(desk_seconds)),
            )
            return int(cur.lastrowid)

    def finish_movement_break(self, break_id: int, completed: bool, now: Optional[datetime] = None) -> bool:
        cur = self.db.execute(
            "UPDATE movement_breaks SET status=?, ended_at=? WHERE id=? AND status='in_progress'",
            ("completed" if completed else "cancelled", clock.iso_ts(_now(now)), break_id),
        )
        return cur.rowcount > 0

    def movement_breaks_on(self, day: date) -> list[dict]:
        return [dict(r) for r in self.db.query(
            "SELECT * FROM movement_breaks WHERE day=? ORDER BY started_at", (day.isoformat(),))]

    def count_completed_breaks(self) -> int:
        return int(self.db.scalar("SELECT COUNT(*) FROM movement_breaks WHERE status='completed'", default=0))

    def close_dangling_breaks(self, now: Optional[datetime] = None) -> None:
        self.db.execute(
            "UPDATE movement_breaks SET status='cancelled', ended_at=? WHERE status='in_progress'",
            (clock.iso_ts(_now(now)),),
        )

    # ================================================================ xp & achievements
    def award_xp(self, source_key: str, amount: int, reason: str, now: Optional[datetime] = None) -> bool:
        now = _now(now)
        cur = self.db.execute(
            "INSERT OR IGNORE INTO xp_transactions(source_key, amount, reason, day, created_at) VALUES(?,?,?,?,?)",
            (source_key, int(amount), reason, clock.day_of(now), clock.iso_ts(now)),
        )
        return cur.rowcount > 0

    def revoke_xp(self, source_key: str) -> bool:
        return self.db.execute("DELETE FROM xp_transactions WHERE source_key=?", (source_key,)).rowcount > 0

    def total_xp(self) -> int:
        return int(self.db.scalar("SELECT COALESCE(SUM(amount),0) FROM xp_transactions", default=0))

    def unlock_achievement(self, key: str, now: Optional[datetime] = None) -> bool:
        cur = self.db.execute(
            "INSERT OR IGNORE INTO achievements(key, unlocked_at) VALUES(?,?)", (key, clock.iso_ts(_now(now)))
        )
        return cur.rowcount > 0

    def achievements(self) -> dict[str, str]:
        return {r["key"]: r["unlocked_at"] for r in self.db.query("SELECT * FROM achievements")}

    # ================================================================ misc
    def end_of_day_summary(self, day: date) -> dict[str, Any]:
        tasks = self.tasks_for_day(day)
        water_ml, servings = self.water_total(day)
        usage = self.daily_usage(day)
        focus = self.focus_summary(day)
        cats = self.category_totals(day)
        return {
            "tasks_done": len(tasks["done_today"]),
            "tasks_total": len(tasks["done_today"]) + len(tasks["pending"]),
            "focus_seconds": focus["seconds"],
            "focus_sessions": focus["completed"],
            "water_ml": water_ml,
            "water_servings": servings,
            "active_seconds": usage["active_seconds"],
            "productive_seconds": cats.get("productive", 0.0) + cats.get("learning", 0.0),
            "breaks": sum(1 for b in self.movement_breaks_on(day) if b["status"] == "completed"),
        }

    def week_ago(self, day: date) -> date:
        return day - timedelta(days=6)
