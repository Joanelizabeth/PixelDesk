"""Live clock, date and a gentle rotating message."""
from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import QPoint, QRectF, Qt, QTimer
from PySide6.QtGui import QFont, QMouseEvent, QPainter

from .panel import Panel
from .pixel_art import draw_pixel_text, pixel_text_width
from .theme import ui_font


def greeting_for(hour: int) -> str:
    if 5 <= hour < 12:
        return "Good morning"
    if 12 <= hour < 17:
        return "Good afternoon"
    if 17 <= hour < 22:
        return "Good evening"
    return "Hello, night owl"


class ClockPanel(Panel):
    card = False
    W, H = 380, 150

    def __init__(self, ctx, parent=None):
        super().__init__("clock", ctx, parent)
        self.setFixedSize(self.W, self.H)
        self.setToolTip("Click to see another message")
        self._msg_index = datetime.now().hour
        self._last_minute = -1
        self._timer = QTimer(self)
        self._timer.setInterval(1000)
        self._timer.timeout.connect(self._tick)
        self._timer.start()

    def _tick(self) -> None:
        now = datetime.now()
        if now.minute != self._last_minute:
            self._last_minute = now.minute
            if now.minute % 30 == 0:
                self._msg_index += 1
        self.update()

    def message(self) -> str:
        msgs = [m for m in self.ctx.settings["greeting_messages"] if str(m).strip()]
        return msgs[self._msg_index % len(msgs)] if msgs else ""

    def paint_content(self, p: QPainter) -> None:
        t = self.theme
        now = datetime.now()
        hhmm = now.strftime("%H:%M")
        scale = 9
        w = pixel_text_width(hhmm, scale)
        x0 = self.W - w - 8
        draw_pixel_text(p, hhmm, QPoint(x0, 6), scale, t.c("text"), shadow=t.c("outline", 0.75))
        # seconds as a row of 6 pixel ticks (one per 10 s) under the clock
        p.setPen(Qt.PenStyle.NoPen)
        for i in range(6):
            p.setBrush(t.c("accent") if now.second >= i * 10 else t.c("border"))
            p.drawRect(x0 + w - (6 - i) * 10, 6 + 7 * scale + 8, 6, 3)

        p.setFont(ui_font(10.5, QFont.Weight.DemiBold))
        p.setPen(t.c("text"))
        name = self.ctx.settings["user_name"].strip()
        greeting = greeting_for(now.hour) + (f", {name}" if name else "")
        p.drawText(QRectF(0, 86, self.W - 8, 20), Qt.AlignmentFlag.AlignRight, now.strftime("%A, %d %B"))
        p.setFont(ui_font(9.5))
        p.setPen(t.c("text_dim"))
        p.drawText(QRectF(0, 106, self.W - 8, 20), Qt.AlignmentFlag.AlignRight, greeting + ".")
        msg = self.message()
        if msg:
            p.setPen(t.c("accent"))
            p.setFont(ui_font(9.5, QFont.Weight.Normal))
            f = p.font()
            f.setItalic(True)
            p.setFont(f)
            p.drawText(QRectF(0, 126, self.W - 8, 20), Qt.AlignmentFlag.AlignRight, msg)

    def mouseReleaseEvent(self, e: QMouseEvent) -> None:  # noqa: N802
        if not self._edit_mode and e.button() == Qt.MouseButton.LeftButton:
            self._msg_index += 1
            self.update()
        super().mouseReleaseEvent(e)
