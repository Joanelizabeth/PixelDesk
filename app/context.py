"""Shared application context handed to UI components."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from PySide6.QtCore import QObject, Signal


class AppSignals(QObject):
    #: area: "tasks" | "habits" | "water" | "movement" | "usage" | "launcher" | "focus" | "xp" | "all"
    data_changed = Signal(str)
    theme_changed = Signal()
    settings_changed = Signal(str)
    #: (state, message, action_key) for the companion
    companion = Signal(str, str, str)
    #: open a detail section: "tasks" | "water" | "movement" | "screen_time" | "streaks" | "settings:<tab>"
    open_section = Signal(str)
    layout_edit_changed = Signal(bool)


@dataclass
class AppContext:
    repo: Any
    settings: Any
    progress: Any
    focus: Any
    wellbeing: Any
    notifications: Any
    launcher: Any
    startup: Any
    signals: AppSignals
    monitor: Any = None
    monitor_status: Any = None
    probe_available: bool = False
    app: Any = None  # PixelDeskApplication
    extras: dict = field(default_factory=dict)

    @property
    def theme(self):
        from ui.theme import get_theme

        return get_theme(self.settings["theme"])

    def notify_changed(self, area: str) -> None:
        self.signals.data_changed.emit(area)

    def say(self, state: str, message: str, action: str = "") -> None:
        self.signals.companion.emit(state, message, action)

    def current_monitor_state(self) -> Optional[str]:
        st = self.monitor_status
        return st.state.value if st is not None else None
