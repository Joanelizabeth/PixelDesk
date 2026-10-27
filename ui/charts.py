"""Small custom-painted charts used in the detail dialogs."""
from __future__ import annotations

from datetime import date
from typing import Callable, Optional, Sequence

from PySide6.QtCore import QRectF, QSize, Qt
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QSizePolicy, QToolTip, QWidget

from .theme import Theme, ui_font


class _Chart(QWidget):
    def __init__(self, theme: Theme, height: int = 140, parent=None):
        super().__init__(parent)
        self.theme = theme
        self.setMinimumHeight(height)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setMouseTracking(True)
        self._tips: list[tuple[QRectF, str]] = []

    def mouseMoveEvent(self, e):  # noqa: N802
        for rect, tip in self._tips:
            if rect.contains(e.position()):
                QToolTip.showText(e.globalPosition().toPoint(), tip, self)
                return
        QToolTip.hideText()


class BarChart(_Chart):
    """Vertical bars with labels underneath, e.g. a 7-day history."""

    def __init__(self, theme: Theme, height: int = 150, fmt: Callable[[float], str] = str, parent=None):
        super().__init__(theme, height, parent)
        self.labels: list[str] = []
        self.values: list[float] = []
        self.colors: list[QColor] = []
        self.goal: Optional[float] = None
        self.fmt = fmt

    def set_data(self, labels: Sequence[str], values: Sequence[float], colors: Sequence[QColor] | None = None,
                 goal: Optional[float] = None) -> None:
        self.labels, self.values = list(labels), list(values)
        self.colors = list(colors) if colors else [self.theme.c("accent")] * len(values)
        self.goal = goal
        self.update()

    def paintEvent(self, _e):  # noqa: N802
        t = self.theme
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        self._tips = []
        n = len(self.values)
        if not n:
            return
        top, bottom = 18, self.height() - 22
        maxv = max(max(self.values), self.goal or 0, 1e-9)
        slot = self.width() / n
        bw = min(34.0, slot * 0.55)
        p.setFont(ui_font(8))
        if self.goal:
            gy = bottom - (bottom - top) * self.goal / maxv
            p.setPen(QPen(t.c("text_dim", 0.6), 1, Qt.PenStyle.DashLine))
            p.drawLine(0, int(gy), self.width(), int(gy))
        for i, (label, v) in enumerate(zip(self.labels, self.values)):
            x = slot * i + (slot - bw) / 2
            h = (bottom - top) * (v / maxv)
            rect = QRectF(x, bottom - h, bw, max(h, 2 if v > 0 else 0))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(t.c("border", 0.5))
            p.drawRoundedRect(QRectF(x, top, bw, bottom - top), 4, 4)
            p.setBrush(self.colors[i])
            if v > 0:
                p.drawRoundedRect(rect, 4, 4)
            p.setPen(t.c("text_dim"))
            p.drawText(QRectF(slot * i, bottom + 4, slot, 16), Qt.AlignmentFlag.AlignCenter, label)
            self._tips.append((QRectF(slot * i, top, slot, bottom - top), f"{label}: {self.fmt(v)}"))


class HourlyTimeline(_Chart):
    """24 columns showing active (accent) and idle (dim) time per hour."""

    def __init__(self, theme: Theme, parent=None):
        super().__init__(theme, 110, parent)
        self.hours: list[tuple[float, float]] = [(0.0, 0.0)] * 24

    def set_data(self, hours: list[tuple[float, float]]) -> None:
        self.hours = hours
        self.update()

    def paintEvent(self, _e):  # noqa: N802
        from app.clock import format_duration

        t = self.theme
        p = QPainter(self)
        self._tips = []
        top, bottom = 6, self.height() - 22
        slot = self.width() / 24
        bw = max(3.0, slot - 3)
        for h, (active, idle) in enumerate(self.hours):
            x = slot * h + (slot - bw) / 2
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(t.c("border", 0.35))
            p.drawRect(QRectF(x, top, bw, bottom - top))
            ah = (bottom - top) * min(active, 3600) / 3600
            ih = (bottom - top) * min(idle, 3600 - min(active, 3600)) / 3600
            p.setBrush(t.c("accent"))
            p.drawRect(QRectF(x, bottom - ah, bw, ah))
            p.setBrush(t.c("text_dim", 0.45))
            p.drawRect(QRectF(x, bottom - ah - ih, bw, ih))
            if h % 3 == 0:
                p.setPen(t.c("text_dim"))
                p.setFont(ui_font(7.5))
                p.drawText(QRectF(slot * h - 6, bottom + 4, slot + 12, 14), Qt.AlignmentFlag.AlignCenter, f"{h:02d}")
            self._tips.append((QRectF(slot * h, top, slot, bottom - top),
                               f"{h:02d}:00 - active {format_duration(active)}, idle {format_duration(idle)}"))


class StackedBar(_Chart):
    """One horizontal bar split into labelled segments with a legend."""

    def __init__(self, theme: Theme, parent=None):
        super().__init__(theme, 64, parent)
        self.segments: list[tuple[str, float, QColor]] = []

    def set_data(self, segments: list[tuple[str, float, QColor]]) -> None:
        self.segments = segments
        self.update()

    def paintEvent(self, _e):  # noqa: N802
        from app.clock import format_duration

        t = self.theme
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        self._tips = []
        total = sum(v for _, v, _ in self.segments)
        bar = QRectF(0, 4, self.width(), 14)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(t.c("border", 0.5))
        p.drawRoundedRect(bar, 7, 7)
        x = 0.0
        if total > 0:
            for label, v, color in self.segments:
                w = bar.width() * v / total
                if w <= 0:
                    continue
                p.setBrush(color)
                p.drawRect(QRectF(x, bar.top(), w, bar.height()))
                self._tips.append((QRectF(x, bar.top(), w, bar.height()),
                                   f"{label}: {format_duration(v)} ({v / total:.0%})"))
                x += w
        # legend
        p.setFont(ui_font(8.5))
        lx, ly = 0.0, 30.0
        for label, v, color in self.segments:
            text = f"{label} {format_duration(v)}"
            w = p.fontMetrics().horizontalAdvance(text) + 22
            if lx + w > self.width():
                lx, ly = 0.0, ly + 18
            p.setBrush(color)
            p.setPen(Qt.PenStyle.NoPen)
            p.drawRect(QRectF(lx, ly + 4, 8, 8))
            p.setPen(t.c("text_dim"))
            p.drawText(QRectF(lx + 12, ly, w, 16), Qt.AlignmentFlag.AlignVCenter, text)
            lx += w + 6

    def sizeHint(self) -> QSize:  # noqa: N802
        return QSize(300, 64)


class MonthHeatmap(_Chart):
    """Calendar month; cell intensity = completions that day / max."""

    def __init__(self, theme: Theme, parent=None):
        super().__init__(theme, 170, parent)
        self.weeks: list[list[Optional[date]]] = []
        self.counts: dict[date, int] = {}
        self.max_count = 1
        self.today: Optional[date] = None

    def set_data(self, weeks, counts: dict[date, int], max_count: int, today: date) -> None:
        self.weeks, self.counts, self.max_count, self.today = weeks, counts, max(1, max_count), today
        self.update()

    def paintEvent(self, _e):  # noqa: N802
        t = self.theme
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        self._tips = []
        cell = min(22.0, (self.width() - 6) / 7 - 4, (self.height() - 22) / max(1, len(self.weeks)) - 4)
        p.setFont(ui_font(7.5))
        p.setPen(t.c("text_dim"))
        for i, d in enumerate("MTWTFSS"):
            p.drawText(QRectF(i * (cell + 4), 0, cell, 14), Qt.AlignmentFlag.AlignCenter, d)
        for r, week in enumerate(self.weeks):
            for c, d in enumerate(week):
                rect = QRectF(c * (cell + 4), 18 + r * (cell + 4), cell, cell)
                if d is None:
                    continue
                n = self.counts.get(d, 0)
                if n:
                    col = t.c("success", 0.35 + 0.65 * min(1.0, n / self.max_count))
                else:
                    col = t.c("border", 0.45)
                p.setPen(QPen(t.c("accent"), 1.5) if d == self.today else Qt.PenStyle.NoPen)
                p.setBrush(col)
                p.drawRoundedRect(rect, 4, 4)
                if self.today and d > self.today:
                    p.setBrush(t.c("bg_bottom", 0.5))
                    p.setPen(Qt.PenStyle.NoPen)
                    p.drawRoundedRect(rect, 4, 4)
                self._tips.append((rect, f"{d.strftime('%a %d %b')}: {n} check-in{'s' if n != 1 else ''}"))
