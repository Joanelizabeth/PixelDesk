"""Typed access to persisted settings with change notification."""
from __future__ import annotations

import copy
import logging
from typing import Any, Callable

from database.repository import Repository

from .config import DEFAULT_SETTINGS

log = logging.getLogger(__name__)

Listener = Callable[[str, Any], None]


class SettingsStore:
    def __init__(self, repo: Repository):
        self._repo = repo
        self._values: dict[str, Any] = copy.deepcopy(DEFAULT_SETTINGS)
        stored = repo.load_settings()
        for key, value in stored.items():
            if key in DEFAULT_SETTINGS and isinstance(DEFAULT_SETTINGS[key], dict) and isinstance(value, dict):
                merged = copy.deepcopy(DEFAULT_SETTINGS[key])
                merged.update(value)
                self._values[key] = merged
            else:
                self._values[key] = value
        self._listeners: list[Listener] = []

    def get(self, key: str, default: Any = None) -> Any:
        if key in self._values:
            return copy.deepcopy(self._values[key])
        return copy.deepcopy(DEFAULT_SETTINGS.get(key, default))

    def __getitem__(self, key: str) -> Any:
        return self.get(key)

    def set(self, key: str, value: Any, notify: bool = True) -> None:
        if self._values.get(key) == value:
            return
        self._values[key] = copy.deepcopy(value)
        self._repo.save_setting(key, value)
        if notify:
            for listener in list(self._listeners):
                try:
                    listener(key, value)
                except Exception:  # pragma: no cover - listener bugs must not break saving
                    log.exception("Settings listener failed for %s", key)

    def set_transient(self, key: str, value: Any) -> None:
        """Change a value for this session only (not persisted, no notification)."""
        self._values[key] = copy.deepcopy(value)

    def update(self, values: dict[str, Any]) -> None:
        for key, value in values.items():
            self.set(key, value)

    def subscribe(self, listener: Listener) -> None:
        self._listeners.append(listener)

    def unsubscribe(self, listener: Listener) -> None:
        if listener in self._listeners:
            self._listeners.remove(listener)

    def as_dict(self) -> dict[str, Any]:
        return copy.deepcopy(self._values)
