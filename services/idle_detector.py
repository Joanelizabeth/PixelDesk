"""Idle-state classification on top of the platform probe's idle seconds."""
from __future__ import annotations

from enum import Enum
from typing import Optional


class ActivityState(str, Enum):
    ACTIVE = "active"
    IDLE = "idle"
    LOCKED = "locked"
    PAUSED = "paused"
    UNAVAILABLE = "unavailable"


class IdleDetector:
    def __init__(self, threshold_seconds: float = 300.0):
        self.threshold_seconds = float(threshold_seconds)

    def classify(self, idle_seconds: Optional[float], locked: bool, available: bool = True) -> ActivityState:
        if not available:
            return ActivityState.UNAVAILABLE
        if locked:
            return ActivityState.LOCKED
        if idle_seconds is not None and idle_seconds >= self.threshold_seconds:
            return ActivityState.IDLE
        return ActivityState.ACTIVE
