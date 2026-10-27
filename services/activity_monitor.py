"""Foreground-application screen-time monitoring.

Pipeline:  probe.sample()  ->  ActivityAggregator.tick()  ->  UsageRecorder  ->  SQLite

How time is classified
----------------------
* Each poll interval is attributed to the application that was in the
  foreground at the start of the interval.
* Time after the most recent keyboard/mouse input is held as *pending*. If
  input resumes before the idle threshold, it is counted as active (reading,
  watching a video). If the threshold is reached, the whole input-less stretch
  is reclassified as idle - so idle time is never reported as app usage.
* Locked sessions, sleep/suspend (detected as a gap between polls) and clock
  changes are excluded entirely.
* Every second is committed exactly once, so nothing is double counted.
"""
from __future__ import annotations

import logging
import threading
import time
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Iterator, Optional

from PySide6.QtCore import QThread, Signal

from winintegration.probe import ActivityProbe, Sample

from .app_catalog import default_category, friendly_name
from .idle_detector import ActivityState, IdleDetector

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class UsageDelta:
    day: str
    hour: int
    exe: Optional[str]
    kind: str  # "active" | "idle"
    seconds: float
    start_ts: float
    end_ts: float


def split_by_hour(start_ts: float, end_ts: float) -> Iterator[tuple[str, int, float, float, float]]:
    """Split [start, end) at local hour boundaries -> (day, hour, seconds, s, e)."""
    cursor = start_ts
    while cursor < end_ts:
        dt = datetime.fromtimestamp(cursor)
        boundary = (dt.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)).timestamp()
        if boundary <= cursor:  # defensive (DST oddities)
            boundary = cursor + 3600
        seg_end = min(end_ts, boundary)
        yield dt.date().isoformat(), dt.hour, seg_end - cursor, cursor, seg_end
        cursor = seg_end


class ActivityAggregator:
    def __init__(self, idle_threshold_s: float = 300.0, max_gap_s: float = 15.0):
        self.idle_threshold_s = float(idle_threshold_s)
        self.max_gap_s = float(max_gap_s)
        self._prev_ts: Optional[float] = None
        self._prev_sample: Optional[Sample] = None
        self._pending: list[list] = []  # [exe, start, end]
        self._last_input_ts: Optional[float] = None

    def reset(self) -> None:
        self._prev_ts = None
        self._prev_sample = None
        self._pending = []
        self._last_input_ts = None

    def _commit(self, exe: Optional[str], start: float, end: float, kind: str) -> list[UsageDelta]:
        if end <= start:
            return []
        return [UsageDelta(day, hour, exe if kind == "active" else None, kind, secs, s, e)
                for day, hour, secs, s, e in split_by_hour(start, end)]

    def _settle(self, cut: float, after_kind: Optional[str]) -> list[UsageDelta]:
        """Commit pending segments: the part before `cut` is active; the part after
        is committed as `after_kind` ('idle') or discarded (None) or kept ('keep')."""
        out: list[UsageDelta] = []
        keep: list[list] = []
        for exe, s, e in self._pending:
            if s < cut:
                out += self._commit(exe, s, min(e, cut), "active")
            if e > cut:
                rest_start = max(s, cut)
                if after_kind == "idle":
                    out += self._commit(exe, rest_start, e, "idle")
                elif after_kind == "keep":
                    keep.append([exe, rest_start, e])
        self._pending = keep
        return out

    def tick(self, now_ts: float, sample: Sample) -> list[UsageDelta]:
        if self._prev_ts is None or self._prev_sample is None:
            self._prev_ts, self._prev_sample = now_ts, sample
            if sample.idle_seconds is not None and not sample.locked:
                self._last_input_ts = now_ts - sample.idle_seconds
            return []

        prev_ts, prev = self._prev_ts, self._prev_sample
        self._prev_ts, self._prev_sample = now_ts, sample
        elapsed = now_ts - prev_ts

        # Sleep/suspend, a stalled process or a clock change: exclude the gap.
        if elapsed <= 0 or elapsed > self.max_gap_s:
            cut = self._last_input_ts if self._last_input_ts is not None else prev_ts
            out = self._settle(min(cut, prev_ts), None)
            self._last_input_ts = None if sample.idle_seconds is None else now_ts - sample.idle_seconds
            return out

        if sample.locked or prev.locked:
            cut = self._last_input_ts if self._last_input_ts is not None else prev_ts
            out = self._settle(min(cut, prev_ts), None)
            self._last_input_ts = None
            return out

        if prev.exe:
            self._pending.append([prev.exe, prev_ts, now_ts])

        idle = sample.idle_seconds
        if idle is None:  # idle detection unavailable: treat as active
            self._last_input_ts = now_ts
            return self._settle(now_ts, "keep")

        last_input = now_ts - idle
        self._last_input_ts = last_input
        if idle >= self.idle_threshold_s:
            return self._settle(last_input, "idle")
        return self._settle(last_input, "keep")

    def flush(self) -> list[UsageDelta]:
        """Commit everything pending as active (used on pause/shutdown, when the
        idle threshold has not been reached)."""
        out = self._settle(float("inf"), None)
        self._pending = []
        return out


class UsageRecorder:
    """Buffers deltas in memory and writes them in one transaction."""

    def __init__(self, repo):
        self.repo = repo
        self._lock = threading.Lock()
        self._deltas: list[UsageDelta] = []
        self._app_info: dict[str, Optional[str]] = {}

    def note_app(self, exe: str, exe_path: Optional[str]) -> None:
        if exe and exe not in self._app_info:
            self._app_info[exe] = exe_path

    def add(self, deltas: list[UsageDelta]) -> None:
        if deltas:
            with self._lock:
                self._deltas.extend(deltas)

    def flush(self) -> int:
        with self._lock:
            deltas, self._deltas = self._deltas, []
        if not deltas:
            return 0
        app_seconds: dict[tuple[str, str], float] = defaultdict(float)
        hourly: dict[tuple[str, int], list[float]] = defaultdict(lambda: [0.0, 0.0])
        daily: dict[str, list[float]] = defaultdict(lambda: [0.0, 0.0])
        observed: dict[str, list[str]] = {}
        for d in deltas:
            idx = 0 if d.kind == "active" else 1
            hourly[(d.day, d.hour)][idx] += d.seconds
            daily[d.day][idx] += d.seconds
            if d.kind == "active" and d.exe:
                app_seconds[(d.day, d.exe)] += d.seconds
            first = datetime.fromtimestamp(d.start_ts).astimezone().isoformat(timespec="seconds")
            last = datetime.fromtimestamp(d.end_ts).astimezone().isoformat(timespec="seconds")
            if d.day not in observed:
                observed[d.day] = [first, last]
            else:
                observed[d.day][0] = min(observed[d.day][0], first)
                observed[d.day][1] = max(observed[d.day][1], last)
        try:
            for (_, exe) in app_seconds:
                if not self.repo.app_known(exe):
                    path = self._app_info.get(exe)
                    self.repo.ensure_app(exe, friendly_name(exe, path), path, default_category(exe))
            self.repo.apply_usage(
                dict(app_seconds),
                {k: (v[0], v[1]) for k, v in hourly.items()},
                {k: (v[0], v[1]) for k, v in daily.items()},
                {k: (v[0], v[1]) for k, v in observed.items()},
            )
        except Exception:
            log.exception("Failed to write usage; keeping data for the next attempt")
            with self._lock:
                self._deltas = deltas + self._deltas
            return 0
        return len(deltas)


@dataclass(frozen=True)
class MonitorStatus:
    state: ActivityState
    exe: Optional[str]
    idle_seconds: Optional[float]
    available: bool
    recording: bool


class ActivityMonitor(QThread):
    """Polls the probe off the UI thread; communicates only through signals."""

    status = Signal(object)  # MonitorStatus
    flushed = Signal()

    def __init__(self, repo, probe: ActivityProbe, idle_threshold_s: float = 300.0,
                 recording: bool = True, poll_interval: float = 1.0, flush_interval: float = 30.0,
                 parent=None):
        super().__init__(parent)
        self.probe = probe
        self.poll_interval = poll_interval
        self.flush_interval = flush_interval
        self.aggregator = ActivityAggregator(idle_threshold_s, max_gap_s=max(15.0, poll_interval * 10))
        self.detector = IdleDetector(idle_threshold_s)
        self.recorder = UsageRecorder(repo)
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._recording = recording
        self._pending_threshold: Optional[float] = None
        self._consecutive_errors = 0

    # -- called from the UI thread ---------------------------------------
    def set_recording(self, enabled: bool) -> None:
        with self._lock:
            self._recording = enabled

    def set_idle_threshold(self, seconds: float) -> None:
        with self._lock:
            self._pending_threshold = float(seconds)

    def stop(self) -> None:
        self._stop.set()
        self.wait(5000)

    # -- worker thread --------------------------------------------------
    def run(self) -> None:  # noqa: C901 - straightforward loop
        last_flush = time.monotonic()
        was_recording = False
        while not self._stop.is_set():
            with self._lock:
                recording = self._recording
                threshold = self._pending_threshold
                self._pending_threshold = None
            if threshold is not None:
                self.aggregator.idle_threshold_s = threshold
                self.detector.threshold_seconds = threshold

            try:
                sample = self.probe.sample()
                self._consecutive_errors = 0
            except Exception:
                self._consecutive_errors += 1
                if self._consecutive_errors in (1, 60):
                    log.exception("Activity probe failed")
                sample = Sample(None, None, None, None, False)

            available = self.probe.available and self._consecutive_errors == 0
            if recording and available:
                if sample.exe:
                    self.recorder.note_app(sample.exe, sample.exe_path)
                self.recorder.add(self.aggregator.tick(time.time(), sample))
            elif was_recording:
                self.recorder.add(self.aggregator.flush())
                self.aggregator.reset()
            was_recording = recording and available

            state = self.detector.classify(sample.idle_seconds, sample.locked, available)
            if not recording and available:
                state = ActivityState.PAUSED
            self.status.emit(MonitorStatus(state, sample.exe, sample.idle_seconds, available, recording))

            if time.monotonic() - last_flush >= self.flush_interval:
                if self.recorder.flush():
                    self.flushed.emit()
                last_flush = time.monotonic()
            self._stop.wait(self.poll_interval)

        # Shutdown: commit pending time and write everything.
        self.recorder.add(self.aggregator.flush())
        self.recorder.flush()
