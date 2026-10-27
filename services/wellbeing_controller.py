"""Qt glue for water and movement reminders."""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

from PySide6.QtCore import QObject, QTimer, Signal

from app import clock

from .activity_monitor import MonitorStatus
from .idle_detector import ActivityState
from .reminder_service import (
    MovementConfig, MovementState, MovementTracker, QuietHours, WaterConfig, WaterReminder, parse_hhmm,
)

log = logging.getLogger(__name__)


class WellbeingController(QObject):
    water_changed = Signal()
    water_reminder = Signal()
    water_goal_reached = Signal()
    movement_changed = Signal()
    movement_due = Signal()
    movement_break_finished = Signal()

    def __init__(self, repo, settings, progress, parent=None):
        super().__init__(parent)
        self.repo, self.settings, self.progress = repo, settings, progress
        now = clock.now()
        self.water = WaterReminder(self._water_config(), now)
        last = repo.last_water_time()
        if last and (now - last).total_seconds() >= 0:
            self.water.on_logged(last if last.date() == now.date() else now)
        self.movement = MovementTracker(self._movement_config())
        self.idle_available = False
        self._break_id: Optional[int] = None
        repo.close_dangling_breaks(now)

        self._timer = QTimer(self)
        self._timer.setInterval(15_000)
        self._timer.timeout.connect(self._check_water)
        self._timer.start()
        # Fallback clock for movement when the activity monitor is unavailable.
        self._move_timer = QTimer(self)
        self._move_timer.setInterval(5_000)
        self._move_timer.timeout.connect(self._fallback_movement_tick)
        self._move_timer.start()
        self._last_status_at: Optional[datetime] = None

    # -- configuration -----------------------------------------------------
    def _quiet(self) -> QuietHours:
        s = self.settings
        return QuietHours(s["quiet_hours_enabled"], parse_hhmm(s["quiet_start"]), parse_hhmm(s["quiet_end"]))

    def _water_config(self) -> WaterConfig:
        s = self.settings
        return WaterConfig(s["water_reminders"], int(s["water_interval_min"]), int(s["water_snooze_min"]),
                           self._quiet())

    def _movement_config(self) -> MovementConfig:
        s = self.settings
        return MovementConfig(s["movement_reminders"], int(s["movement_interval_min"]), int(s["movement_break_min"]),
                              int(s["movement_snooze_min"]), int(s["movement_idle_reset_min"]), self._quiet())

    def apply_settings(self) -> None:
        now = clock.now()
        self.water.update_config(self._water_config(), now)
        self.movement.config = self._movement_config()
        self.water_changed.emit()
        self.movement_changed.emit()

    # -- water -------------------------------------------------------------
    def water_status(self) -> dict:
        ml, servings = self.repo.water_total(clock.today())
        goal = int(self.settings["water_goal_servings"])
        serving = int(self.settings["water_serving_ml"])
        return {"ml": ml, "servings": servings, "goal": goal, "serving_ml": serving,
                "goal_ml": goal * serving, "reached": ml >= goal * serving}

    def log_water(self) -> None:
        before = self.water_status()["reached"]
        now = clock.now()
        self.repo.add_water(int(self.settings["water_serving_ml"]), now)
        self.water.on_logged(now)
        status = self.water_status()
        if status["reached"] and not before:
            self.progress.water_goal_reached(now.date(), now)
            self.water_goal_reached.emit()
        self.water_changed.emit()

    def undo_water(self) -> bool:
        ok = self.repo.undo_last_water(clock.today())
        if ok:
            self.water_changed.emit()
        return ok

    def snooze_water(self) -> None:
        self.water.snooze(clock.now())

    def _check_water(self) -> None:
        if self.water.check(clock.now(), self.water_status()["reached"]):
            self.water_reminder.emit()

    # -- movement ------------------------------------------------------------
    def on_monitor_status(self, status: MonitorStatus) -> None:
        self.idle_available = status.available and status.idle_seconds is not None
        if not status.available:
            return
        self._last_status_at = clock.now()
        active = status.state in (ActivityState.ACTIVE, ActivityState.PAUSED)
        idle = status.idle_seconds if status.state != ActivityState.LOCKED else float("inf")
        self._apply_movement_events(self.movement.update(self._last_status_at, idle, active))

    def _fallback_movement_tick(self) -> None:
        now = clock.now()
        if self._last_status_at and (now - self._last_status_at).total_seconds() < 10:
            return  # the monitor is feeding us
        # No idle information: estimate from time the app has been running.
        self._apply_movement_events(self.movement.update(now, None, True))

    def _apply_movement_events(self, events: list[str]) -> None:
        for event in events:
            if event == "reminder_due":
                self.movement_due.emit()
            elif event == "break_finished":
                if self._break_id is not None:
                    self.repo.finish_movement_break(self._break_id, True)
                    self.progress.movement_completed(self._break_id)
                    self._break_id = None
                self.movement_break_finished.emit()
        self.movement_changed.emit()

    def start_break(self) -> None:
        now = clock.now()
        self._break_id = self.repo.start_movement_break(
            int(self.settings["movement_break_min"]) * 60, int(self.movement.desk_seconds), now)
        self.movement.start_break(now)
        self.movement_changed.emit()

    def cancel_break(self) -> None:
        now = clock.now()
        if self._break_id is not None:
            self.repo.finish_movement_break(self._break_id, False, now)
            self._break_id = None
        self.movement.cancel_break(now)
        self.movement_changed.emit()

    def snooze_movement(self) -> None:
        self.movement.snooze(clock.now())
        self.movement_changed.emit()

    def dismiss_movement(self) -> None:
        self.movement.dismiss(clock.now())
        self.movement_changed.emit()

    @property
    def movement_state(self) -> MovementState:
        return self.movement.state

    def shutdown(self) -> None:
        if self._break_id is not None:
            self.repo.finish_movement_break(self._break_id, False)
