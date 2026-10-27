"""Paths, constants and default settings for Pixel Desk.

User data always lives outside the source tree / install directory:
  Windows: %LOCALAPPDATA%\\PixelDesk\\
  Other:   $XDG_DATA_HOME/PixelDesk (development only)
The PIXELDESK_DATA_DIR environment variable overrides the location (used by tests).
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

APP_NAME = "PixelDesk"
APP_DISPLAY_NAME = "Pixel Desk"
APP_VERSION = "1.0.0"
IS_WINDOWS = sys.platform == "win32"

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def data_dir() -> Path:
    override = os.environ.get("PIXELDESK_DATA_DIR")
    if override:
        path = Path(override)
    elif IS_WINDOWS:
        base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
        path = Path(base) / APP_NAME
    else:
        base = os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local" / "share")
        path = Path(base) / APP_NAME
    path.mkdir(parents=True, exist_ok=True)
    return path


def db_path() -> Path:
    return data_dir() / "pixeldesk.db"


def log_dir() -> Path:
    path = data_dir() / "logs"
    path.mkdir(parents=True, exist_ok=True)
    return path


def backup_dir() -> Path:
    path = data_dir() / "backups"
    path.mkdir(parents=True, exist_ok=True)
    return path


def cache_dir() -> Path:
    path = data_dir() / "cache"
    path.mkdir(parents=True, exist_ok=True)
    return path


def resource_path(relative: str) -> Path:
    """Resolve bundled resources both from source and from a PyInstaller build."""
    base = Path(getattr(sys, "_MEIPASS", PROJECT_ROOT))
    return base / relative


APP_CATEGORIES = ("productive", "learning", "communication", "entertainment", "other")

PANEL_IDS = ("wheel", "clock", "character", "tasks", "water", "movement", "screen_time")

# Top-left corner of each panel as a fraction of the available area.
DEFAULT_LAYOUT = {
    "wheel": [0.04, 0.12],
    "clock": [0.70, 0.07],
    "character": [0.70, 0.27],
    "tasks": [0.62, 0.74],
    "water": [0.80, 0.74],
    "movement": [0.62, 0.86],
    "screen_time": [0.80, 0.86],
}

DEFAULT_SETTINGS: dict = {
    # General
    "user_name": "",
    "greeting_messages": [
        "Small steps, big future.",
        "One thing at a time.",
        "Progress, not perfection.",
        "Be kind to future you.",
        "Slow is smooth, smooth is fast.",
    ],
    "display_mode": "desktop" if IS_WINDOWS else "window",  # "desktop" | "window"
    "desktop_background": "none",  # "none" | "wallpaper" | "live"
    "saved_wallpaper": "",
    "screen_index": 0,
    "start_with_windows": False,
    "first_run_done": False,
    # Appearance
    "theme": "dark_purple",
    "background_brightness": 1.0,
    "widget_opacity": 0.9,
    "custom_background": "",
    "reduced_motion": False,
    "animations_enabled": True,
    "sounds_enabled": False,
    "character_messages": True,
    "character_name": "Pip",
    "character_hair": "#c99ad6",
    "character_outfit": "#8f9fd9",
    "wheel_size": "medium",  # small | medium | large
    "widgets_visible": {pid: True for pid in PANEL_IDS},
    "layout": {},
    "window_geometry": None,
    # Focus
    "focus_minutes": 25,
    "break_minutes": 5,
    "auto_start_breaks": True,
    "auto_start_focus": False,
    "focus_notifications": True,
    "focus_celebration": True,
    # Wellbeing
    "quiet_hours_enabled": True,
    "quiet_start": "22:00",
    "quiet_end": "08:00",
    "water_goal_servings": 8,
    "water_serving_ml": 250,
    "water_reminders": True,
    "water_interval_min": 60,
    "water_snooze_min": 15,
    "movement_reminders": True,
    "movement_interval_min": 60,
    "movement_break_min": 5,
    "movement_snooze_min": 10,
    "movement_idle_reset_min": 5,
    # Screen time
    "monitoring_enabled": True,
    "idle_threshold_min": 5,
    "usage_retention_days": 180,
    # Notifications & gamification
    "notifications_native": True,
    "xp_enabled": True,
}

# Suggested launcher labels offered in the "Add folder" dialog. They are only
# suggestions; nothing is created or assumed about the user's real folders.
SUGGESTED_LAUNCHER_LABELS = [
    "College", "Projects", "Python", "Notes", "Resources", "Personal",
    "Screenshots", "FITQUEST", "Downloads", "Documents",
]

DEFAULT_HABITS = ["Coding", "DSA", "Exercise", "Reading"]
