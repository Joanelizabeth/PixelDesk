"""Integration tests: the real application starts headless with a mocked
Windows activity probe, loads configuration and survives a restart."""
import time

import pytest
from PySide6.QtCore import QSize

from winintegration.probe import Sample


class MockProbe:
    available = True

    def __init__(self, exe="code.exe", idle=0.0, locked=False):
        self.exe, self.idle, self.locked = exe, idle, locked

    def sample(self):
        return Sample(self.exe if not self.locked else None, None, 1, self.idle, self.locked)


@pytest.fixture
def started_app(qapp, tmp_path, monkeypatch):
    monkeypatch.setenv("PIXELDESK_DATA_DIR", str(tmp_path / "data"))
    from app.application import PixelDeskApplication

    apps = []

    def make(probe=None):
        app = PixelDeskApplication(qapp, probe=probe or MockProbe(), db_file=tmp_path / "app.db")
        ctx = app.start()
        apps.append(app)
        return app, ctx

    yield make
    for app in apps:
        app.shutdown()


def test_startup_loads_defaults_and_builds_window(started_app):
    app, ctx = started_app()
    assert ctx.settings["focus_minutes"] == 25
    assert ctx.settings["first_run_done"] is True
    assert {h.name for h in ctx.repo.list_habits()} == {"Coding", "DSA", "Exercise", "Reading"}
    assert ctx.repo.list_all_tasks() == []  # no hardcoded tasks
    shell = app.shell
    assert shell.mode == "window" and shell.window is not None
    assert set(shell.panels) == {"wheel", "clock", "character", "tasks", "water", "movement", "screen_time"}
    img = shell.window.grab()
    assert not img.isNull() and img.width() > 800


def test_settings_persist_across_restart(started_app):
    app, ctx = started_app()
    ctx.settings.set("theme", "midnight_blue")
    ctx.settings.set("water_goal_servings", 6)
    tid = ctx.repo.add_task("Update resume")
    ctx.wellbeing.log_water()
    app.shutdown()
    app2, ctx2 = started_app()
    assert ctx2.settings["theme"] == "midnight_blue"
    assert ctx2.settings["water_goal_servings"] == 6
    assert ctx2.repo.get_task(tid).title == "Update resume"
    assert ctx2.wellbeing.water_status()["servings"] == 1
    # first-run seeding happens once only
    assert len(ctx2.repo.list_habits()) == 4


def test_monitor_records_usage_through_app(started_app, qapp):
    app, ctx = started_app()
    seen = []
    app.monitor.status.connect(lambda st: seen.append(st))
    deadline = time.time() + 5
    while time.time() < deadline and len(seen) < 3:
        qapp.processEvents()
        time.sleep(0.05)
    assert ctx.monitor_status is not None and ctx.monitor_status.state.value == "active"
    app.shutdown()  # flushes pending usage
    from datetime import date
    db_rows = ctx.repo.db  # closed now; reopen to verify persistence
    from database.connection import Database
    from database.repository import Repository
    repo = Repository(Database(db_rows.path))
    assert sum(a.seconds for a in repo.app_usage_for(date.today())) > 0


def test_pausing_monitoring_reports_paused(started_app, qapp):
    app, ctx = started_app()
    ctx.settings.set("monitoring_enabled", False)
    deadline = time.time() + 3
    while time.time() < deadline and (ctx.monitor_status is None or ctx.monitor_status.state.value != "paused"):
        qapp.processEvents()
        time.sleep(0.05)
    assert ctx.monitor_status.state.value == "paused"


def test_wheel_handles_invalid_paths(started_app, tmp_path):
    app, ctx = started_app()
    good = tmp_path / "Projects"
    good.mkdir()
    ctx.repo.add_launcher_item("Projects", "folder", str(good), "rocket")
    ctx.repo.add_launcher_item("Gone", "folder", str(tmp_path / "gone"), "folder")
    ctx.notify_changed("launcher")
    opened = []
    ctx.launcher._opener = lambda p, k: opened.append(p)
    wheel = app.shell.panels["wheel"]
    labels = [i.label for i in wheel.items]
    wheel.launch(labels.index("Gone"))
    wheel.launch(labels.index("Projects"))
    assert opened == [str(good)]
    assert wheel._valid[labels.index("Gone")] is False
    assert (tmp_path / "Projects").is_dir()  # nothing on disk changed


def test_wheel_keyboard_navigation(started_app, tmp_path, qapp):
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest

    app, ctx = started_app()
    for name in ("A", "B", "C"):
        (tmp_path / name).mkdir()
        ctx.repo.add_launcher_item(name, "folder", str(tmp_path / name))
    ctx.notify_changed("launcher")
    opened = []
    ctx.launcher._opener = lambda p, k: opened.append(p)
    wheel = app.shell.panels["wheel"]
    wheel._selected = -1
    QTest.keyClick(wheel, Qt.Key.Key_Right)
    QTest.keyClick(wheel, Qt.Key.Key_Right)
    QTest.keyClick(wheel, Qt.Key.Key_Return)
    assert len(opened) == 1


def test_water_goal_awards_xp_once(started_app):
    app, ctx = started_app()
    ctx.settings.set("water_goal_servings", 2)
    for _ in range(4):
        ctx.wellbeing.log_water()
    assert ctx.repo.total_xp() == 5
    assert ctx.wellbeing.undo_water()
    assert ctx.wellbeing.water_status()["servings"] == 3


def test_movement_reminder_signal(started_app):
    from app import clock

    app, ctx = started_app()
    fired = []
    ctx.wellbeing.movement_due.connect(lambda: fired.append(1))
    ctx.settings.set("quiet_hours_enabled", False)
    tr = ctx.wellbeing.movement
    tr.desk_seconds = tr.interval_seconds
    ctx.wellbeing._apply_movement_events(tr.update(clock.now(), 0, True))
    assert fired == [1]
    ctx.wellbeing.start_break()
    assert ctx.repo.movement_breaks_on(clock.today())[-1]["status"] == "in_progress"
    ctx.wellbeing.cancel_break()
    assert ctx.repo.movement_breaks_on(clock.today())[-1]["status"] == "cancelled"


def test_all_dialogs_open(started_app):
    app, ctx = started_app()
    for key in ("tasks", "water", "movement", "screen_time", "streaks", "settings:launcher"):
        app.shell.open_section(key)
    assert set(app.shell.dialogs) == {"tasks", "water", "movement", "screen_time", "streaks", "settings"}
    for dlg in app.shell.dialogs.values():
        assert not dlg.grab().isNull()


def test_theme_switch_restyles(started_app):
    app, ctx = started_app()
    for key in ("midnight_blue", "warm_charcoal", "muted_pastel", "dark_purple"):
        ctx.settings.set("theme", key)
        assert not app.shell.window.grab().isNull()


def test_default_layout_has_no_overlaps():
    from ui.desktop_shell import default_positions

    sizes = {"wheel": QSize(460, 460), "clock": QSize(380, 150), "character": QSize(300, 440),
             "tasks": QSize(236, 96), "water": QSize(236, 96), "movement": QSize(236, 96),
             "screen_time": QSize(236, 96)}
    for area in (QSize(1920, 1040), QSize(2560, 1400), QSize(1600, 856)):
        pos = default_positions(area, sizes)
        from PySide6.QtCore import QRect
        rects = {k: QRect(pos[k], sizes[k]) for k in sizes}
        for a in rects:
            assert rects[a].left() >= 0 and rects[a].right() <= area.width(), (a, area)
            for b in rects:
                if a < b:
                    assert not rects[a].intersects(rects[b]), (a, b, area)


def test_single_instance(qapp):
    from app.single_instance import SingleInstance

    first = SingleInstance("PixelDeskTest-" + str(time.time_ns()))
    assert not first.already_running()
    assert first.listen()
    second = SingleInstance(first.name)
    assert second.already_running()
    first.close()


def test_panel_click_opens_section_and_press_is_accepted(started_app, qapp):
    """A press on a panel must be accepted, otherwise the window would start a
    system move and the release (the click) would never reach the panel."""
    from PySide6.QtCore import QEvent, QPointF, Qt
    from PySide6.QtGui import QMouseEvent
    from PySide6.QtTest import QTest

    app, ctx = started_app()
    tile = app.shell.panels["tasks"]
    press = QMouseEvent(QEvent.Type.MouseButtonPress, QPointF(20, 20), QPointF(20, 20), Qt.MouseButton.LeftButton,
                        Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
    press.ignore()
    qapp.sendEvent(tile, press)
    assert press.isAccepted()
    opened = []
    ctx.signals.open_section.connect(opened.append)
    QTest.mouseClick(tile, Qt.MouseButton.LeftButton)
    assert opened == ["tasks"]
