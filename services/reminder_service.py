"""Water and movement reminder logic (pure Python, clock injected for tests).

Movement reminders are an *estimate* of uninterrupted desk time based on
computer activity and idle time. Pixel Desk cannot know whether someone is
physically sitting or walking, and never claims to.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, time, timedelta
from enum import Enum
from typing import Optional


def parse_hhmm(value: str, fallback: time = time(0, 0)) -> time:
    try:
        hh, mm = str(value).strip().split(":")
        return time(int(hh) % 24, int(mm) % 60)
    except (ValueError, AttributeError):
        return fallback


def in_quiet_hours(moment: time, start: time, end: time, enabled: bool = True) -> bool:
    """True if `moment` is inside [start, end). Handles windows across midnight."""
    if not enabled or start == end:
        return False
    if start < end:
        return start <= moment < end
    return moment >= start or moment < end


@dataclass
class QuietHours:
    enabled: bool = True
    start: time = time(22, 0)
    end: time = time(8, 0)

    def active(self, now: datetime) -> bool:
        return in_quiet_hours(now.time(), self.start, self.end, self.enabled)


# ======================================================================= water
@dataclass
class WaterConfig:
    enabled: bool = True
    interval_min: int = 60
    snooze_min: int = 15
    quiet: QuietHours = field(default_factory=QuietHours)


class WaterReminder:
    """Fires at most once per interval, never during quiet hours, never once the
    goal is reached. Logging water or snoozing pushes the next reminder back."""

    def __init__(self, config: WaterConfig, now: datetime):
        self.config = config
        self.next_due = now + timedelta(minutes=config.interval_min)

    def update_config(self, config: WaterConfig, now: datetime) -> None:
        interval_changed = config.interval_min != self.config.interval_min
        self.config = config
        if interval_changed:
            self.next_due = now + timedelta(minutes=config.interval_min)

    def on_logged(self, now: datetime) -> None:
        self.next_due = now + timedelta(minutes=self.config.interval_min)

    def snooze(self, now: datetime) -> None:
        self.next_due = now + timedelta(minutes=self.config.snooze_min)

    def check(self, now: datetime, goal_reached: bool) -> bool:
        if not self.config.enabled or goal_reached:
            return False
        if self.config.quiet.active(now):
            return False
        if now >= self.next_due:
            self.next_due = now + timedelta(minutes=self.config.interval_min)
            return True
        return False


# ======================================================================= movement
@dataclass
class MovementConfig:
    enabled: bool = True
    interval_min: int = 60
    break_min: int = 5
    snooze_min: int = 10
    idle_reset_min: int = 5
    quiet: QuietHours = field(default_factory=QuietHours)


class MovementState(str, Enum):
    TRACKING = "tracking"
    DUE = "due"
    ON_BREAK = "on_break"


class MovementTracker:
    #: Gaps between updates longer than this mean the machine slept / the app
    #: was not running; that time is treated as being away from the desk.
    MAX_UPDATE_GAP = 120.0

    def __init__(self, config: MovementConfig):
        self.config = config
        self.desk_seconds = 0.0
        self.state = MovementState.TRACKING
        self.snoozed_until: Optional[datetime] = None
        self.break_started_at: Optional[datetime] = None
        self.break_ends_at: Optional[datetime] = None
        self._last: Optional[datetime] = None

    @property
    def interval_seconds(self) -> float:
        return self.config.interval_min * 60.0

    @property
    def progress(self) -> float:
        return min(1.0, self.desk_seconds / max(1.0, self.interval_seconds))

    def update(self, now: datetime, idle_seconds: Optional[float], active: bool) -> list[str]:
        """Advance the estimate. Returns events: 'reminder_due', 'break_finished', 'reset'."""
        events: list[str] = []
        delta = 0.0
        if self._last is not None:
            delta = (now - self._last).total_seconds()
        self._last = now
        if delta < 0:
            delta = 0.0  # clock moved backwards
        elif delta > self.MAX_UPDATE_GAP:
            delta = 0.0
            if self.state != MovementState.ON_BREAK:
                self._reset_desk_time()
                events.append("reset")

        if self.state == MovementState.ON_BREAK:
            if self.break_ends_at is not None and now >= self.break_ends_at:
                self.state = MovementState.TRACKING
                self.break_started_at = self.break_ends_at = None
                self._reset_desk_time()
                events.append("break_finished")
            return events

        idle = idle_seconds or 0.0
        if idle >= self.config.idle_reset_min * 60:
            # The computer has been untouched for a break-length stretch.
            if self.desk_seconds > 0 or self.state == MovementState.DUE:
                events.append("reset")
            self._reset_desk_time()
            self.state = MovementState.TRACKING
            return events

        if active:
            self.desk_seconds += delta

        if (
            self.state == MovementState.TRACKING
            and self.config.enabled
            and self.desk_seconds >= self.interval_seconds
            and (self.snoozed_until is None or now >= self.snoozed_until)
            and not self.config.quiet.active(now)
        ):
            self.state = MovementState.DUE
            events.append("reminder_due")
        return events

    def _reset_desk_time(self) -> None:
        self.desk_seconds = 0.0
        self.snoozed_until = None

    def snooze(self, now: datetime) -> None:
        self.state = MovementState.TRACKING
        self.snoozed_until = now + timedelta(minutes=self.config.snooze_min)

    def dismiss(self, now: datetime) -> None:
        self.state = MovementState.TRACKING
        self._reset_desk_time()

    def start_break(self, now: datetime) -> None:
        self.state = MovementState.ON_BREAK
        self.break_started_at = now
        self.break_ends_at = now + timedelta(minutes=self.config.break_min)

    def cancel_break(self, now: datetime) -> None:
        """Ending a break early keeps the accumulated desk time but snoozes."""
        if self.state != MovementState.ON_BREAK:
            return
        self.state = MovementState.TRACKING
        self.break_started_at = self.break_ends_at = None
        self.snoozed_until = now + timedelta(minutes=self.config.snooze_min)

    def break_remaining(self, now: datetime) -> float:
        if self.state != MovementState.ON_BREAK or self.break_ends_at is None:
            return 0.0
        return max(0.0, (self.break_ends_at - now).total_seconds())
