"""Thin ctypes bindings to the Win32 functions Pixel Desk uses.

Everything here is a no-op / returns None on non-Windows platforms, so the rest
of the application can import it unconditionally. No keyboard hooks, window
titles, screenshots or content capture of any kind are used.
"""
from __future__ import annotations

import logging
import sys
from typing import Callable, Optional

log = logging.getLogger(__name__)
IS_WINDOWS = sys.platform == "win32"

if IS_WINDOWS:  # pragma: no cover - exercised only on Windows
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    try:
        version = ctypes.WinDLL("version", use_last_error=True)
    except OSError:
        version = None

    class LASTINPUTINFO(ctypes.Structure):
        _fields_ = [("cbSize", wintypes.UINT), ("dwTime", wintypes.DWORD)]

    class WINDOWPOS(ctypes.Structure):
        _fields_ = [
            ("hwnd", wintypes.HWND), ("hwndInsertAfter", wintypes.HWND),
            ("x", ctypes.c_int), ("y", ctypes.c_int), ("cx", ctypes.c_int), ("cy", ctypes.c_int),
            ("flags", wintypes.UINT),
        ]

    class MONITORINFOEXW(ctypes.Structure):
        _fields_ = [
            ("cbSize", wintypes.DWORD), ("rcMonitor", wintypes.RECT), ("rcWork", wintypes.RECT),
            ("dwFlags", wintypes.DWORD), ("szDevice", wintypes.WCHAR * 32),
        ]

    WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    MONITORENUMPROC = ctypes.WINFUNCTYPE(
        wintypes.BOOL, wintypes.HMONITOR, wintypes.HDC, ctypes.POINTER(wintypes.RECT), wintypes.LPARAM
    )

    user32.GetForegroundWindow.restype = wintypes.HWND
    user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    user32.GetWindowThreadProcessId.restype = wintypes.DWORD
    user32.GetLastInputInfo.argtypes = [ctypes.POINTER(LASTINPUTINFO)]
    user32.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    user32.FindWindowW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR]
    user32.FindWindowW.restype = wintypes.HWND
    user32.FindWindowExW.argtypes = [wintypes.HWND, wintypes.HWND, wintypes.LPCWSTR, wintypes.LPCWSTR]
    user32.FindWindowExW.restype = wintypes.HWND
    user32.SendMessageTimeoutW.argtypes = [
        wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM, wintypes.UINT, wintypes.UINT,
        ctypes.POINTER(ctypes.c_size_t),
    ]
    user32.EnumWindows.argtypes = [WNDENUMPROC, wintypes.LPARAM]
    user32.SetParent.argtypes = [wintypes.HWND, wintypes.HWND]
    user32.SetParent.restype = wintypes.HWND
    user32.GetParent.argtypes = [wintypes.HWND]
    user32.GetParent.restype = wintypes.HWND
    user32.IsWindow.argtypes = [wintypes.HWND]
    user32.SetWindowPos.argtypes = [
        wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, wintypes.UINT
    ]
    user32.OpenInputDesktop.restype = wintypes.HANDLE
    user32.CloseDesktop.argtypes = [wintypes.HANDLE]
    user32.GetUserObjectInformationW.argtypes = [
        wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(wintypes.DWORD)
    ]
    user32.SystemParametersInfoW.argtypes = [wintypes.UINT, wintypes.UINT, ctypes.c_void_p, wintypes.UINT]
    user32.EnumDisplayMonitors.argtypes = [wintypes.HDC, ctypes.c_void_p, MONITORENUMPROC, wintypes.LPARAM]
    user32.GetMonitorInfoW.argtypes = [wintypes.HMONITOR, ctypes.POINTER(MONITORINFOEXW)]
    user32.GetSystemMetrics.argtypes = [ctypes.c_int]
    if hasattr(user32, "SetWindowLongPtrW"):
        _SetWindowLongPtr = user32.SetWindowLongPtrW
        _GetWindowLongPtr = user32.GetWindowLongPtrW
    else:  # 32-bit Python
        _SetWindowLongPtr = user32.SetWindowLongW
        _GetWindowLongPtr = user32.GetWindowLongW
    _SetWindowLongPtr.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_ssize_t]
    _SetWindowLongPtr.restype = ctypes.c_ssize_t
    _GetWindowLongPtr.argtypes = [wintypes.HWND, ctypes.c_int]
    _GetWindowLongPtr.restype = ctypes.c_ssize_t

HWND_BOTTOM = 1
SWP_NOSIZE, SWP_NOMOVE, SWP_NOZORDER, SWP_NOACTIVATE, SWP_SHOWWINDOW = 0x1, 0x2, 0x4, 0x10, 0x40
WM_WINDOWPOSCHANGING = 0x0046
GWL_STYLE, GWLP_HWNDPARENT = -16, -8
WS_CHILD, WS_POPUP = 0x40000000, 0x80000000
SPI_GETDESKWALLPAPER, SPI_SETDESKWALLPAPER = 0x0073, 0x0014
SPIF_UPDATEINIFILE, SPIF_SENDCHANGE = 0x01, 0x02


def _safe(default=None):
    def wrap(fn: Callable):
        def inner(*args, **kwargs):
            if not IS_WINDOWS:
                return default
            try:
                return fn(*args, **kwargs)
            except Exception:  # pragma: no cover
                log.debug("Win32 call %s failed", fn.__name__, exc_info=True)
                return default
        inner.__name__ = fn.__name__
        return inner
    return wrap


@_safe()
def foreground_window() -> Optional[int]:
    hwnd = user32.GetForegroundWindow()
    return int(hwnd) if hwnd else None


@_safe()
def window_pid(hwnd: int) -> Optional[int]:
    pid = wintypes.DWORD(0)
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    return int(pid.value) or None


@_safe("")
def window_class(hwnd: int) -> str:
    buf = ctypes.create_unicode_buffer(256)
    user32.GetClassNameW(hwnd, buf, 256)
    return buf.value


@_safe()
def idle_seconds() -> Optional[float]:
    """Seconds since the last keyboard/mouse input (no content is read)."""
    info = LASTINPUTINFO()
    info.cbSize = ctypes.sizeof(LASTINPUTINFO)
    if not user32.GetLastInputInfo(ctypes.byref(info)):
        return None
    ticks = kernel32.GetTickCount() & 0xFFFFFFFF
    return ((ticks - info.dwTime) & 0xFFFFFFFF) / 1000.0


@_safe(False)
def workstation_locked() -> bool:
    DESKTOP_SWITCHDESKTOP = 0x0100
    UOI_NAME = 2
    handle = user32.OpenInputDesktop(0, False, DESKTOP_SWITCHDESKTOP)
    if not handle:
        return True  # the secure (Winlogon) desktop is active
    try:
        buf = ctypes.create_unicode_buffer(256)
        needed = wintypes.DWORD(0)
        if user32.GetUserObjectInformationW(handle, UOI_NAME, buf, ctypes.sizeof(buf), ctypes.byref(needed)):
            return buf.value.lower() != "default"
        return False
    finally:
        user32.CloseDesktop(handle)


@_safe()
def file_description(path: str) -> Optional[str]:
    """FileDescription from an executable's version resource (e.g. 'Visual Studio Code')."""
    if version is None:
        return None
    size = version.GetFileVersionInfoSizeW(path, None)
    if not size:
        return None
    data = ctypes.create_string_buffer(size)
    if not version.GetFileVersionInfoW(path, 0, size, data):
        return None
    ptr, length = ctypes.c_void_p(), wintypes.UINT()
    if not version.VerQueryValueW(data, "\\VarFileInfo\\Translation", ctypes.byref(ptr), ctypes.byref(length)):
        return None
    if length.value < 4:
        return None
    lang, codepage = ctypes.cast(ptr, ctypes.POINTER(ctypes.c_ushort * 2)).contents
    key = f"\\StringFileInfo\\{lang:04x}{codepage:04x}\\FileDescription"
    if not version.VerQueryValueW(data, key, ctypes.byref(ptr), ctypes.byref(length)) or not length.value:
        return None
    text = ctypes.wstring_at(ptr, length.value - 1).strip()
    return text or None


# ------------------------------------------------------------- window helpers
@_safe(False)
def is_window(hwnd: int) -> bool:
    return bool(user32.IsWindow(hwnd))


@_safe()
def find_window(class_name: str, parent: Optional[int] = None, after: Optional[int] = None) -> Optional[int]:
    if parent is None and after is None:
        hwnd = user32.FindWindowW(class_name, None)
    else:
        hwnd = user32.FindWindowExW(parent, after, class_name, None)
    return int(hwnd) if hwnd else None


@_safe()
def send_message_timeout(hwnd: int, msg: int, wparam: int, lparam: int, timeout_ms: int = 1000) -> Optional[int]:
    result = ctypes.c_size_t(0)
    user32.SendMessageTimeoutW(hwnd, msg, wparam, lparam, 0x0000, timeout_ms, ctypes.byref(result))
    return int(result.value)


@_safe([])
def top_level_windows() -> list[int]:
    found: list[int] = []

    def cb(hwnd, _lparam):
        found.append(int(hwnd))
        return True

    user32.EnumWindows(WNDENUMPROC(cb), 0)
    return found


@_safe()
def set_parent(child: int, parent: Optional[int]) -> Optional[int]:
    return user32.SetParent(child, parent)


@_safe()
def get_parent(hwnd: int) -> Optional[int]:
    p = user32.GetParent(hwnd)
    return int(p) if p else None


@_safe(False)
def set_child_style(hwnd: int, child: bool) -> bool:
    style = _GetWindowLongPtr(hwnd, GWL_STYLE)
    style = (style | WS_CHILD) & ~WS_POPUP if child else (style & ~WS_CHILD) | WS_POPUP
    _SetWindowLongPtr(hwnd, GWL_STYLE, style)
    return True


@_safe(False)
def set_owner(hwnd: int, owner: Optional[int]) -> bool:
    _SetWindowLongPtr(hwnd, GWLP_HWNDPARENT, owner or 0)
    return True


@_safe(False)
def move_window(hwnd: int, x: int, y: int, w: int, h: int) -> bool:
    return bool(user32.SetWindowPos(hwnd, None, x, y, w, h, SWP_NOZORDER | SWP_NOACTIVATE | SWP_SHOWWINDOW))


@_safe(False)
def send_to_bottom(hwnd: int) -> bool:
    return bool(user32.SetWindowPos(hwnd, HWND_BOTTOM, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE))


@_safe(False)
def force_bottom_in_windowpos(message_ptr: int) -> bool:
    """For WM_WINDOWPOSCHANGING: keep a widget window at the bottom of the z-order."""
    msg = wintypes.MSG.from_address(int(message_ptr))
    if msg.message != WM_WINDOWPOSCHANGING or not msg.lParam:
        return False
    pos = WINDOWPOS.from_address(msg.lParam)
    pos.hwndInsertAfter = HWND_BOTTOM
    pos.flags &= ~SWP_NOZORDER
    return True


@_safe({})
def monitor_rects() -> dict[str, tuple[int, int, int, int]]:
    """Physical-pixel rectangles keyed by device name (e.g. '\\\\.\\DISPLAY1')."""
    out: dict[str, tuple[int, int, int, int]] = {}

    def cb(hmon, _hdc, _rect, _lparam):
        info = MONITORINFOEXW()
        info.cbSize = ctypes.sizeof(MONITORINFOEXW)
        if user32.GetMonitorInfoW(hmon, ctypes.byref(info)):
            r = info.rcMonitor
            out[info.szDevice] = (r.left, r.top, r.right - r.left, r.bottom - r.top)
        return True

    user32.EnumDisplayMonitors(None, None, MONITORENUMPROC(cb), 0)
    return out


@_safe((0, 0))
def virtual_screen_origin() -> tuple[int, int]:
    return user32.GetSystemMetrics(76), user32.GetSystemMetrics(77)


# ------------------------------------------------------------- wallpaper
@_safe("")
def get_wallpaper() -> str:
    buf = ctypes.create_unicode_buffer(1024)
    user32.SystemParametersInfoW(SPI_GETDESKWALLPAPER, len(buf), buf, 0)
    return buf.value


@_safe(False)
def set_wallpaper(path: str) -> bool:
    return bool(user32.SystemParametersInfoW(
        SPI_SETDESKWALLPAPER, 0, ctypes.c_wchar_p(path), SPIF_UPDATEINIFILE | SPIF_SENDCHANGE))
