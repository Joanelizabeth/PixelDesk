"""Focus/break timer.

Elapsed time is measured from a monotonic clock (not by counting ticks), so the
timer does not drift and is unaffected by wall-clock changes. Each session gets
a uid and is reported once, which prevents duplicate records.
"""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Callable, Optional

from PySide6.QtCore import QObject, QTimer, Signal

from app import clock

MIN_RECORD_SECONDS = 60  # cancelled sessions shorter than this are not stored


class Phase(str, Enum):
    FOCUS = "focus"
    BREAK = "break"


class TimerState(str, Enum):
    IDLE = "idle"
    RUNNING = "running"
    PAUSED = "paused"


@dataclass(frozen=True)
class SessionRecord:
    session_uid: str
    kind: str
    task_id: Optional[int]
    planned_seconds: int
    actual_seconds: int
    status: str  # completed | cancelled
    started_at: datetime
    ended_at: datetime


class FocusTimer:
    def __init__(self, focus_seconds: int = 25 * 60, break_seconds: int = 5 * 60,
                 monotonic: Callable[[], float] = time.monotonic,
                 wall: Callable[[], datetime] = clock.now):
        self.focus_seconds = int(focus_seconds)
        self.break_seconds = int(break_seconds)
        self._mono = monotonic
        self._wall = wall
        self.phase = Phase.FOCUS
        self.state = TimerState.IDLE
        self.task_id: Optional[int] = None
        self._uid: Optional[str] = None
        self._started_at: Optional[datetime] = None
        self._accumulated = 0.0
        self._run_start: Optional[float] = None
        self._reported: set[str] = set()

    # -- queries --------------------------------------------------------
    @property
    def planned(self) -> int:
        return self.focus_seconds if self.phase == Phase.FOCUS else self.break_seconds

    def elapsed(self) -> float:
        running = self._mono() - self._run_start if self.state == TimerState.RUNNING and self._run_start else 0.0
        return self._accumulated + running

    def remaining(self) -> float:
        if self.state == TimerState.IDLE:
            return float(self.planned)
        return max(0.0, self.planned - self.elapsed())

    def progress(self) -> float:
        return 0.0 if self.state == TimerState.IDLE else min(1.0, self.elapsed() / max(1, self.planned))

    # -- control --------------------------------------------------------
    def configure(self, focus_seconds: int, break_seconds: int) -> None:
        self.focus_seconds, self.break_seconds = int(focus_seconds), int(break_seconds)

    def start(self, task_id: Optional[int] = None) -> None:
        if self.state == TimerState.RUNNING:
            return
        if self.state == TimerState.PAUSED:
            self.resume()
            return
        self.task_id = task_id if self.phase == Phase.FOCUS else self.task_id
        self._uid = uuid.uuid4().hex
        self._started_at = self._wall()
        self._accumulated = 0.0
        self._run_start = self._mono()
        self.state = TimerState.RUNNING

    def pause(self) -> None:
        if self.state != TimerState.RUNNING:
            return
        self._accumulated += self._mono() - (self._run_start or self._mono())
        self._run_start = None
        self.state = TimerState.PAUSED

    def resume(self) -> None:
        if self.state != TimerState.PAUSED:
            return
        self._run_start = self._mono()
        self.state = TimerState.RUNNING

    def reset(self) -> Optional[SessionRecord]:
        """Cancel the current session. Partial focus time >= 1 minute is kept as
        a *cancelled* session (no completion credit). Returns to an idle focus phase."""
        record = None
        if self.state != TimerState.IDLE:
            elapsed = int(self.elapsed())
            if elapsed >= MIN_RECORD_SECONDS:
                record = self._make_record("cancelled", min(elapsed, self.planned))
        self._clear()
        self.phase = Phase.FOCUS
        return record

    def skip_break(self) -> Optional[SessionRecord]:
        if self.phase != Phase.BREAK:
            return None
        record = self.reset()
        return record

    def tick(self, auto_start_break: bool = False, auto_start_focus: bool = False) -> Optional[SessionRecord]:
        """Call regularly. Returns the completed record when a session ends."""
        if self.state != TimerState.RUNNING or self.elapsed() < self.planned:
            return None
        record = self._make_record("completed", self.planned)
        finished_phase = self.phase
        task = self.task_id
        self._clear()
        self.phase = Phase.BREAK if finished_phase == Phase.FOCUS else Phase.FOCUS
        if (self.phase == Phase.BREAK and auto_start_break) or (self.phase == Phase.FOCUS and auto_start_focus):
            self.start(task)
        else:
            self.task_id = task
        return record

    # -- internals ------------------------------------------------------
    def _make_record(self, status: str, actual: int) -> Optional[SessionRecord]:
        if self._uid is None or self._uid in self._reported:
            return None
        self._reported.add(self._uid)
        return SessionRecord(
            session_uid=self._uid, kind=self.phase.value, task_id=self.task_id,
            planned_seconds=self.planned, actual_seconds=int(actual), status=status,
            started_at=self._started_at or self._wall(), ended_at=self._wall(),
        )

    def _clear(self) -> None:
        self.state = TimerState.IDLE
        self._uid = None
        self._started_at = None
        self._accumulated = 0.0
        self._run_start = None


class FocusController(QObject):
    """Qt wrapper: drives FocusTimer with a QTimer and persists sessions."""

    changed = Signal()
    session_finished = Signal(object)  # SessionRecord (completed)
    session_cancelled = Signal(object)
    started = Signal()

    def __init__(self, repo, settings, progress, parent=None):
        super().__init__(parent)
        self.repo, self.settings, self.progress = repo, settings, progress
        self.timer = FocusTimer(settings["focus_minutes"] * 60, settings["break_minutes"] * 60)
        self._qt = QTimer(self)
        self._qt.setInterval(250)
        self._qt.timeout.connect(self._on_tick)
        self._qt.start()

    def apply_settings(self) -> None:
        if self.timer.state == TimerState.IDLE:
            self.timer.configure(self.settings["focus_minutes"] * 60, self.settings["break_minutes"] * 60)
            self.changed.emit()

    def start(self, task_id: Optional[int] = None) -> None:
        was_idle = self.timer.state == TimerState.IDLE
        self.timer.start(task_id)
        if was_idle:
            self.started.emit()
        self.changed.emit()

    def start_focus(self, task_id: Optional[int] = None) -> None:
        """Start a focus session (not a break) when the timer is idle."""
        if self.timer.state != TimerState.IDLE:
            return
        self.timer.phase = Phase.FOCUS
        self.apply_settings()
        self.start(task_id)

    def pause(self) -> None:
        self.timer.pause()
        self.changed.emit()

    def toggle(self, task_id: Optional[int] = None) -> None:
        if self.timer.state == TimerState.RUNNING:
            self.pause()
        else:
            self.start(task_id)

    def reset(self) -> None:
        record = self.timer.reset()
        if record:
            self._save(record)
            self.session_cancelled.emit(record)
        self.apply_settings()
        self.changed.emit()

    def set_task(self, task_id: Optional[int]) -> None:
        self.timer.task_id = task_id
        self.changed.emit()

    def _save(self, record: SessionRecord) -> bool:
        return self.repo.record_focus_session(
            session_uid=record.session_uid, kind=record.kind, task_id=record.task_id,
            planned_seconds=record.planned_seconds, actual_seconds=record.actual_seconds,
            status=record.status, started_at=record.started_at, ended_at=record.ended_at,
        )

    def _on_tick(self) -> None:
        if self.timer.state != TimerState.RUNNING:
            return
        record = self.timer.tick(self.settings["auto_start_breaks"], self.settings["auto_start_focus"])
        if record is not None:
            if self._save(record) and record.kind == "focus":
                self.progress.focus_completed(record.session_uid)
            if self.timer.state == TimerState.IDLE:
                self.apply_settings()
            self.session_finished.emit(record)
        self.changed.emit()

    def shutdown(self) -> None:
        """Called on exit: an unfinished session is stored as cancelled."""
        record = self.timer.reset()
        if record:
            self._save(record)
