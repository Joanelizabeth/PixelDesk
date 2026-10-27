"""Application orchestrator: wires persistence, services, monitoring and UI."""
from __future__ import annotations

import logging
import sys
from datetime import timedelta
from pathlib import Path
from typing import Optional

from PySide6.QtCore import QObject, QProcess
from PySide6.QtWidgets import QApplication

from database.connection import Database, DatabaseError
from database.repository import Repository
from database.schema import migrate
from services.activity_monitor import ActivityMonitor, MonitorStatus
from services.focus_timer import FocusController
from services.launcher_service import LauncherService, known_folder_defaults
from services.notification_service import NotificationService
from services.startup_service import StartupService
from services.streak_service import ProgressService
from services.wellbeing_controller import WellbeingController
from winintegration.probe import ActivityProbe, create_probe

from . import clock
from .config import DEFAULT_HABITS, db_path
from .context import AppContext, AppSignals
from .settings_store import SettingsStore

log = logging.getLogger(__name__)


class PixelDeskApplication(QObject):
    def __init__(self, qapp: QApplication, probe: Optional[ActivityProbe] = None,
                 db_file: Optional[Path] = None, single_instance=None):
        super().__init__()
        self.qapp = qapp
        self._probe = probe
        self._db_file = Path(db_file) if db_file else db_path()
        self.instance = single_instance
        self.ctx: Optional[AppContext] = None
        self.shell = None
        self.monitor: Optional[ActivityMonitor] = None
        self._last_state = None
        self._stopped = False

    # ------------------------------------------------------------------ start
    def start(self) -> AppContext:
        from ui.desktop_shell import DesktopShell
        from ui.theme import stylesheet

        log.info("Starting Pixel Desk (data: %s)", self._db_file)
        self.db = Database(self._db_file)
        migrate(self.db)
        repo = Repository(self.db)
        settings = SettingsStore(repo)
        self._seed_first_run(repo, settings)
        self._apply_retention(repo, settings)

        progress = ProgressService(repo, xp_enabled=lambda: bool(settings["xp_enabled"]))
        signals = AppSignals()
        ctx = AppContext(
            repo=repo, settings=settings, progress=progress,
            focus=FocusController(repo, settings, progress),
            wellbeing=WellbeingController(repo, settings, progress),
            notifications=NotificationService(settings),
            launcher=LauncherService(), startup=StartupService(),
            signals=signals, app=self,
        )
        self.ctx = ctx
        self.qapp.setStyleSheet(stylesheet(ctx.theme))

        self.shell = DesktopShell(ctx)
        self.shell.rebuild()
        if self.instance is not None:
            self.instance.activated.connect(self.shell.show_all)

        probe = self._probe or create_probe()
        ctx.probe_available = probe.available
        self.monitor = ActivityMonitor(repo, probe, settings["idle_threshold_min"] * 60,
                                       recording=bool(settings["monitoring_enabled"]))
        self.monitor.status.connect(self._on_monitor_status)
        self.monitor.flushed.connect(lambda: signals.data_changed.emit("usage"))
        ctx.monitor = self.monitor
        self.monitor.start()

        wb = ctx.wellbeing
        wb.water_reminder.connect(lambda: self.remind(
            "Water break", "Time for a few sips of water?", "water", "water"))
        wb.movement_due.connect(lambda: self.remind(
            "Time to move",
            f"You've been active for about {settings['movement_interval_min']} minutes. "
            f"How about a {settings['movement_break_min']}-minute walk or stretch?", "movement", "movement"))
        wb.movement_break_finished.connect(lambda: (ctx.say("happy", "Welcome back! That break counts.", ""),
                                                    signals.data_changed.emit("movement")))
        wb.water_goal_reached.connect(lambda: ctx.say("achievement", "Water goal reached today - nice!", "water"))
        ctx.focus.session_finished.connect(self._on_session_finished)

        settings.subscribe(self._on_setting)
        self.qapp.aboutToQuit.connect(self.shutdown)
        # Windows sign-out/shutdown: save everything before the session ends.
        self.qapp.commitDataRequest.connect(lambda _manager: self.shutdown())

        if not settings["first_run_done"]:
            settings.set("first_run_done", True, notify=False)
            ctx.say("wave", "Hi, I'm Pip! Right-click the wheel's centre to add folders, and click my "
                            "bubble any time.", "settings:launcher")
        elif not probe.available:
            ctx.say("idle", "Screen-time monitoring isn't available on this system, so it's paused.", "screen_time")
        else:
            ctx.say("idle", self._welcome_back(), "tasks")
        return ctx

    def _welcome_back(self) -> str:
        parts = self.ctx.repo.tasks_for_day(clock.today())
        pending = len(parts["pending"])
        if pending:
            return f"Welcome back! {pending} task{'s' if pending != 1 else ''} on today's list."
        return "Welcome back! Want to plan a task or two?"

    def _seed_first_run(self, repo: Repository, settings: SettingsStore) -> None:
        if settings["first_run_done"]:
            return
        if not repo.list_launcher_items():
            for label, path, icon in known_folder_defaults():
                repo.add_launcher_item(label, "folder", path, icon)
        if not repo.list_habits(include_inactive=True):
            for name in DEFAULT_HABITS:
                repo.add_habit(name)

    def _apply_retention(self, repo: Repository, settings: SettingsStore) -> None:
        try:
            days = int(settings["usage_retention_days"])
            repo.purge_usage_before(clock.today() - timedelta(days=days))
        except Exception:  # pragma: no cover - never block startup on housekeeping
            log.exception("Retention purge failed")

    # ------------------------------------------------------------------ events
    def _on_monitor_status(self, status: MonitorStatus) -> None:
        if self._stopped:
            return  # a queued signal delivered after shutdown
        ctx = self.ctx
        ctx.monitor_status = status
        ctx.wellbeing.on_monitor_status(status)
        if status.state != self._last_state:
            self._last_state = status.state
            self.shell.on_monitor_status(status)

    def _on_session_finished(self, record) -> None:
        if record.kind == "focus":
            if self.ctx.settings["focus_notifications"]:
                self.shell.notify("Focus session complete", "Great work! Time for a short break.", "")
            self.check_achievements()
        elif self.ctx.settings["focus_notifications"]:
            self.shell.notify("Break finished", "Ready for another focus session?", "")

    def remind(self, title: str, message: str, state: str, action: str) -> None:
        self.ctx.say(state, message, action)
        self.shell.notify(title, message, action)

    def check_achievements(self) -> None:
        try:
            unlocked = self.ctx.progress.check_achievements(
                water_goal_met=self.ctx.wellbeing.water_status()["reached"])
        except Exception:
            log.exception("Achievement check failed")
            return
        for a in unlocked:
            self.ctx.say("achievement", f"Badge unlocked: {a.title}! {a.description}", "streaks")

    def _on_setting(self, key: str, value) -> None:
        ctx, shell = self.ctx, self.shell
        ctx.signals.settings_changed.emit(key)
        if key == "theme":
            from ui.theme import stylesheet

            self.qapp.setStyleSheet(stylesheet(ctx.theme))
            shell.apply_theme()
        elif key in ("background_brightness", "custom_background"):
            shell.request_background()
        elif key in ("widget_opacity", "character_hair", "character_outfit", "character_name", "user_name",
                     "greeting_messages", "animations_enabled", "reduced_motion", "xp_enabled"):
            for panel in shell.panels.values():
                panel.update()
            if key == "xp_enabled":
                shell.on_data_changed("xp")
        elif key in ("display_mode", "screen_index"):
            shell.rebuild()
        elif key == "desktop_background":
            shell.apply_background()
        elif key == "widgets_visible":
            shell.apply_visibility()
        elif key == "layout":
            shell.position_panels()
        elif key == "wheel_size":
            shell.panels["wheel"].apply_size()
            if shell.mode == "desktop" and "wheel" in shell.floating:
                shell.floating["wheel"].setFixedSize(shell.panels["wheel"].size())
            shell.position_panels()
        elif key == "monitoring_enabled":
            self.monitor.set_recording(bool(value))
            shell.panels["screen_time"].refresh()
            ctx.notify_changed("usage")
        elif key == "idle_threshold_min":
            self.monitor.set_idle_threshold(int(value) * 60)
        elif key in ("focus_minutes", "break_minutes"):
            ctx.focus.apply_settings()
        elif key.startswith(("water_", "movement_", "quiet_")):
            ctx.wellbeing.apply_settings()
            ctx.notify_changed("water")
            ctx.notify_changed("movement")

    # ------------------------------------------------------------------ backup
    def restore_backup(self, path: str) -> tuple[bool, str]:
        try:
            Database.validate_backup(path)
        except DatabaseError as exc:
            return False, str(exc)
        log.info("Restoring backup from %s", path)
        self.shutdown()
        try:
            Database.restore_file(path, self._db_file)
        except Exception as exc:  # pragma: no cover - filesystem errors
            log.exception("Restore failed")
            return False, f"Restore failed: {exc}. Please restart Pixel Desk."
        if self.instance is not None:
            self.instance.close()
        args = sys.argv[1:] if getattr(sys, "frozen", False) else sys.argv
        QProcess.startDetached(sys.executable, args)
        self.qapp.quit()
        return True, ""

    # ------------------------------------------------------------------ stop
    def shutdown(self) -> None:
        if self._stopped:
            return
        self._stopped = True
        log.info("Shutting down")
        try:
            if self.ctx is not None:
                self.ctx.focus.shutdown()
                self.ctx.wellbeing.shutdown()
        except Exception:
            log.exception("Error while saving timers")
        if self.monitor is not None:
            try:
                self.monitor.status.disconnect(self._on_monitor_status)
            except (RuntimeError, TypeError):
                pass
            self.monitor.stop()
        if self.shell is not None:
            self.shell.shutdown()
        try:
            if hasattr(self, "db"):
                self.db.close()
        except Exception:
            log.exception("Error closing database")
