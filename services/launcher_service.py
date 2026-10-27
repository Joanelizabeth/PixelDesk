"""Opens configured folders and applications safely.

* Paths are validated before use; missing items produce a friendly message.
* Nothing is executed through a shell, and labels are never interpreted.
* Files are never moved, renamed, deleted or scanned.
"""
from __future__ import annotations

import logging
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

log = logging.getLogger(__name__)

APP_SUFFIXES = {".exe", ".lnk", ".appref-ms", ".url"}
if sys.platform != "win32":  # development on other systems
    APP_SUFFIXES |= {".desktop", ".appimage", ""}


@dataclass(frozen=True)
class LaunchResult:
    ok: bool
    message: str = ""


def validate_entry(kind: str, path: str) -> Optional[str]:
    """Return an error message, or None if the entry can be opened."""
    if not path or not str(path).strip():
        return "No path is set for this item."
    if "\x00" in path:
        return "The path contains invalid characters."
    p = Path(os.path.expandvars(path)).expanduser()
    try:
        if not p.exists():
            return f"“{p}” no longer exists. You can edit or remove it in Settings."
        if kind == "folder" and not p.is_dir():
            return f"“{p}” is not a folder."
        if kind == "app":
            if p.is_dir():
                return "Choose an application or shortcut file, not a folder."
            if p.suffix.lower() not in APP_SUFFIXES:
                return f"“{p.name}” is not an application or shortcut (.exe, .lnk)."
    except OSError as exc:
        return f"Cannot access “{p}”: {exc.strerror or exc}"
    if kind not in ("folder", "app"):
        return f"Unknown item type “{kind}”."
    return None


def default_opener(path: str, kind: str) -> None:  # pragma: no cover - side effects
    if sys.platform == "win32":
        # ShellExecute "open": folders open in File Explorer, .lnk/.exe launch.
        # No shell string is constructed, so labels/paths cannot inject commands.
        os.startfile(path)  # type: ignore[attr-defined]
    elif kind == "folder" or path.endswith(".desktop"):
        opener = "open" if sys.platform == "darwin" else "xdg-open"
        subprocess.Popen([opener, path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    else:
        subprocess.Popen([path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


class LauncherService:
    def __init__(self, opener: Callable[[str, str], None] = default_opener):
        self._opener = opener

    def launch(self, kind: str, path: str) -> LaunchResult:
        error = validate_entry(kind, path)
        if error:
            return LaunchResult(False, error)
        resolved = str(Path(os.path.expandvars(path)).expanduser())
        try:
            self._opener(resolved, kind)
        except OSError as exc:
            log.warning("Launch failed for %s: %s", resolved, exc)
            return LaunchResult(False, f"Windows could not open “{Path(resolved).name}”: {exc.strerror or exc}")
        return LaunchResult(True)


def known_folder_defaults() -> list[tuple[str, str, str]]:
    """Common user folders that actually exist on this machine: (label, path, icon)."""
    home = Path.home()
    candidates = [
        ("Desktop", home / "Desktop", "star"),
        ("Documents", home / "Documents", "book"),
        ("Downloads", home / "Downloads", "download"),
        ("Pictures", home / "Pictures", "image"),
        ("Screenshots", home / "Pictures" / "Screenshots", "camera"),
        ("Music", home / "Music", "music"),
        ("Videos", home / "Videos", "game"),
    ]
    one_drive = os.environ.get("OneDrive")
    if one_drive:
        # Windows may redirect Desktop/Documents into OneDrive.
        od = Path(one_drive)
        candidates = [
            (label, (od / p.name) if not p.exists() and (od / p.name).exists() else p, icon)
            for label, p, icon in candidates
        ]
    return [(label, str(p), icon) for label, p, icon in candidates if p.is_dir()]
