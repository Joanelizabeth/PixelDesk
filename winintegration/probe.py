"""Activity probe: which application is in the foreground, how long the user
has been idle, and whether the session is locked.

Only the process executable name/path is read. Window titles, keystrokes,
screen contents and browser pages are never collected.
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Optional, Protocol

from . import api

log = logging.getLogger(__name__)

LOCK_SCREEN_EXES = {"lockapp.exe", "logonui.exe"}


@dataclass(frozen=True)
class Sample:
    exe: Optional[str]          # normalised lower-case executable name, e.g. "code.exe"
    exe_path: Optional[str]
    pid: Optional[int]
    idle_seconds: Optional[float]  # None = idle detection unavailable
    locked: bool = False


class ActivityProbe(Protocol):
    available: bool

    def sample(self) -> Sample: ...


class UnavailableProbe:
    """Used on non-Windows systems or when Win32 calls fail."""

    available = False

    def sample(self) -> Sample:
        return Sample(None, None, None, None, False)


class WindowsProbe:  # pragma: no cover - requires Windows
    available = True

    def __init__(self) -> None:
        import psutil  # imported lazily so tests don't need it

        self._psutil = psutil
        self._cache: dict[int, tuple[float, str, Optional[str]]] = {}

    def _process(self, pid: int) -> tuple[Optional[str], Optional[str]]:
        try:
            proc = self._psutil.Process(pid)
            created = proc.create_time()
            cached = self._cache.get(pid)
            if cached and cached[0] == created:
                return cached[1], cached[2]
            name = proc.name()
            try:
                path = proc.exe()
            except (self._psutil.AccessDenied, OSError):
                path = None
            if len(self._cache) > 256:
                self._cache.clear()
            self._cache[pid] = (created, name.lower(), path)
            return name.lower(), path
        except self._psutil.AccessDenied:
            return "unknown", None  # e.g. an elevated process: still count the time
        except (self._psutil.NoSuchProcess, OSError):
            return None, None

    def sample(self) -> Sample:
        idle = api.idle_seconds()
        locked = api.workstation_locked()
        hwnd = api.foreground_window()
        exe = path = None
        pid = None
        if hwnd and not locked:
            pid = api.window_pid(hwnd)
            if pid:
                exe, path = self._process(pid)
                if exe == "explorer.exe" and api.window_class(hwnd) in ("Progman", "WorkerW"):
                    exe, path = "desktop", None
        if exe in LOCK_SCREEN_EXES:
            locked, exe, path = True, None, None
        return Sample(exe, path, pid, idle, locked)


def create_probe() -> ActivityProbe:
    if api.IS_WINDOWS:
        try:
            return WindowsProbe()
        except Exception:  # pragma: no cover
            log.exception("Windows activity probe unavailable")
    return UnavailableProbe()


def exe_stem(exe: str) -> str:
    return os.path.splitext(exe)[0]
