"""Base for the small lower-right utility widgets."""
from __future__ import annotations

from PySide6.QtCore import QRect, QRectF, Qt
from PySide6.QtGui import QFont, QMouseEvent, QPainter, QPen
from PySide6.QtWidgets import QPushButton, QWidget

from .panel import Panel
from .pixel_art import draw_pixel_image, icon_image
from .theme import stylesheet, ui_font


class CompactPanel(Panel):
    W, H = 236, 96
    icon_name = "star"
    title = ""
    section = ""

    def __init__(self, panel_id: str, ctx, parent=None):
        super().__init__(panel_id, ctx, parent)
        self.setFixedSize(self.W, self.H)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.TabFocus)
        self.value = ""
        self.sub = ""
        self.progress = 0.0
        self.progress_color = "accent"

    def icon_color(self) -> str:
        return self.theme.accent

    def make_button(self, text: str, tip: str, slot, accent: bool = False) -> QPushButton:
        b = QPushButton(text, self)
        b.setToolTip(tip)
        b.setCursor(Qt.CursorShape.PointingHandCursor)
        b.setProperty("flat", "true" if not accent else "false")
        if accent:
            b.setProperty("accent", "true")
        b.setStyleSheet(stylesheet(self.theme))
        b.clicked.connect(slot)
        return b

    def apply_theme(self) -> None:
        for b in self.findChildren(QPushButton):
            b.setStyleSheet(stylesheet(self.theme))
        self.update()

    def paint_content(self, p: QPainter) -> None:
        t = self.theme
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(t.c("bg_bottom", 0.5))
        p.drawEllipse(QRectF(12, 14, 34, 34))
        draw_pixel_image(p, icon_image(self.icon_name, self.icon_color(), t.outline, t.accent2), QRect(17, 19, 24, 24))
        p.setFont(ui_font(8.5))
        p.setPen(t.c("text_dim"))
        p.drawText(QRectF(56, 10, self.W - 64, 16), Qt.AlignmentFlag.AlignLeft, self.title)
        p.setFont(ui_font(12.5, QFont.Weight.DemiBold))
        p.setPen(t.c("text"))
        p.drawText(QRectF(56, 26, self.W - 64, 24), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                   self.value)
        p.setFont(ui_font(8.5))
        p.setPen(t.c("text_dim"))
        fm = p.fontMetrics()
        p.drawText(QRectF(56, 50, self.W - 64, 16), Qt.AlignmentFlag.AlignLeft,
                   fm.elidedText(self.sub, Qt.TextElideMode.ElideRight, self.W - 66))
        self.paint_extra(p)
        if self.hasFocus():
            p.setPen(QPen(t.c("accent"), 1.5, Qt.PenStyle.DashLine))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRoundedRect(QRectF(self.rect()).adjusted(2, 2, -2, -2), 12, 12)

    def paint_extra(self, p: QPainter) -> None:
        t = self.theme
        bar = QRectF(14, self.H - 18, self.W - 28, 5)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(t.c("border", 0.8))
        p.drawRoundedRect(bar, 2.5, 2.5)
        if self.progress > 0:
            p.setBrush(t.c(self.progress_color))
            p.drawRoundedRect(QRectF(bar.left(), bar.top(), max(5.0, bar.width() * min(1.0, self.progress)), 5), 2.5, 2.5)

    def mouseReleaseEvent(self, e: QMouseEvent) -> None:  # noqa: N802
        if not self._edit_mode and e.button() == Qt.MouseButton.LeftButton and self.section:
            self.ctx.signals.open_section.emit(self.section)
        super().mouseReleaseEvent(e)

    def keyPressEvent(self, e) -> None:  # noqa: N802
        if e.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space) and self.section:
            self.ctx.signals.open_section.emit(self.section)
            return
        super().keyPressEvent(e)


class DetailDialog(QWidget):
    """Base for detail windows: a normal top-level window, never always-on-top."""

    def __init__(self, ctx, title: str, width: int = 560, height: int = 600):
        super().__init__(None, Qt.WindowType.Window)
        self.ctx = ctx
        self.setWindowTitle(f"{title} - Pixel Desk")
        self.setObjectName("page")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.resize(width, height)
        self.apply_theme()

    def apply_theme(self) -> None:
        t = self.ctx.theme
        self.setStyleSheet(stylesheet(t) + f"QWidget#page {{ background: {t.bg_top if t.dark else '#f5f1f9'}; }}")

    def reload(self) -> None:
        pass

    def present(self) -> None:
        self.reload()
        self.show()
        self.raise_()
        self.activateWindow()
