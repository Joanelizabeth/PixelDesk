"""Optional "Start with Windows" registration.

Uses a single per-user value under
  HKEY_CURRENT_USER\\Software\\Microsoft\\Windows\\CurrentVersion\\Run\\PixelDesk
No admin rights needed, nothing else is touched. To remove it manually: open
Task Manager > Startup apps and disable "PixelDesk", or delete that registry value.
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path

log = logging.getLogger(__name__)

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
VALUE_NAME = "PixelDesk"


def launch_command() -> str:
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}"'
    exe = Path(sys.executable)
    pythonw = exe.with_name("pythonw.exe")
    interpreter = pythonw if pythonw.exists() else exe
    main = Path(__file__).resolve().parent.parent / "main.py"
    return f'"{interpreter}" "{main}"'


class StartupService:
    def __init__(self, winreg_module=None):
        if winreg_module is None and sys.platform == "win32":
            import winreg as winreg_module  # type: ignore[no-redef]
        self._reg = winreg_module

    @property
    def supported(self) -> bool:
        return self._reg is not None

    def is_enabled(self) -> bool:
        if not self._reg:
            return False
        try:
            with self._reg.OpenKey(self._reg.HKEY_CURRENT_USER, RUN_KEY) as key:
                self._reg.QueryValueEx(key, VALUE_NAME)
                return True
        except OSError:
            return False

    def set_enabled(self, enabled: bool) -> tuple[bool, str]:
        if not self._reg:
            return False, "Start with Windows is only available on Windows."
        try:
            with self._reg.OpenKey(self._reg.HKEY_CURRENT_USER, RUN_KEY, 0, self._reg.KEY_SET_VALUE) as key:
                if enabled:
                    self._reg.SetValueEx(key, VALUE_NAME, 0, self._reg.REG_SZ, launch_command())
                else:
                    try:
                        self._reg.DeleteValue(key, VALUE_NAME)
                    except FileNotFoundError:
                        pass
            return True, ""
        except OSError as exc:
            log.warning("Could not update startup registration: %s", exc)
            return False, f"Could not update the startup setting: {exc}"
