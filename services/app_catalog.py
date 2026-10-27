"""Friendly names and *default* categories for common applications.

These are only starting points: every category is editable in Settings, and
browsers deliberately default to "other" rather than being assumed unproductive.
"""
from __future__ import annotations

import os
from typing import Optional

from winintegration import api

KNOWN_APPS: dict[str, tuple[str, str]] = {
    "code.exe": ("VS Code", "productive"),
    "pycharm64.exe": ("PyCharm", "productive"),
    "idea64.exe": ("IntelliJ IDEA", "productive"),
    "devenv.exe": ("Visual Studio", "productive"),
    "windowsterminal.exe": ("Windows Terminal", "productive"),
    "wt.exe": ("Windows Terminal", "productive"),
    "cmd.exe": ("Command Prompt", "productive"),
    "powershell.exe": ("PowerShell", "productive"),
    "pwsh.exe": ("PowerShell", "productive"),
    "notepad++.exe": ("Notepad++", "productive"),
    "sublime_text.exe": ("Sublime Text", "productive"),
    "winword.exe": ("Word", "productive"),
    "excel.exe": ("Excel", "productive"),
    "powerpnt.exe": ("PowerPoint", "productive"),
    "notion.exe": ("Notion", "productive"),
    "obsidian.exe": ("Obsidian", "learning"),
    "anki.exe": ("Anki", "learning"),
    "acrord32.exe": ("Acrobat Reader", "learning"),
    "sumatrapdf.exe": ("SumatraPDF", "learning"),
    "discord.exe": ("Discord", "communication"),
    "slack.exe": ("Slack", "communication"),
    "ms-teams.exe": ("Teams", "communication"),
    "teams.exe": ("Teams", "communication"),
    "outlook.exe": ("Outlook", "communication"),
    "olk.exe": ("Outlook", "communication"),
    "zoom.exe": ("Zoom", "communication"),
    "telegram.exe": ("Telegram", "communication"),
    "whatsapp.exe": ("WhatsApp", "communication"),
    "spotify.exe": ("Spotify", "entertainment"),
    "vlc.exe": ("VLC", "entertainment"),
    "steam.exe": ("Steam", "entertainment"),
    "steamwebhelper.exe": ("Steam", "entertainment"),
    "epicgameslauncher.exe": ("Epic Games", "entertainment"),
    "chrome.exe": ("Chrome", "other"),
    "msedge.exe": ("Edge", "other"),
    "firefox.exe": ("Firefox", "other"),
    "brave.exe": ("Brave", "other"),
    "opera.exe": ("Opera", "other"),
    "explorer.exe": ("File Explorer", "other"),
    "desktop": ("Desktop", "other"),
    "pixeldesk.exe": ("Pixel Desk", "other"),
    "unknown": ("Unknown app (access denied)", "other"),
}


def friendly_name(exe: str, exe_path: Optional[str]) -> str:
    known = KNOWN_APPS.get(exe)
    if known:
        return known[0]
    if exe_path:
        desc = api.file_description(exe_path)
        if desc:
            return desc[:60]
    stem = os.path.splitext(exe)[0]
    return stem.replace("_", " ").replace("-", " ").strip().title() or exe


def default_category(exe: str) -> str:
    known = KNOWN_APPS.get(exe)
    return known[1] if known else "other"
