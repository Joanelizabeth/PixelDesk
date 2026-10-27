"""Windows desktop-layer integration.

Two separate concerns live here:

1. *Wallpaper host* (experimental "live" background): asks Explorer (Progman,
   message 0x052C) to create the WorkerW window that sits between the
   wallpaper and the desktop icons, then parents a background window into it.
   A window there is *behind* the icons, so it can only be decorative: Windows
   routes all mouse input on the desktop to the icon view.  Pixel Desk only
   paints its gradient there.  Supports both the classic layout and the
   Windows 11 24H2+ layout (WorkerW as a child of Progman).

2. *Widget windows* are ordinary frameless tool windows that are pinned to the
   bottom of the z-order (above the icons, below every application) and owned
   by Progman so "Show desktop" does not hide them. Icons not covered by a
   widget remain fully visible and clickable.

All functions fail softly; callers fall back to normal window mode.
"""
from __future__ import annotations

import logging
from typing import Optional

from . import api

log = logging.getLogger(__name__)

SPAWN_WORKERW = 0x052C


def progman() -> Optional[int]:
    return api.find_window("Progman")


def find_wallpaper_host() -> Optional[int]:
    if not api.IS_WINDOWS:
        return None
    pm = progman()
    if not pm:
        log.warning("Progman window not found; desktop layer unavailable")
        return None
    # Ask Explorer to spawn the WorkerW behind the icons (harmless if it exists).
    api.send_message_timeout(pm, SPAWN_WORKERW, 0xD, 0x1)
    api.send_message_timeout(pm, SPAWN_WORKERW, 0, 0)

    # Classic layout: top-level WorkerW holding SHELLDLL_DefView; the wallpaper
    # WorkerW is the next top-level sibling.
    for hwnd in api.top_level_windows():
        if api.find_window("SHELLDLL_DefView", parent=hwnd, after=0):
            worker = api.find_window("WorkerW", parent=0, after=hwnd)
            if worker:
                return worker
    # Windows 11 24H2+: WorkerW is a child of Progman, below SHELLDLL_DefView.
    worker = api.find_window("WorkerW", parent=pm, after=0)
    if worker:
        return worker
    log.warning("No WorkerW wallpaper host found")
    return None


def attach_background(hwnd: int, rect: tuple[int, int, int, int]) -> Optional[int]:
    """Parent `hwnd` into the wallpaper host and size it to `rect` (physical
    pixels, virtual-screen coordinates). Returns the host on success."""
    host = find_wallpaper_host()
    if not host:
        return None
    api.set_child_style(hwnd, True)
    if not api.set_parent(hwnd, host) and api.get_parent(hwnd) != host:
        api.set_child_style(hwnd, False)
        return None
    ox, oy = api.virtual_screen_origin()
    x, y, w, h = rect
    api.move_window(hwnd, x - ox, y - oy, w, h)
    log.info("Background attached to desktop layer (host=%s)", host)
    return host


def detach_background(hwnd: int) -> None:
    api.set_parent(hwnd, None)
    api.set_child_style(hwnd, False)


def background_healthy(hwnd: int, host: Optional[int]) -> bool:
    return bool(host) and api.is_window(host) and api.is_window(hwnd) and api.get_parent(hwnd) == host


def icon_layer_window() -> Optional[int]:
    """The top-level window that currently hosts the desktop icons
    (SHELLDLL_DefView): Progman normally, or a WorkerW once a wallpaper layer
    has been spawned by Pixel Desk or another wallpaper tool."""
    pm = progman()
    if pm and api.find_window("SHELLDLL_DefView", parent=pm, after=0):
        return pm
    for hwnd in api.top_level_windows():
        if api.window_class(hwnd) == "WorkerW" and api.find_window("SHELLDLL_DefView", parent=hwnd, after=0):
            return hwnd
    return pm


def pin_widget_window(hwnd: int) -> None:
    """Keep a widget window above the icons but below applications.

    An owned window always stays above its owner, so owning it by the icon
    layer and then sending it to the bottom of the z-order places it directly
    above the icons and below every normal application window."""
    owner = icon_layer_window()
    if owner:
        api.set_owner(hwnd, owner)
    api.send_to_bottom(hwnd)
