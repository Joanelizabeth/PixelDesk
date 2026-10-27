"""Notifications: native Windows toasts via the tray icon when available, with an
in-app fallback (the companion's speech bubble / a small toast)."""
from __future__ import annotations

import logging
import math
import struct
import sys
import wave
from pathlib import Path
from typing import Optional

from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QApplication, QSystemTrayIcon

from app.config import cache_dir

log = logging.getLogger(__name__)


def _write_chime(path: Path) -> None:
    """Generate a soft two-note chime so no third-party audio is bundled."""
    rate = 22050
    frames = bytearray()
    for freq, dur in ((784.0, 0.12), (1046.5, 0.22)):
        n = int(rate * dur)
        for i in range(n):
            env = math.sin(math.pi * i / n) ** 2
            frames += struct.pack("<h", int(9000 * env * math.sin(2 * math.pi * freq * i / rate)))
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(bytes(frames))


class NotificationService(QObject):
    #: (title, message, action_key) - shown in-app by the shell
    in_app = Signal(str, str, str)

    def __init__(self, settings, parent=None):
        super().__init__(parent)
        self.settings = settings
        self.tray: Optional[QSystemTrayIcon] = None

    def attach_tray(self, tray: Optional[QSystemTrayIcon]) -> None:
        self.tray = tray

    def notify(self, title: str, message: str, action: str = "", native: bool = True) -> None:
        log.info("Notification: %s - %s", title, message)
        self.in_app.emit(title, message, action)
        if (
            native
            and self.settings["notifications_native"]
            and self.tray is not None
            and QSystemTrayIcon.supportsMessages()
            and self.tray.isVisible()
        ):
            self.tray.showMessage(title, message, QSystemTrayIcon.MessageIcon.Information, 8000)
        self.play_sound()

    def play_sound(self) -> None:
        if not self.settings["sounds_enabled"]:
            return
        try:
            if sys.platform == "win32":
                import winsound  # standard library, plays asynchronously

                path = cache_dir() / "chime.wav"
                if not path.exists():
                    _write_chime(path)
                winsound.PlaySound(str(path), winsound.SND_FILENAME | winsound.SND_ASYNC | winsound.SND_NODEFAULT)
            else:
                QApplication.beep()
        except Exception:  # pragma: no cover - audio devices vary
            log.debug("Sound playback unavailable", exc_info=True)
