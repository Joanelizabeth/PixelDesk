from datetime import date, datetime, timedelta, timezone

import pytest

from app.settings_store import SettingsStore
from database.connection import Database, DatabaseError
from database.repository import Repository
from database.schema import SCHEMA_VERSION, migrate

TZ = timezone(timedelta(hours=5, minutes=30))


def at(y, m, d, hh=12, mm=0):
    return datetime(y, m, d, hh, mm, tzinfo=TZ).astimezone()


def test_migration_sets_version_and_is_idempotent(db_file):
    db = Database(db_file)
    assert migrate(db) == SCHEMA_VERSION
    assert db.user_version == SCHEMA_VERSION
    migrate(db)  # second run is a no-op
    assert db.user_version == SCHEMA_VERSION
    db.close()


def test_task_create_edit_delete(repo):
    tid = repo.add_task("Study Python", priority=2, estimate_minutes=45, category="Learning")
    task = repo.get_task(tid)
    assert task.title == "Study Python" and task.priority == 2 and task.estimate_minutes == 45
    repo.update_task(tid, title="  Solve three DSA problems ", due_date="2026-10-30")
    task = repo.get_task(tid)
    assert task.title == "Solve three DSA problems" and task.due_date == "2026-10-30"
    with pytest.raises(ValueError):
        repo.update_task(tid, title="   ")
    repo.delete_task(tid)
    assert repo.get_task(tid) is None


def test_empty_task_title_rejected(repo):
    with pytest.raises(ValueError):
        repo.add_task("   ")


def test_task_completed_exactly_once(repo):
    tid = repo.add_task("Go for a walk")
    now = datetime.now().astimezone()
    assert repo.set_task_completed(tid, True, now) is True
    assert repo.set_task_completed(tid, True, now) is False  # second completion is ignored
    assert repo.count_completed_tasks() == 1
    rows = repo.db.query("SELECT * FROM task_completions WHERE task_id=?", (tid,))
    assert len(rows) == 1
    assert repo.set_task_completed(tid, False) is True
    assert repo.count_completed_tasks() == 0


def test_tasks_for_day_partitions(repo):
    today = date(2026, 10, 27)
    a = repo.add_task("pending")
    b = repo.add_task("future", due_date="2026-11-02")
    c = repo.add_task("done today")
    d = repo.add_task("done earlier")
    repo.set_task_completed(c, True, at(2026, 10, 27, 9))
    repo.set_task_completed(d, True, at(2026, 10, 25, 9))
    parts = repo.tasks_for_day(today)
    assert [t.id for t in parts["pending"]] == [a]
    assert [t.id for t in parts["upcoming"]] == [b]
    assert [t.id for t in parts["done_today"]] == [c]
    assert [t.id for t in parts["done_before"]] == [d]


def test_reorder_tasks(repo):
    ids = [repo.add_task(f"t{i}") for i in range(3)]
    repo.reorder_tasks(list(reversed(ids)))
    assert [t.id for t in repo.list_all_tasks()] == list(reversed(ids))


def test_water_entry_and_undo(repo):
    day = date(2026, 10, 27)
    repo.add_water(250, at(2026, 10, 27, 9))
    repo.add_water(250, at(2026, 10, 27, 10))
    repo.add_water(300, at(2026, 10, 26, 10))
    assert repo.water_total(day) == (500, 2)
    assert repo.undo_last_water(day) is True
    assert repo.water_total(day) == (250, 1)
    assert repo.water_total(date(2026, 10, 26)) == (300, 1)  # other days untouched
    assert repo.undo_last_water(day) is True
    assert repo.undo_last_water(day) is False


def test_focus_session_deduplicated(repo):
    tid = repo.add_task("Work on FITQUEST")
    now = datetime.now().astimezone()
    kwargs = dict(session_uid="abc", kind="focus", task_id=tid, planned_seconds=1500, actual_seconds=1500,
                  status="completed", started_at=now - timedelta(minutes=25), ended_at=now)
    assert repo.record_focus_session(**kwargs) is True
    assert repo.record_focus_session(**kwargs) is False
    assert repo.get_task(tid).focus_seconds == 1500
    assert repo.count_completed_focus_sessions() == 1


def test_focus_session_with_deleted_task(repo):
    now = datetime.now().astimezone()
    assert repo.record_focus_session(session_uid="x", kind="focus", task_id=999, planned_seconds=60,
                                     actual_seconds=60, status="completed", started_at=now, ended_at=now)
    assert repo.focus_sessions()[0]["task_id"] is None


def test_xp_not_duplicated(repo):
    assert repo.award_xp("task:1", 10, "x") is True
    assert repo.award_xp("task:1", 10, "x") is False
    assert repo.total_xp() == 10


def test_persistence_across_restart(db_file):
    db = Database(db_file)
    migrate(db)
    repo = Repository(db)
    settings = SettingsStore(repo)
    settings.set("water_goal_servings", 10)
    tid = repo.add_task("Update resume")
    repo.add_water(250)
    lid = repo.add_launcher_item("Projects", "folder", "/tmp", "rocket")
    db.close()

    db2 = Database(db_file)
    migrate(db2)
    repo2 = Repository(db2)
    assert SettingsStore(repo2)["water_goal_servings"] == 10
    assert repo2.get_task(tid).title == "Update resume"
    assert repo2.water_total(date.today())[0] == 250
    assert repo2.list_launcher_items()[0].id == lid
    db2.close()


def test_settings_defaults_and_nested_merge(repo):
    repo.save_setting("widgets_visible", {"water": False})
    s = SettingsStore(repo)
    vis = s["widgets_visible"]
    assert vis["water"] is False and vis["wheel"] is True  # new keys get defaults
    assert s["focus_minutes"] == 25
    seen = []
    s.subscribe(lambda k, v: seen.append(k))
    s.set("focus_minutes", 30)
    s.set("focus_minutes", 30)  # unchanged -> no event
    assert seen == ["focus_minutes"]


def test_backup_and_restore(repo, tmp_path):
    repo.add_task("keep me")
    backup = repo.db.backup_to(tmp_path / "b.db")
    assert Database.validate_backup(backup) >= 1
    bogus = tmp_path / "bogus.db"
    bogus.write_bytes(b"not a database at all" * 10)
    with pytest.raises(DatabaseError):
        Database.validate_backup(bogus)

    target = tmp_path / "restored.db"
    Database.restore_file(backup, target)
    db = Database(target)
    assert Repository(db).list_all_tasks()[0].title == "keep me"
    db.close()


def test_launcher_items_crud(repo):
    a = repo.add_launcher_item("College", "folder", "C:/College")
    b = repo.add_launcher_item("Notes", "folder", "C:/Notes", "note")
    repo.reorder_launcher_items([b, a])
    assert [i.label for i in repo.list_launcher_items()] == ["Notes", "College"]
    repo.update_launcher_item(a, label="Uni", path="C:/Uni", icon="cap", kind="folder")
    repo.delete_launcher_item(b)
    items = repo.list_launcher_items()
    assert len(items) == 1 and items[0].label == "Uni" and items[0].icon == "cap"


def test_habit_toggle_unique_per_day(repo):
    h = repo.add_habit("Reading")
    d = date(2026, 10, 27)
    assert repo.set_habit_done(h, d, True)
    assert not repo.set_habit_done(h, d, True)
    assert repo.habit_days(h) == {d}
    assert repo.set_habit_done(h, d, False)
    assert repo.habit_days(h) == set()
