"""Base class for desktop panels: restrained card painting plus drag-to-move
in layout-edit mode. A panel can be a child of the window-mode canvas or the
content of its own floating desktop window."""
from __future__ import annotations

from PySide6.QtCore import QPoint, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QMouseEvent, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QMenu, QWidget

from app.context import AppContext


class Panel(QWidget):
    moved = Signal(str, QPoint)  # panel id, new global top-left
    card = True  # paint a translucent card behind the content

    def __init__(self, panel_id: str, ctx: AppContext, parent=None):
        super().__init__(parent)
        self.panel_id = panel_id
        self.ctx = ctx
        self._edit_mode = False
        self._drag_offset: QPoint | None = None
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, False)

    # -- theming --------------------------------------------------------
    @property
    def theme(self):
        return self.ctx.theme

    def opacity(self) -> float:
        return float(self.ctx.settings["widget_opacity"])

    def paint_card(self, p: QPainter, rect: QRectF | None = None, radius: float = 14.0) -> None:
        t = self.theme
        r = QRectF(rect if rect is not None else QRectF(self.rect())).adjusted(0.5, 0.5, -0.5, -0.5)
        path = QPainterPath()
        path.addRoundedRect(r, radius, radius)
        p.fillPath(path, t.c("panel", self.opacity()))
        p.setPen(QPen(t.c("border", 0.9), 1))
        p.drawPath(path)
        # two tiny pixel accents on opposite corners
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(t.c("accent", 0.55))
        p.drawRect(int(r.left() + radius), int(r.top() + 3), 3, 3)
        p.drawRect(int(r.right() - radius - 3), int(r.bottom() - 6), 3, 3)

    def paint_edit_overlay(self, p: QPainter) -> None:
        if not self._edit_mode:
            return
        t = self.theme
        p.setPen(QPen(t.c("accent"), 1.5, Qt.PenStyle.DashLine))
        p.setBrush(t.c("accent", 0.08))
        p.drawRoundedRect(QRectF(self.rect()).adjusted(1, 1, -1, -1), 12, 12)

    def paintEvent(self, _event) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        if self.card:
            self.paint_card(p)
        self.paint_content(p)
        self.paint_edit_overlay(p)

    def paint_content(self, p: QPainter) -> None:
        pass

    def refresh(self) -> None:
        self.update()

    # -- layout editing -------------------------------------------------
    def set_edit_mode(self, on: bool) -> None:
        self._edit_mode = on
        for child in self.findChildren(QWidget):
            child.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, on)
        self.setCursor(Qt.CursorShape.SizeAllCursor if on else Qt.CursorShape.ArrowCursor)
        self.update()

    def _mover(self) -> QWidget:
        return self.window() if self.window() is not self and self.parent() is not None and \
            self.window().property("pixeldesk_floating") else self

    def mousePressEvent(self, e: QMouseEvent) -> None:  # noqa: N802
        if self._edit_mode and e.button() == Qt.MouseButton.LeftButton:
            mover = self._mover()
            self._drag_offset = e.globalPosition().toPoint() - mover.mapToGlobal(QPoint(0, 0))
        # Always accept: an ignored press would reach the window and start a
        # system move, swallowing the release that panels use as their click.
        e.accept()

    def contextMenuEvent(self, e) -> None:  # noqa: N802
        shell = getattr(self.ctx.app, "shell", None)
        if shell is None:
            return
        menu = QMenu(self)
        menu.addAction("Settings…", lambda: shell.open_section("settings"))
        menu.addAction("Finish editing layout" if shell.edit_mode else "Edit layout",
                       lambda: shell.set_edit_mode(not shell.edit_mode))
        menu.addAction("Hide this widget", lambda: self._hide_self())
        menu.addAction("Hide all widgets", shell.toggle_visible)
        menu.addSeparator()
        menu.addAction("Quit Pixel Desk", shell.quit)
        menu.exec(e.globalPos())

    def _hide_self(self) -> None:
        visible = self.ctx.settings["widgets_visible"]
        visible[self.panel_id] = False
        self.ctx.settings.set("widgets_visible", visible)

    def mouseMoveEvent(self, e: QMouseEvent) -> None:  # noqa: N802
        if self._edit_mode and self._drag_offset is not None:
            mover = self._mover()
            target = e.globalPosition().toPoint() - self._drag_offset
            if mover.isWindow():
                mover.move(target)
            else:
                parent = mover.parentWidget()
                local = parent.mapFromGlobal(target)
                local.setX(max(0, min(local.x(), parent.width() - mover.width())))
                local.setY(max(0, min(local.y(), parent.height() - mover.height())))
                mover.move(local)
            e.accept()
            return
        super().mouseMoveEvent(e)

    def mouseReleaseEvent(self, e: QMouseEvent) -> None:  # noqa: N802
        if self._edit_mode and self._drag_offset is not None:
            self._drag_offset = None
            mover = self._mover()
            self.moved.emit(self.panel_id, mover.mapToGlobal(QPoint(0, 0)))
            e.accept()
            return
        super().mouseReleaseEvent(e)


def dim_label_color(theme) -> QColor:
    return theme.c("text_dim")
