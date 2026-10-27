"""Hosts the panels in one of two modes and owns the tray icon and dialogs.

Desktop companion mode
    Each panel lives in its own small frameless tool window that is pinned to
    the bottom of the z-order (above the desktop icons, below all apps) and
    owned by Progman so "Show desktop" keeps it visible. Desktop icons outside
    the widgets stay visible and clickable. The background can optionally be
    applied as the Windows wallpaper, or (experimental) painted in the WorkerW
    layer behind the icons.

Window mode
    The same panels on the painted background inside one frameless,
    resizable window. Used everywhere desktop integration isn't available.
"""
from __future__ import annotations

import logging
from typing import Optional

from PySide6.QtCore import QObject, QPoint, QRect, QSize, Qt, QTimer
from PySide6.QtGui import QAction, QFont, QGuiApplication, QMouseEvent, QPainter, QScreen
from PySide6.QtWidgets import (
    QApplication, QHBoxLayout, QLabel, QMenu, QPushButton, QSystemTrayIcon, QVBoxLayout, QWidget,
)

from app import clock
from app.config import IS_WINDOWS, cache_dir
from app.context import AppContext
from winintegration import api, desktop_layer

from .background import render_background
from .character_panel import CharacterPanel
from .clock_widget import ClockPanel
from .movement_widget import MovementCompact, MovementDialog
from .panel import Panel
from .pixel_art import app_icon
from .radial_wheel import RadialWheel
from .screen_time_widget import ScreenTimeCompact, ScreenTimeDialog
from .settings_dialog import SettingsDialog
from .streak_widget import StreaksDialog
from .task_widget import TasksCompact, TasksDialog
from .theme import stylesheet, ui_font
from .water_widget import WaterCompact, WaterDialog

log = logging.getLogger(__name__)

GAP = 12


def default_positions(area: QSize, sizes: dict[str, QSize]) -> dict[str, QPoint]:
    """Sparse default composition anchored to the edges of the area."""
    w, h = area.width(), area.height()
    m = max(24, int(w * 0.045))
    out: dict[str, QPoint] = {}
    clock_s, char_s, tile = sizes["clock"], sizes["character"], sizes["tasks"]
    out["clock"] = QPoint(w - m - clock_s.width(), max(16, int(h * 0.06)))
    char_y = out["clock"].y() + clock_s.height() + GAP
    out["character"] = QPoint(w - m - char_s.width(), char_y)
    grid_w = tile.width() * 2 + GAP
    grid_h = tile.height() * 2 + GAP
    gx = out["character"].x() - 2 * GAP - grid_w
    gy = char_y + char_s.height() - grid_h
    out["tasks"] = QPoint(gx, gy)
    out["water"] = QPoint(gx + tile.width() + GAP, gy)
    out["movement"] = QPoint(gx, gy + tile.height() + GAP)
    out["screen_time"] = QPoint(gx + tile.width() + GAP, gy + tile.height() + GAP)
    ws = sizes["wheel"]
    out["wheel"] = QPoint(max(m, int(w * 0.05)), max(16, (h - ws.height()) // 2))
    return out


# ============================================================== window mode
class DashboardWindow(QWidget):
    EDGE = 8

    def __init__(self, shell: "DesktopShell"):
        super().__init__(None, Qt.WindowType.Window | Qt.WindowType.FramelessWindowHint)
        self.shell = shell
        self.ctx = shell.ctx
        self.setWindowTitle("Pixel Desk")
        self.setWindowIcon(app_icon())
        self.setMinimumSize(900, 620)
        self.setMouseTracking(True)
        self._bar = QWidget(self)
        bar = QHBoxLayout(self._bar)
        bar.setContentsMargins(0, 0, 0, 0)
        bar.setSpacing(6)
        self.title = QLabel("PIXEL DESK")
        self.title.setFont(ui_font(8.5))
        self.title.setProperty("role", "dim")
        bar.addWidget(self.title)
        bar.addStretch(1)
        self.buttons = {}
        for key, text, tip in (("edit", "Edit layout", "Drag widgets to rearrange them"),
                               ("settings", "Settings", "Open settings"),
                               ("min", "–", "Minimise"), ("close", "×", "Hide to the tray (or quit if there is no tray)")):
            b = QPushButton(text)
            b.setProperty("flat", "true")
            b.setToolTip(tip)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            bar.addWidget(b)
            self.buttons[key] = b
        self.buttons["edit"].clicked.connect(lambda: shell.set_edit_mode(not shell.edit_mode))
        self.buttons["settings"].clicked.connect(lambda: shell.open_section("settings"))
        self.buttons["min"].clicked.connect(self.showMinimized)
        self.buttons["close"].clicked.connect(shell.close_window)
        self.apply_theme()

    def apply_theme(self) -> None:
        self.setStyleSheet(stylesheet(self.ctx.theme))
        self.update()

    def resizeEvent(self, e) -> None:  # noqa: N802
        self._bar.setGeometry(16, 8, self.width() - 32, 30)
        self._bar.raise_()
        self.shell.position_panels()
        super().resizeEvent(e)

    def paintEvent(self, _e) -> None:  # noqa: N802
        p = QPainter(self)
        s = self.ctx.settings
        p.drawPixmap(0, 0, render_background(self.size(), self.ctx.theme, float(s["background_brightness"]),
                                             s["custom_background"]))

    def _edges(self, pos: QPoint) -> Qt.Edge:
        edges = Qt.Edge(0)
        if pos.x() <= self.EDGE:
            edges |= Qt.Edge.LeftEdge
        if pos.x() >= self.width() - self.EDGE:
            edges |= Qt.Edge.RightEdge
        if pos.y() <= self.EDGE:
            edges |= Qt.Edge.TopEdge
        if pos.y() >= self.height() - self.EDGE:
            edges |= Qt.Edge.BottomEdge
        return edges

    def mouseMoveEvent(self, e: QMouseEvent) -> None:  # noqa: N802
        edges = self._edges(e.position().toPoint())
        if edges in (Qt.Edge.LeftEdge | Qt.Edge.TopEdge, Qt.Edge.RightEdge | Qt.Edge.BottomEdge):
            self.setCursor(Qt.CursorShape.SizeFDiagCursor)
        elif edges in (Qt.Edge.RightEdge | Qt.Edge.TopEdge, Qt.Edge.LeftEdge | Qt.Edge.BottomEdge):
            self.setCursor(Qt.CursorShape.SizeBDiagCursor)
        elif edges & (Qt.Edge.LeftEdge | Qt.Edge.RightEdge):
            self.setCursor(Qt.CursorShape.SizeHorCursor)
        elif edges & (Qt.Edge.TopEdge | Qt.Edge.BottomEdge):
            self.setCursor(Qt.CursorShape.SizeVerCursor)
        else:
            self.setCursor(Qt.CursorShape.ArrowCursor)

    def mousePressEvent(self, e: QMouseEvent) -> None:  # noqa: N802
        if e.button() != Qt.MouseButton.LeftButton or self.windowHandle() is None:
            return
        edges = self._edges(e.position().toPoint())
        if edges:
            self.windowHandle().startSystemResize(edges)
        else:
            self.windowHandle().startSystemMove()

    def mouseDoubleClickEvent(self, _e) -> None:  # noqa: N802
        self.showNormal() if self.isMaximized() else self.showMaximized()

    def closeEvent(self, e) -> None:  # noqa: N802
        self.shell.save_window_geometry()
        if self.shell.tray is not None and not self.shell.quitting:
            e.ignore()
            self.hide()
        else:
            e.accept()
            QApplication.instance().quit()


# ============================================================== desktop mode
class FloatingWindow(QWidget):
    """Frameless, translucent, bottom-pinned window holding one panel."""

    def __init__(self, panel: Panel):
        flags = Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnBottomHint
        super().__init__(None, flags)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setProperty("pixeldesk_floating", True)
        self.setWindowTitle(f"Pixel Desk - {panel.panel_id}")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(panel)
        self.panel = panel
        self.setFixedSize(panel.size())

    def showEvent(self, e) -> None:  # noqa: N802
        super().showEvent(e)
        if IS_WINDOWS:
            desktop_layer.pin_widget_window(int(self.winId()))

    def nativeEvent(self, event_type, message):  # noqa: N802
        if IS_WINDOWS and bytes(event_type) == b"windows_generic_MSG":
            try:
                api.force_bottom_in_windowpos(int(message))
            except Exception:  # pragma: no cover
                pass
        return False, 0


class BackgroundLayer(QWidget):
    """Experimental: painted into the WorkerW layer behind desktop icons."""

    def __init__(self, ctx: AppContext, screen: QScreen):
        super().__init__(None, Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint)
        self.ctx = ctx
        self.screen_ref = screen
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.host: Optional[int] = None
        self.setGeometry(screen.geometry())

    def attach(self) -> bool:
        self.show()
        rect = api.monitor_rects().get(self.screen_ref.name())
        if rect is None:
            g = self.screen_ref.geometry()
            dpr = self.screen_ref.devicePixelRatio()
            rect = (int(g.x() * dpr), int(g.y() * dpr), int(g.width() * dpr), int(g.height() * dpr))
        self.host = desktop_layer.attach_background(int(self.winId()), rect)
        if not self.host:
            self.hide()
        return bool(self.host)

    def healthy(self) -> bool:
        return desktop_layer.background_healthy(int(self.winId()), self.host)

    def paintEvent(self, _e) -> None:  # noqa: N802
        p = QPainter(self)
        s = self.ctx.settings
        p.drawPixmap(self.rect(), render_background(self.size(), self.ctx.theme, float(s["background_brightness"]),
                                                    s["custom_background"]))


class EditBanner(QWidget):
    def __init__(self, shell: "DesktopShell"):
        super().__init__(None, Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint |
                         Qt.WindowType.WindowStaysOnTopHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setStyleSheet(stylesheet(shell.ctx.theme))
        lay = QHBoxLayout(self)
        lay.setContentsMargins(14, 8, 8, 8)
        lab = QLabel("Drag widgets to arrange them.")
        reset = QPushButton("Reset layout")
        reset.clicked.connect(lambda: shell.ctx.settings.set("layout", {}))
        done = QPushButton("Done")
        done.setProperty("accent", "true")
        done.clicked.connect(lambda: shell.set_edit_mode(False))
        lay.addWidget(lab)
        lay.addWidget(reset)
        lay.addWidget(done)
        self.ctx = shell.ctx
        self.adjustSize()

    def paintEvent(self, _e) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        t = self.ctx.theme
        p.setBrush(t.c("panel", 0.97))
        p.setPen(t.c("accent"))
        p.drawRoundedRect(self.rect().adjusted(0, 0, -1, -1), 12, 12)


class Toast(QWidget):
    """In-app notification fallback when native notifications are unavailable."""

    def __init__(self, shell: "DesktopShell", title: str, message: str, action: str):
        super().__init__(None, Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint |
                         Qt.WindowType.WindowStaysOnTopHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.shell, self.action = shell, action
        self.setStyleSheet(stylesheet(shell.ctx.theme))
        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 12, 16, 12)
        t = QLabel(title)
        t.setFont(ui_font(10, QFont.Weight.DemiBold))
        m = QLabel(message)
        m.setWordWrap(True)
        m.setProperty("role", "dim")
        lay.addWidget(t)
        lay.addWidget(m)
        self.setFixedWidth(320)
        self.adjustSize()
        geo = shell.screen().availableGeometry()
        self.move(geo.right() - self.width() - 24, geo.bottom() - self.height() - 24)
        QTimer.singleShot(7000, self.close)

    def paintEvent(self, _e) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        t = self.shell.ctx.theme
        p.setBrush(t.c("panel", 0.98))
        p.setPen(t.c("accent"))
        p.drawRoundedRect(self.rect().adjusted(0, 0, -1, -1), 12, 12)

    def mouseReleaseEvent(self, _e) -> None:  # noqa: N802
        if self.action:
            self.shell.open_section(self.action)
        self.close()


# ============================================================== shell
class DesktopShell(QObject):
    def __init__(self, ctx: AppContext):
        super().__init__()
        self.ctx = ctx
        self.edit_mode = False
        self.quitting = False
        self.hidden = False
        self.mode = "window"
        self.window: Optional[DashboardWindow] = None
        self.floating: dict[str, FloatingWindow] = {}
        self.background: Optional[BackgroundLayer] = None
        self.banner: Optional[EditBanner] = None
        self.dialogs: dict[str, QWidget] = {}
        self.tray: Optional[QSystemTrayIcon] = None

        self.panels: dict[str, Panel] = {
            "wheel": RadialWheel(ctx),
            "clock": ClockPanel(ctx),
            "character": CharacterPanel(ctx),
            "tasks": TasksCompact(ctx),
            "water": WaterCompact(ctx),
            "movement": MovementCompact(ctx),
            "screen_time": ScreenTimeCompact(ctx),
        }
        for panel in self.panels.values():
            panel.moved.connect(self._panel_moved)

        sig = ctx.signals
        sig.data_changed.connect(self.on_data_changed)
        sig.open_section.connect(self.open_section)
        sig.layout_edit_changed.connect(self.set_edit_mode)
        ctx.wellbeing.water_changed.connect(lambda: self.on_data_changed("water"))
        ctx.wellbeing.movement_changed.connect(self.panels["movement"].refresh)
        ctx.focus.session_finished.connect(lambda _r: self.on_data_changed("focus"))
        ctx.focus.session_cancelled.connect(lambda _r: self.on_data_changed("focus"))

        self._refresh_timer = QTimer(self)
        self._refresh_timer.setInterval(30_000)
        self._refresh_timer.timeout.connect(self._periodic)
        self._refresh_timer.start()
        self._today = clock.today()

        self._health = QTimer(self)
        self._health.setInterval(5000)
        self._health.timeout.connect(self._check_desktop_health)

        self._reposition = QTimer(self)
        self._reposition.setSingleShot(True)
        self._reposition.setInterval(400)
        self._reposition.timeout.connect(self.rebuild)
        app = QGuiApplication.instance()
        app.screenAdded.connect(lambda _s: self._reposition.start())
        app.screenRemoved.connect(lambda _s: self._reposition.start())
        app.primaryScreenChanged.connect(lambda _s: self._reposition.start())
        self._watched_screen: Optional[QScreen] = None
        self._bg_timer = QTimer(self)
        self._bg_timer.setSingleShot(True)
        self._bg_timer.setInterval(600)
        self._bg_timer.timeout.connect(self.apply_background)

        self._create_tray()

    # -- tray ----------------------------------------------------------------
    def _create_tray(self) -> None:
        if not QSystemTrayIcon.isSystemTrayAvailable():
            log.info("System tray not available; using in-app notifications only")
            return
        self.tray = QSystemTrayIcon(app_icon(), self)
        self.tray.setToolTip("Pixel Desk")
        menu = QMenu()
        self._tray_menu = menu
        self.act_toggle = menu.addAction("Hide widgets", self.toggle_visible)
        self.act_edit = menu.addAction("Edit layout", lambda: self.set_edit_mode(not self.edit_mode))
        menu.addSeparator()
        menu.addAction("Log a glass of water", self.ctx.wellbeing.log_water)
        menu.addAction("Start / pause focus", lambda: self.ctx.focus.toggle())
        menu.addAction("Tasks…", lambda: self.open_section("tasks"))
        menu.addAction("Screen time…", lambda: self.open_section("screen_time"))
        menu.addAction("Streaks & habits…", lambda: self.open_section("streaks"))
        menu.addSeparator()
        self.act_monitor = QAction("Pause screen-time monitoring", menu)
        self.act_monitor.triggered.connect(
            lambda: self.ctx.settings.set("monitoring_enabled", not self.ctx.settings["monitoring_enabled"]))
        menu.addAction(self.act_monitor)
        self.act_mode = menu.addAction("Switch to window mode", self._switch_mode)
        menu.addAction("Settings…", lambda: self.open_section("settings"))
        menu.addSeparator()
        menu.addAction("Quit Pixel Desk", self.quit)
        menu.aboutToShow.connect(self._update_tray_menu)
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(self._tray_activated)
        self.tray.show()
        self.ctx.notifications.attach_tray(self.tray)

    def _update_tray_menu(self) -> None:
        self.act_toggle.setText("Show widgets" if self.hidden else "Hide widgets")
        self.act_edit.setText("Finish editing layout" if self.edit_mode else "Edit layout")
        self.act_monitor.setText("Resume screen-time monitoring" if not self.ctx.settings["monitoring_enabled"]
                                 else "Pause screen-time monitoring")
        self.act_mode.setText("Switch to window mode" if self.mode == "desktop" else "Switch to desktop mode")
        self.act_mode.setEnabled(IS_WINDOWS or self.mode == "desktop")

    def _tray_activated(self, reason) -> None:
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            self.toggle_visible()

    def _switch_mode(self) -> None:
        self.ctx.settings.set("display_mode", "window" if self.mode == "desktop" else "desktop")

    # -- geometry ----------------------------------------------------------------
    def screen(self) -> QScreen:
        screens = QGuiApplication.screens()
        idx = int(self.ctx.settings["screen_index"])
        return screens[idx] if 0 <= idx < len(screens) else QGuiApplication.primaryScreen()

    def area(self) -> QRect:
        if self.mode == "window" and self.window is not None:
            return QRect(0, 44, self.window.width(), self.window.height() - 44)
        return self.screen().availableGeometry()

    def _layout_key(self) -> str:
        return self.mode

    def position_panels(self) -> None:
        area = self.area()
        sizes = {pid: p.size() for pid, p in self.panels.items()}
        defaults = default_positions(area.size(), sizes)
        saved = self.ctx.settings["layout"].get(self._layout_key(), {})
        for pid, panel in self.panels.items():
            if pid in saved:
                fx, fy = saved[pid]
                pos = QPoint(int(fx * area.width()), int(fy * area.height()))
            else:
                pos = defaults[pid]
            x = max(0, min(pos.x(), area.width() - panel.width()))
            y = max(0, min(pos.y(), area.height() - panel.height()))
            if self.mode == "window":
                panel.move(area.x() + x, area.y() + y)
            elif pid in self.floating:
                self.floating[pid].move(area.x() + x, area.y() + y)

    def _panel_moved(self, pid: str, global_pos: QPoint) -> None:
        area = self.area()
        if self.mode == "window" and self.window is not None:
            local = self.window.mapFromGlobal(global_pos) - area.topLeft()
        else:
            local = global_pos - area.topLeft()
        layout = self.ctx.settings["layout"]
        mode_layout = layout.get(self._layout_key(), {})
        mode_layout[pid] = [round(local.x() / max(1, area.width()), 4), round(local.y() / max(1, area.height()), 4)]
        layout[self._layout_key()] = mode_layout
        self.ctx.settings.set("layout", layout, notify=False)

    # -- building hosts ------------------------------------------------------------
    def rebuild(self) -> None:
        """(Re)create the host for the configured display mode."""
        wanted = self.ctx.settings["display_mode"]
        if wanted == "desktop" and not IS_WINDOWS:
            log.info("Desktop mode is Windows-only; using window mode")
            wanted = "window"
        self._teardown()
        self.mode = wanted
        try:
            if wanted == "desktop":
                self._build_desktop()
            else:
                self._build_window()
        except Exception:
            log.exception("Desktop mode failed; falling back to window mode")
            self._teardown()
            self.mode = "window"
            self._build_window()
        self._watch_screen()
        self.apply_visibility()
        self.position_panels()
        self.apply_background()
        if self.edit_mode:
            self.set_edit_mode(True)

    def _watch_screen(self) -> None:
        if self._watched_screen is not None:
            try:
                self._watched_screen.availableGeometryChanged.disconnect(self._on_geometry)
            except (RuntimeError, TypeError):
                pass
        self._watched_screen = self.screen()
        self._watched_screen.availableGeometryChanged.connect(self._on_geometry)

    def _on_geometry(self, _rect) -> None:
        self.position_panels()
        if self.background is not None:
            self._reposition.start()

    def _teardown(self) -> None:
        self._health.stop()
        for pid, panel in self.panels.items():
            panel.setParent(None)
        for fw in self.floating.values():
            fw.panel = None
            fw.close()
            fw.deleteLater()
        self.floating.clear()
        if self.window is not None:
            self.save_window_geometry()
            self.window.hide()
            self.window.deleteLater()
            self.window = None
        self._drop_background_layer()

    def _build_window(self) -> None:
        self.window = DashboardWindow(self)
        for panel in self.panels.values():
            panel.setParent(self.window)
        geo = self.ctx.settings["window_geometry"]
        avail = self.screen().availableGeometry()
        if geo and len(geo) == 4:
            rect = QRect(*geo)
            if not avail.intersects(rect):
                rect.moveCenter(avail.center())
            self.window.setGeometry(rect)
        else:
            w, h = int(min(avail.width() * 0.92, 1760)), int(min(avail.height() * 0.92, 990))
            self.window.setGeometry(QRect(avail.x() + (avail.width() - w) // 2, avail.y() + (avail.height() - h) // 2, w, h))
        self.window._bar.raise_()
        self.window.show()

    def _build_desktop(self) -> None:
        for pid, panel in self.panels.items():
            fw = FloatingWindow(panel)
            fw.setWindowIcon(app_icon())
            self.floating[pid] = fw
        self._health.start()

    def apply_visibility(self) -> None:
        visible = self.ctx.settings["widgets_visible"]
        for pid, panel in self.panels.items():
            on = bool(visible.get(pid, True)) and not self.hidden
            if self.mode == "window":
                panel.setVisible(bool(visible.get(pid, True)))
            elif pid in self.floating:
                self.floating[pid].setVisible(on)
                panel.setVisible(True)
        if self.mode == "window" and self.window is not None:
            self.window.setVisible(not self.hidden)

    # -- background ----------------------------------------------------------------
    def request_background(self) -> None:
        """Debounced apply_background (sliders fire many change events)."""
        if self.window is not None:
            self.window.update()
        self._bg_timer.start()

    def _drop_background_layer(self) -> None:
        if self.background is not None:
            try:
                desktop_layer.detach_background(int(self.background.winId()))
            except Exception:  # pragma: no cover
                pass
            self.background.hide()
            self.background.deleteLater()
            self.background = None

    def apply_background(self) -> None:
        if self.mode == "window":
            self.window.update() if self.window else None
        choice = self.ctx.settings["desktop_background"] if IS_WINDOWS else "none"
        if choice == "live" and self.mode == "desktop":
            if self.background is None:
                self.background = BackgroundLayer(self.ctx, self.screen())
                if not self.background.attach():
                    log.warning("Live desktop layer unavailable; keeping the current wallpaper")
                    self._drop_background_layer()
                    self.notify("Desktop background", "The live background layer isn't supported here. "
                                "Try “Use the Pixel Desk background as wallpaper” in Settings.", "settings:general")
            else:
                self.background.update()
        else:
            self._drop_background_layer()
        if choice == "wallpaper":
            self._apply_wallpaper()
        else:
            self._restore_wallpaper()

    def _wallpaper_path(self) -> str:
        return str(cache_dir() / "pixeldesk_wallpaper.png")

    def _apply_wallpaper(self) -> None:
        sc = self.screen()
        dpr = sc.devicePixelRatio()
        size = QSize(int(sc.geometry().width() * dpr), int(sc.geometry().height() * dpr))
        s = self.ctx.settings
        pm = render_background(size, self.ctx.theme, float(s["background_brightness"]), s["custom_background"])
        path = self._wallpaper_path()
        pm.save(path, "PNG")
        current = api.get_wallpaper()
        if current and current != path and not s["saved_wallpaper"]:
            s.set("saved_wallpaper", current, notify=False)
        if not api.set_wallpaper(path):
            log.warning("Could not set the desktop wallpaper")

    def _restore_wallpaper(self) -> None:
        s = self.ctx.settings
        saved = s["saved_wallpaper"]
        if IS_WINDOWS and api.get_wallpaper() == self._wallpaper_path():
            api.set_wallpaper(saved or "")
        if saved:
            s.set("saved_wallpaper", "", notify=False)

    def _check_desktop_health(self) -> None:
        """Explorer restarts destroy the WorkerW host and Progman owner; re-attach."""
        if self.mode != "desktop":
            return
        if self.background is not None and not self.background.healthy():
            log.info("Desktop layer lost (Explorer restart?); re-attaching")
            self._drop_background_layer()
            self.apply_background()
        for fw in self.floating.values():
            if fw.isVisible():
                desktop_layer.pin_widget_window(int(fw.winId()))

    # -- visibility / editing ----------------------------------------------------------
    def toggle_visible(self) -> None:
        self.hidden = not self.hidden
        self.apply_visibility()
        if not self.hidden and self.window is not None:
            self.window.showNormal()
            self.window.raise_()
            self.window.activateWindow()

    def show_all(self) -> None:
        self.hidden = False
        self.apply_visibility()
        if self.window is not None:
            self.window.showNormal()
            self.window.raise_()
            self.window.activateWindow()

    def set_edit_mode(self, on: bool) -> None:
        self.edit_mode = on
        for panel in self.panels.values():
            panel.set_edit_mode(on)
        if self.window is not None:
            self.window.buttons["edit"].setText("Done" if on else "Edit layout")
            self.window.buttons["edit"].setProperty("accent", "true" if on else "false")
            self.window.buttons["edit"].setStyleSheet(stylesheet(self.ctx.theme))
        if self.mode == "desktop":
            if on and self.banner is None:
                self.banner = EditBanner(self)
                geo = self.screen().availableGeometry()
                self.banner.move(geo.center().x() - self.banner.width() // 2, geo.top() + 16)
                self.banner.show()
            elif not on and self.banner is not None:
                self.banner.close()
                self.banner.deleteLater()
                self.banner = None

    def close_window(self) -> None:
        if self.window is not None:
            self.window.close()

    def save_window_geometry(self) -> None:
        if self.window is not None and not self.window.isMaximized():
            g = self.window.geometry()
            self.ctx.settings.set("window_geometry", [g.x(), g.y(), g.width(), g.height()], notify=False)

    # -- theming ----------------------------------------------------------------------
    def apply_theme(self) -> None:
        if self.window is not None:
            self.window.apply_theme()
        for panel in self.panels.values():
            if hasattr(panel, "apply_theme"):
                panel.apply_theme()
            panel.update()
        for dlg in self.dialogs.values():
            dlg.apply_theme()
            dlg.reload()
        self.request_background()

    # -- data -----------------------------------------------------------------------
    def on_data_changed(self, area: str) -> None:
        p = self.panels
        if area in ("launcher", "all"):
            p["wheel"].reload()
        if area in ("tasks", "focus", "habits", "xp", "all"):
            p["tasks"].refresh()
            p["character"].refresh()
        if area in ("water", "all"):
            p["water"].refresh()
            p["character"].refresh()
        if area in ("usage", "all"):
            p["screen_time"].refresh()
        if area in ("movement", "all"):
            p["movement"].refresh()
        for key, dlg in list(self.dialogs.items()):
            if dlg.isVisible():
                dlg.reload()
        if area in ("tasks", "habits", "water", "focus", "all"):
            self.ctx.app.check_achievements()

    def _periodic(self) -> None:
        if clock.today() != self._today:
            self._today = clock.today()
            self.on_data_changed("all")
            self.ctx.say("happy", "A brand-new day! What's one thing you'd like to do today?", "tasks")
        else:
            for pid in ("tasks", "water", "screen_time", "wheel"):
                self.panels[pid].refresh()
            dlg = self.dialogs.get("screen_time")
            if dlg is not None and dlg.isVisible():
                dlg.reload()

    def on_monitor_status(self, _status) -> None:
        self.panels["screen_time"].update_status()

    # -- dialogs ----------------------------------------------------------------------
    def open_section(self, key: str) -> None:
        tab = None
        if key.startswith("settings"):
            key, _, tab = key.partition(":")
        factories = {"tasks": TasksDialog, "water": WaterDialog, "movement": MovementDialog,
                     "screen_time": ScreenTimeDialog, "streaks": StreaksDialog, "settings": SettingsDialog}
        if key not in factories:
            return
        dlg = self.dialogs.get(key)
        if dlg is None:
            dlg = factories[key](self.ctx)
            dlg.setWindowIcon(app_icon())
            self.dialogs[key] = dlg
        if tab and hasattr(dlg, "show_tab"):
            dlg.show_tab(tab)
        dlg.present()

    def notify(self, title: str, message: str, action: str = "") -> None:
        """Native notification if possible, otherwise a small in-app toast."""
        native_ok = (self.tray is not None and QSystemTrayIcon.supportsMessages()
                     and self.ctx.settings["notifications_native"])
        if native_ok:
            self.ctx.notifications.notify(title, message, action)
        else:
            self.ctx.notifications.notify(title, message, action, native=False)
            Toast(self, title, message, action).show()

    # -- lifecycle -------------------------------------------------------------------
    def quit(self) -> None:
        self.quitting = True
        QApplication.instance().quit()

    def shutdown(self) -> None:
        self.quitting = True
        self.save_window_geometry()
        self._health.stop()
        if self.tray is not None:
            self.tray.hide()
        for dlg in self.dialogs.values():
            dlg.close()
        self._drop_background_layer()
