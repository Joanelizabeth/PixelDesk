"""The radial launcher: a custom-painted circle of folders and applications."""
from __future__ import annotations

import math
from pathlib import Path

from PySide6.QtCore import QPoint, QPointF, QRect, QRectF, QSize, Qt, QTimer
from PySide6.QtGui import (
    QContextMenuEvent, QFont, QFontMetrics, QKeyEvent, QMouseEvent, QPainter, QPen, QRadialGradient,
)
from PySide6.QtWidgets import QMenu, QToolTip

from database.repository import LauncherItem
from services.launcher_service import validate_entry

from .panel import Panel
from .pixel_art import draw_pixel_image, draw_pixel_text, icon_image, pixel_text_width
from .theme import blend, ui_font

WHEEL_SIZES = {"small": 380, "medium": 460, "large": 540}


class RadialWheel(Panel):
    card = False

    def __init__(self, ctx, parent=None):
        super().__init__("wheel", ctx, parent)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMouseTracking(True)
        self.setAccessibleName("Radial folder launcher")
        self.items: list[LauncherItem] = []
        self._valid: list[bool] = []
        self._hover = -1
        self._selected = -1  # keyboard selection
        self._scales: list[float] = []
        self._pulse: dict[int, float] = {}
        self._sel_angle = -90.0
        self._intro = 1.0
        self._anim = QTimer(self)
        self._anim.setInterval(16)
        self._anim.timeout.connect(self._step)
        self.apply_size()
        self.reload()
        if not self._reduced():
            self._intro = 0.0
            self._anim.start()

    # -- data --------------------------------------------------------------
    def apply_size(self) -> None:
        side = WHEEL_SIZES.get(self.ctx.settings["wheel_size"], 460)
        self.setFixedSize(side, side)
        self.update()

    def reload(self) -> None:
        self.items = self.ctx.repo.list_launcher_items()
        self._valid = [validate_entry(i.kind, i.path) is None for i in self.items]
        self._scales = [1.0] * len(self.items)
        if self._selected >= len(self.items):
            self._selected = len(self.items) - 1
        self._hover = -1
        self.update()

    def refresh(self) -> None:
        self._valid = [validate_entry(i.kind, i.path) is None for i in self.items]
        self.update()

    # -- geometry ------------------------------------------------------------
    def _reduced(self) -> bool:
        s = self.ctx.settings
        return bool(s["reduced_motion"]) or not s["animations_enabled"]

    @property
    def center(self) -> QPointF:
        return QPointF(self.width() / 2, self.height() / 2)

    @property
    def ring_radius(self) -> float:
        return self.width() * 0.355

    @property
    def node_radius(self) -> float:
        n = max(1, len(self.items))
        arc = 2 * math.pi * self.ring_radius / n
        return max(16.0, min(self.width() * 0.072, arc * 0.34))

    @property
    def hub_radius(self) -> float:
        return self.ring_radius * 0.46

    def _angle(self, index: int) -> float:
        n = max(1, len(self.items))
        intro = (1 - self._ease(self._intro)) * -28.0
        return -90.0 + index * 360.0 / n + intro

    @staticmethod
    def _ease(t: float) -> float:
        return 1 - (1 - t) ** 3

    def node_center(self, index: int) -> QPointF:
        a = math.radians(self._angle(index))
        return self.center + QPointF(math.cos(a), math.sin(a)) * self.ring_radius

    def item_at(self, pos: QPointF) -> int:
        r = self.node_radius * 1.3
        for i in range(len(self.items)):
            d = self.node_center(i) - pos
            if d.x() ** 2 + d.y() ** 2 <= r * r:
                return i
        return -1

    def _in_hub(self, pos: QPointF) -> bool:
        d = pos - self.center
        return d.x() ** 2 + d.y() ** 2 <= self.hub_radius ** 2

    # -- animation -----------------------------------------------------------
    def _focus_index(self) -> int:
        return self._hover if self._hover >= 0 else self._selected

    def _step(self) -> None:
        busy = False
        reduced = self._reduced()
        if self._intro < 1.0:
            self._intro = 1.0 if reduced else min(1.0, self._intro + 0.035)
            busy = True
        focus = self._focus_index()
        for i in range(len(self._scales)):
            target = 1.16 if i == focus else 1.0
            target += self._pulse.get(i, 0.0)
            cur = self._scales[i]
            nxt = target if reduced else cur + (target - cur) * 0.25
            if abs(nxt - target) < 0.003:
                nxt = target
            busy |= nxt != cur
            self._scales[i] = nxt
        for i in list(self._pulse):
            self._pulse[i] *= 0.82
            if self._pulse[i] < 0.01:
                del self._pulse[i]
            busy = True
        if focus >= 0:
            target_angle = self._angle(focus)
            diff = (target_angle - self._sel_angle + 540) % 360 - 180
            if abs(diff) > 0.2 and not reduced:
                self._sel_angle += diff * 0.22
                busy = True
            else:
                self._sel_angle = target_angle
        if not busy:
            self._anim.stop()
        self.update()

    def _kick(self) -> None:
        if not self._anim.isActive():
            self._anim.start()

    # -- painting ------------------------------------------------------------
    def paint_content(self, p: QPainter) -> None:
        t = self.theme
        c = self.center
        R = self.ring_radius
        op = self.opacity()

        # soft disc behind the ring
        disc = QRadialGradient(c, R * 1.35)
        disc.setColorAt(0.0, t.c("panel", 0.55 * op))
        disc.setColorAt(0.75, t.c("panel", 0.35 * op))
        disc.setColorAt(1.0, t.c("panel", 0.0))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(disc)
        p.drawEllipse(c, R * 1.35, R * 1.35)

        # outer dotted pixel ring with ticks
        p.setBrush(t.c("accent", 0.35))
        outer = R + self.node_radius + 16
        for k in range(0, 360, 6):
            a = math.radians(k)
            size = 3 if k % 30 == 0 else 2
            pt = c + QPointF(math.cos(a), math.sin(a)) * outer
            p.drawRect(QRectF(round(pt.x()) - size / 2, round(pt.y()) - size / 2, size, size))

        # main ring
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(t.c("border", 0.9), 1.2))
        p.drawEllipse(c, R, R)
        p.setPen(QPen(t.c("border", 0.45), 1))
        p.drawEllipse(c, R * 0.72, R * 0.72)

        # selection arc
        focus = self._focus_index()
        if focus >= 0 and self.items:
            span = min(60.0, 360.0 / len(self.items) * 0.7)
            rect = QRectF(c.x() - outer, c.y() - outer, outer * 2, outer * 2)
            pen = QPen(t.c("accent", 0.85), 3)
            pen.setCapStyle(Qt.PenCapStyle.FlatCap)
            p.setPen(pen)
            p.drawArc(rect, int(-(self._sel_angle - span / 2) * 16), int(-span * 16))

        # spokes to the hub for the focused item
        if focus >= 0 and self.items:
            nc = self.node_center(focus)
            p.setPen(QPen(t.c("accent", 0.35), 1, Qt.PenStyle.DotLine))
            p.drawLine(self._towards(c, nc, self.hub_radius + 4), self._towards(nc, c, self.node_radius * 1.2))

        self._paint_hub(p)
        for i in range(len(self.items)):
            self._paint_node(p, i)

        if self.hasFocus() and self._selected >= 0 and self.items:
            nc = self.node_center(self._selected)
            rr = self.node_radius * self._scales[self._selected] + 6
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.setPen(QPen(t.c("accent2"), 1.5, Qt.PenStyle.DashLine))
            p.drawEllipse(nc, rr, rr)

    @staticmethod
    def _towards(a: QPointF, b: QPointF, dist: float) -> QPointF:
        d = b - a
        length = math.hypot(d.x(), d.y()) or 1
        return a + d * (dist / length)

    def _paint_hub(self, p: QPainter) -> None:
        t = self.theme
        c = self.center
        hr = self.hub_radius
        grad = QRadialGradient(c - QPointF(hr * 0.3, hr * 0.4), hr * 1.4)
        grad.setColorAt(0.0, blend(t.c("panel"), t.c("accent"), 0.16))
        grad.setColorAt(1.0, t.c("panel"))
        p.setBrush(grad)
        p.setPen(QPen(t.c("accent", 0.7), 1.5))
        p.drawEllipse(c, hr, hr)
        p.setPen(QPen(t.c("border", 0.8), 1))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(c, hr - 6, hr - 6)

        focus = self._focus_index()
        moon = int(hr * 0.5) // 12 * 12 or 24
        moon_rect = QRect(int(c.x() - moon / 2), int(c.y() - hr * 0.62), moon, moon)
        draw_pixel_image(p, icon_image("moon", t.warning if t.dark else t.accent, t.outline), moon_rect)
        # small sparkle next to the moon
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(t.c("star", 0.8))
        sx, sy = moon_rect.right() + 6, moon_rect.top() + 4
        for dx, dy in ((0, 0), (-2, 0), (2, 0), (0, -2), (0, 2)):
            p.drawRect(sx + dx, sy + dy, 2, 2)

        if focus >= 0 and self.items:
            item = self.items[focus]
            title = item.label
            sub = ("Folder" if item.kind == "folder" else "Application") if self._valid[focus] else "Not found"
        elif not self.items:
            title, sub = "Add folders", "Click to set up"
        else:
            title, sub = "", f"{len(self.items)} shortcuts"

        if title:
            f = ui_font(11.5, QFont.Weight.DemiBold)
            fm = QFontMetrics(f)
            text = fm.elidedText(title, Qt.TextElideMode.ElideRight, int(hr * 1.6))
            p.setFont(f)
            p.setPen(t.c("text"))
            p.drawText(QRectF(c.x() - hr, c.y() - 4, hr * 2, 24), Qt.AlignmentFlag.AlignCenter, text)
        else:
            scale = 2
            label = "PIXEL DESK"
            w = pixel_text_width(label, scale)
            draw_pixel_text(p, label, QPoint(int(c.x() - w / 2), int(c.y() - 2)), scale, t.c("text"),
                            shadow=t.c("outline", 0.6))
        p.setFont(ui_font(8.5))
        p.setPen(t.c("warning") if sub == "Not found" else t.c("text_dim"))
        p.drawText(QRectF(c.x() - hr, c.y() + 20, hr * 2, 18), Qt.AlignmentFlag.AlignCenter, sub)

    def _paint_node(self, p: QPainter, i: int) -> None:
        t = self.theme
        item = self.items[i]
        nc = self.node_center(i)
        scale = self._scales[i] if i < len(self._scales) else 1.0
        r = self.node_radius * scale
        focused = i == self._focus_index()
        valid = self._valid[i]

        if focused:
            glow = QRadialGradient(nc, r * 2.0)
            glow.setColorAt(0.0, t.c("accent", 0.35))
            glow.setColorAt(1.0, t.c("accent", 0.0))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(glow)
            p.drawEllipse(nc, r * 2.0, r * 2.0)

        fill = blend(t.c("panel"), t.c("accent"), 0.22 if focused else 0.08)
        fill.setAlphaF(0.95)
        p.setBrush(fill)
        p.setPen(QPen(t.c("accent") if focused else t.c("border"), 1.5 if focused else 1.0))
        p.drawEllipse(nc, r, r)

        color = t.accent if item.kind == "folder" else t.accent2
        if not valid:
            color = t.text_dim
        icon_px = max(24, int(r * 1.15) // 12 * 12)
        rect = QRect(int(nc.x() - icon_px / 2), int(nc.y() - icon_px / 2), icon_px, icon_px)
        p.setOpacity(1.0 if valid else 0.55)
        draw_pixel_image(p, icon_image(item.icon, color, t.outline, t.accent2), rect)
        p.setOpacity(1.0)
        if not valid:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(t.c("warning"))
            p.drawRect(QRectF(nc.x() + r * 0.55, nc.y() - r * 0.85, 5, 5))

        # short label outside the ring
        a = math.radians(self._angle(i))
        lr = self.ring_radius + self.node_radius + 30
        lp = self.center + QPointF(math.cos(a), math.sin(a)) * lr
        f = ui_font(8.5, QFont.Weight.DemiBold if focused else QFont.Weight.Normal)
        fm = QFontMetrics(f)
        label = fm.elidedText(item.label, Qt.TextElideMode.ElideRight, 86)
        w = fm.horizontalAdvance(label) + 4
        p.setFont(f)
        p.setPen(t.c("text") if focused else t.c("text_dim"))
        p.drawText(QRectF(lp.x() - w / 2, lp.y() - 9, w, 18), Qt.AlignmentFlag.AlignCenter, label)

    # -- interaction ---------------------------------------------------------
    def mouseMoveEvent(self, e: QMouseEvent) -> None:  # noqa: N802
        if self._edit_mode:
            super().mouseMoveEvent(e)
            return
        idx = self.item_at(e.position())
        if idx != self._hover:
            self._hover = idx
            self.setCursor(Qt.CursorShape.PointingHandCursor if idx >= 0 or self._in_hub(e.position())
                           else Qt.CursorShape.ArrowCursor)
            if idx >= 0:
                item = self.items[idx]
                tip = f"<b>{item.label}</b><br>{item.path}"
                if not self._valid[idx]:
                    tip += "<br><i>Not found - right-click to edit or remove</i>"
                QToolTip.showText(e.globalPosition().toPoint(), tip, self)
            else:
                QToolTip.hideText()
            self._kick()
        super().mouseMoveEvent(e)

    def leaveEvent(self, _e) -> None:  # noqa: N802
        self._hover = -1
        self._kick()

    def mouseReleaseEvent(self, e: QMouseEvent) -> None:  # noqa: N802
        if self._edit_mode:
            super().mouseReleaseEvent(e)
            return
        if e.button() == Qt.MouseButton.LeftButton:
            idx = self.item_at(e.position())
            if idx >= 0:
                self._selected = idx
                self.launch(idx)
            elif self._in_hub(e.position()):
                self._hub_menu(e.globalPosition().toPoint())
        super().mouseReleaseEvent(e)

    def keyPressEvent(self, e: QKeyEvent) -> None:  # noqa: N802
        n = len(self.items)
        key = e.key()
        if n and key in (Qt.Key.Key_Right, Qt.Key.Key_Down):
            self._selected = (self._selected + 1) % n
        elif n and key in (Qt.Key.Key_Left, Qt.Key.Key_Up):
            self._selected = (self._selected - 1) % n if self._selected >= 0 else n - 1
        elif n and key == Qt.Key.Key_Home:
            self._selected = 0
        elif n and key == Qt.Key.Key_End:
            self._selected = n - 1
        elif key in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space):
            if self._selected >= 0:
                self.launch(self._selected)
            else:
                self._hub_menu(self.mapToGlobal(self.center.toPoint()))
        elif key == Qt.Key.Key_Menu and self._selected >= 0:
            self._item_menu(self._selected, self.mapToGlobal(self.node_center(self._selected).toPoint()))
        else:
            super().keyPressEvent(e)
            return
        self._hover = -1
        self._kick()
        self.update()

    def focusInEvent(self, e) -> None:  # noqa: N802
        if self._selected < 0 and self.items:
            self._selected = 0
        self._kick()
        super().focusInEvent(e)

    def focusOutEvent(self, e) -> None:  # noqa: N802
        self.update()
        super().focusOutEvent(e)

    def contextMenuEvent(self, e: QContextMenuEvent) -> None:  # noqa: N802
        if self._edit_mode:
            return
        idx = self.item_at(QPointF(e.pos()))
        if idx >= 0:
            self._item_menu(idx, e.globalPos())
        else:
            self._hub_menu(e.globalPos())

    def launch(self, idx: int) -> None:
        item = self.items[idx]
        result = self.ctx.launcher.launch(item.kind, item.path)
        self._pulse[idx] = 0.14 if result.ok else 0.0
        self._kick()
        if not result.ok:
            self._valid[idx] = False
            QToolTip.showText(self.mapToGlobal(self.node_center(idx).toPoint()), result.message, self)
            if self.ctx.settings["character_messages"]:
                self.ctx.say("idle", f"Hmm, I couldn't open “{item.label}”. Right-click it to fix the path.",
                             "settings:launcher")

    def _hub_menu(self, pos: QPoint) -> None:
        menu = QMenu(self)
        menu.addAction("Add folder…", lambda: self._add("folder"))
        menu.addAction("Add application…", lambda: self._add("app"))
        menu.addSeparator()
        menu.addAction("Edit wheel…", lambda: self.ctx.signals.open_section.emit("settings:launcher"))
        menu.exec(pos)

    def _item_menu(self, idx: int, pos: QPoint) -> None:
        item = self.items[idx]
        menu = QMenu(self)
        menu.addAction("Open", lambda: self.launch(idx))
        if item.kind == "app":
            folder = str(Path(item.path).parent)
            menu.addAction("Open containing folder", lambda: self.ctx.launcher.launch("folder", folder))
        menu.addAction("Edit…", lambda: self._edit(idx))
        menu.addSeparator()
        left = menu.addAction("Move counter-clockwise", lambda: self._move(idx, -1))
        right = menu.addAction("Move clockwise", lambda: self._move(idx, 1))
        left.setEnabled(len(self.items) > 1)
        right.setEnabled(len(self.items) > 1)
        menu.addSeparator()
        menu.addAction("Remove from wheel", lambda: self._remove(idx))
        menu.exec(pos)

    def _add(self, kind: str) -> None:
        from .launcher_dialogs import LauncherItemDialog

        dlg = LauncherItemDialog(self.ctx, kind=kind, parent=None)
        if dlg.exec():
            label, kind, path, icon = dlg.values()
            self.ctx.repo.add_launcher_item(label, kind, path, icon)
            self.ctx.notify_changed("launcher")

    def _edit(self, idx: int) -> None:
        from .launcher_dialogs import LauncherItemDialog

        item = self.items[idx]
        dlg = LauncherItemDialog(self.ctx, item=item, parent=None)
        if dlg.exec():
            label, kind, path, icon = dlg.values()
            self.ctx.repo.update_launcher_item(item.id, label=label, path=path, icon=icon, kind=kind)
            self.ctx.notify_changed("launcher")

    def _move(self, idx: int, delta: int) -> None:
        ids = [i.id for i in self.items]
        j = (idx + delta) % len(ids)
        ids[idx], ids[j] = ids[j], ids[idx]
        self.ctx.repo.reorder_launcher_items(ids)
        self._selected = j
        self.ctx.notify_changed("launcher")

    def _remove(self, idx: int) -> None:
        # Removes only the shortcut entry; the folder/app on disk is untouched.
        self.ctx.repo.delete_launcher_item(self.items[idx].id)
        self.ctx.notify_changed("launcher")

    def sizeHint(self) -> QSize:  # noqa: N802
        return self.size()
