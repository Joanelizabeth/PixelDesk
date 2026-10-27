"""Streaks, XP, levels and achievements.

Date rules:
* A streak counts consecutive calendar days with at least one completion.
* Today not being done yet does not break the streak: until the day ends the
  streak continues from yesterday ("opening the app late" never resets it).
* XP is keyed by a unique source (task id, habit+day, session uid...), so
  re-checking the same item can never award duplicate XP.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Callable, Iterable, Optional

from app import clock
from database.repository import Repository

log = logging.getLogger(__name__)


def current_streak(days: Iterable[date], today: date) -> int:
    done = set(days)
    if today in done:
        cursor = today
    elif today - timedelta(days=1) in done:
        cursor = today - timedelta(days=1)
    else:
        return 0
    count = 0
    while cursor in done:
        count += 1
        cursor -= timedelta(days=1)
    return count


def longest_streak(days: Iterable[date]) -> int:
    ordered = sorted(set(days))
    best = run = 0
    prev: Optional[date] = None
    for d in ordered:
        run = run + 1 if prev is not None and d - prev == timedelta(days=1) else 1
        best = max(best, run)
        prev = d
    return best


def completion_rate(days: Iterable[date], start: date, end: date) -> float:
    total = (end - start).days + 1
    if total <= 0:
        return 0.0
    done = sum(1 for d in set(days) if start <= d <= end)
    return done / total


def weekly_completion(habit_days: dict[int, set[date]], today: date) -> float:
    """Share of (habit, day) slots completed over the last 7 days including today."""
    if not habit_days:
        return 0.0
    start = today - timedelta(days=6)
    slots = 7 * len(habit_days)
    done = sum(sum(1 for d in ds if start <= d <= today) for ds in habit_days.values())
    return done / slots


def month_grid(year: int, month: int) -> list[list[Optional[date]]]:
    """Weeks (Mon..Sun) of a month; cells outside the month are None."""
    first = date(year, month, 1)
    nxt = date(year + (month == 12), (month % 12) + 1, 1)
    weeks: list[list[Optional[date]]] = []
    week: list[Optional[date]] = [None] * first.weekday()
    d = first
    while d < nxt:
        week.append(d)
        if len(week) == 7:
            weeks.append(week)
            week = []
        d += timedelta(days=1)
    if week:
        weeks.append(week + [None] * (7 - len(week)))
    return weeks


# ---------------------------------------------------------------- levels
def xp_for_level(level: int) -> int:
    """Cumulative XP needed to reach `level` (level 1 = 0 XP)."""
    return 50 * level * (level - 1)


def level_for_xp(xp: int) -> tuple[int, int, int]:
    """Return (level, xp into level, xp span of level)."""
    level = 1
    while xp >= xp_for_level(level + 1):
        level += 1
    base = xp_for_level(level)
    return level, xp - base, xp_for_level(level + 1) - base


XP_REWARDS = {"task": 10, "habit": 5, "focus": 15, "water_goal": 5, "movement": 5}


@dataclass(frozen=True)
class Achievement:
    key: str
    title: str
    description: str
    icon: str


ACHIEVEMENTS: list[Achievement] = [
    Achievement("first_task", "First Step", "Complete your first task.", "star"),
    Achievement("tasks_25", "Steady Hands", "Complete 25 tasks.", "rocket"),
    Achievement("first_focus", "In the Zone", "Finish a full focus session.", "code"),
    Achievement("focus_20", "Deep Diver", "Finish 20 focus sessions.", "moon"),
    Achievement("streak_3", "Warming Up", "Reach a 3-day streak.", "flame"),
    Achievement("streak_7", "Week Strong", "Reach a 7-day streak.", "flame"),
    Achievement("streak_30", "Monthly Glow", "Reach a 30-day streak.", "heart"),
    Achievement("hydrated", "Well Watered", "Reach your water goal for a day.", "drop"),
    Achievement("first_walk", "Leg Day", "Complete a movement break.", "walk"),
    Achievement("level_5", "Rising Pixel", "Reach level 5.", "star"),
]
ACHIEVEMENT_BY_KEY = {a.key: a for a in ACHIEVEMENTS}


class ProgressService:
    """Applies completions to the database and handles XP/achievements."""

    def __init__(self, repo: Repository, xp_enabled: Callable[[], bool] = lambda: True):
        self.repo = repo
        self._xp_enabled = xp_enabled

    # -- XP helpers ---------------------------------------------------
    def _award(self, key: str, kind: str, reason: str, now: Optional[datetime]) -> bool:
        if not self._xp_enabled():
            return False
        return self.repo.award_xp(key, XP_REWARDS[kind], reason, now)

    # -- events -------------------------------------------------------
    def complete_task(self, task_id: int, done: bool, now: Optional[datetime] = None) -> bool:
        changed = self.repo.set_task_completed(task_id, done, now)
        if changed:
            if done:
                self._award(f"task:{task_id}", "task", "Completed a task", now)
            else:
                self.repo.revoke_xp(f"task:{task_id}")
        return changed

    def set_habit(self, habit_id: int, day: date, done: bool, now: Optional[datetime] = None) -> bool:
        changed = self.repo.set_habit_done(habit_id, day, done, now)
        key = f"habit:{habit_id}:{day.isoformat()}"
        if changed:
            if done:
                self._award(key, "habit", "Habit check-in", now)
            else:
                self.repo.revoke_xp(key)
        return changed

    def focus_completed(self, session_uid: str, now: Optional[datetime] = None) -> bool:
        return self._award(f"focus:{session_uid}", "focus", "Focus session", now)

    def water_goal_reached(self, day: date, now: Optional[datetime] = None) -> bool:
        return self._award(f"water:{day.isoformat()}", "water_goal", "Water goal", now)

    def movement_completed(self, break_id: int, now: Optional[datetime] = None) -> bool:
        return self._award(f"move:{break_id}", "movement", "Movement break", now)

    # -- summaries ----------------------------------------------------
    def overall_streak(self, today: Optional[date] = None) -> tuple[int, int]:
        today = today or clock.today()
        days = self.repo.streak_days()
        return current_streak(days, today), longest_streak(days)

    def level(self) -> tuple[int, int, int, int]:
        xp = self.repo.total_xp()
        lvl, into, span = level_for_xp(xp)
        return lvl, into, span, xp

    def check_achievements(self, today: Optional[date] = None, water_goal_met: bool = False,
                           now: Optional[datetime] = None) -> list[Achievement]:
        today = today or clock.today()
        cur, longest = self.overall_streak(today)
        best = max(cur, longest)
        tasks = self.repo.count_completed_tasks()
        focus = self.repo.count_completed_focus_sessions()
        conditions = {
            "first_task": tasks >= 1,
            "tasks_25": tasks >= 25,
            "first_focus": focus >= 1,
            "focus_20": focus >= 20,
            "streak_3": best >= 3,
            "streak_7": best >= 7,
            "streak_30": best >= 30,
            "hydrated": water_goal_met,
            "first_walk": self.repo.count_completed_breaks() >= 1,
            "level_5": level_for_xp(self.repo.total_xp())[0] >= 5,
        }
        unlocked = []
        for key, met in conditions.items():
            if met and self.repo.unlock_achievement(key, now):
                unlocked.append(ACHIEVEMENT_BY_KEY[key])
        return unlocked
