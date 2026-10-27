from datetime import date, timedelta

from database.repository import Repository
from services.streak_service import (
    ProgressService, completion_rate, current_streak, level_for_xp, longest_streak, month_grid,
    weekly_completion, xp_for_level,
)

D = date(2026, 10, 27)


def days(*offsets):
    return {D - timedelta(days=o) for o in offsets}


def test_consecutive_days_streak():
    assert current_streak(days(0, 1, 2, 3), D) == 4


def test_today_not_done_yet_keeps_streak():
    # Opening the app late in the day must not break the streak.
    assert current_streak(days(1, 2, 3), D) == 3


def test_missing_day_breaks_streak():
    assert current_streak(days(2, 3, 4), D) == 0
    assert current_streak(days(0, 2, 3), D) == 1


def test_longest_streak_with_gaps():
    assert longest_streak(days(0, 1, 5, 6, 7, 8, 12)) == 4
    assert longest_streak(set()) == 0


def test_streak_across_month_and_year_boundaries():
    s = {date(2025, 12, 30), date(2025, 12, 31), date(2026, 1, 1), date(2026, 1, 2)}
    assert current_streak(s, date(2026, 1, 2)) == 4
    assert longest_streak(s) == 4
    leap = {date(2028, 2, 28), date(2028, 2, 29), date(2028, 3, 1)}
    assert current_streak(leap, date(2028, 3, 1)) == 3


def test_completion_rates():
    assert completion_rate(days(0, 1, 2), D - timedelta(days=6), D) == 3 / 7
    assert weekly_completion({1: days(0, 1), 2: days(0)}, D) == 3 / 14
    assert weekly_completion({}, D) == 0.0


def test_month_grid_shape():
    grid = month_grid(2026, 10)
    assert all(len(w) == 7 for w in grid)
    flat = [d for w in grid for d in w if d]
    assert flat[0] == date(2026, 10, 1) and flat[-1] == date(2026, 10, 31)
    assert grid[0].index(date(2026, 10, 1)) == date(2026, 10, 1).weekday()


def test_levels():
    assert level_for_xp(0) == (1, 0, 100)
    assert xp_for_level(2) == 100
    assert level_for_xp(100)[0] == 2
    assert level_for_xp(299)[0] == 2 and level_for_xp(300)[0] == 3


def test_progress_service_no_duplicate_xp(repo: Repository):
    p = ProgressService(repo)
    tid = repo.add_task("Read for 20 minutes")
    assert p.complete_task(tid, True)
    assert not p.complete_task(tid, True)
    assert repo.total_xp() == 10
    p.complete_task(tid, False)  # reopening revokes
    assert repo.total_xp() == 0
    p.complete_task(tid, True)
    assert repo.total_xp() == 10

    h = repo.add_habit("Coding")
    p.set_habit(h, D, True)
    p.set_habit(h, D, True)
    assert repo.total_xp() == 15


def test_overall_streak_respects_configured_habits(repo: Repository):
    p = ProgressService(repo)
    counted = repo.add_habit("DSA", counts_toward_streak=True)
    ignored = repo.add_habit("Gaming", counts_toward_streak=False)
    for o in (1, 2):
        p.set_habit(counted, D - timedelta(days=o), True)
    p.set_habit(ignored, D - timedelta(days=3), True)
    assert p.overall_streak(D) == (2, 2)


def test_xp_disabled(repo):
    p = ProgressService(repo, xp_enabled=lambda: False)
    tid = repo.add_task("x")
    p.complete_task(tid, True)
    assert repo.total_xp() == 0


def test_achievements_unlock_once(repo):
    p = ProgressService(repo)
    tid = repo.add_task("x")
    p.complete_task(tid, True)
    first = p.check_achievements(D)
    assert "first_task" in [a.key for a in first]
    assert p.check_achievements(D) == []
