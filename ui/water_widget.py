"""Hydration: compact widget with one-click logging + history window."""
from __future__ import annotations

from PySide6.QtCore import QRect
from PySide6.QtGui import QFont, QPainter
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QVBoxLayout

from app import clock

from .charts import BarChart
from .compact import CompactPanel, DetailDialog
from .pixel_art import draw_pixel_image, icon_image
from .theme import ui_font


class WaterCompact(CompactPanel):
    icon_name = "drop"
    title = "Water"
    section = "water"

    def __init__(self, ctx, parent=None):
        super().__init__("water", ctx, parent)
        self.add_btn = self.make_button("+", "Log one serving", self._log, accent=True)
        self.add_btn.setGeometry(self.W - 44, 12, 32, 28)
        self.add_btn.setAccessibleName("Log a serving of water")
        self.undo_btn = self.make_button("Undo", "Undo the most recent entry", self._undo)
        self.undo_btn.setGeometry(self.W - 64, 46, 52, 22)
        self.status = {}
        self.refresh()

    def icon_color(self) -> str:
        return self.theme.water

    def _log(self) -> None:
        self.ctx.wellbeing.log_water()

    def _undo(self) -> None:
        self.ctx.wellbeing.undo_water()

    def refresh(self) -> None:
        st = self.ctx.wellbeing.water_status()
        self.status = st
        self.value = f"{st['servings']} / {st['goal']}"
        self.sub = f"{st['ml'] / 1000:.2f} L of {st['goal_ml'] / 1000:.1f} L"
        self.progress = st["ml"] / st["goal_ml"] if st["goal_ml"] else 0
        self.undo_btn.setEnabled(st["servings"] > 0)
        self.update()

    def paint_extra(self, p: QPainter) -> None:
        # one tiny drop per serving of the goal
        t = self.theme
        goal = max(1, min(self.status.get("goal", 8), 12))
        filled = self.status.get("servings", 0)
        size = 12
        gap = (self.W - 28 - goal * size) / max(1, goal - 1)
        gap = min(gap, 6)
        for i in range(goal):
            color = t.water if i < filled else t.border
            draw_pixel_image(p, icon_image("drop", color, t.outline), QRect(int(14 + i * (size + gap)), self.H - 22, size, size))


class WaterDialog(DetailDialog):
    def __init__(self, ctx):
        super().__init__(ctx, "Water", 520, 420)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(18, 16, 18, 16)
        self.headline = QLabel()
        self.headline.setFont(ui_font(13, QFont.Weight.DemiBold))
        self.sub = QLabel()
        self.sub.setProperty("role", "dim")
        lay.addWidget(self.headline)
        lay.addWidget(self.sub)
        row = QHBoxLayout()
        log = QPushButton("Log a serving")
        log.setProperty("accent", "true")
        log.clicked.connect(ctx.wellbeing.log_water)
        undo = QPushButton("Undo last")
        undo.clicked.connect(ctx.wellbeing.undo_water)
        settings = QPushButton("Goal & reminders…")
        settings.clicked.connect(lambda: ctx.signals.open_section.emit("settings:wellbeing"))
        row.addWidget(log)
        row.addWidget(undo)
        row.addStretch(1)
        row.addWidget(settings)
        lay.addLayout(row)
        lay.addSpacing(8)
        cap = QLabel("Last 14 days")
        cap.setProperty("role", "dim")
        lay.addWidget(cap)
        self.chart = BarChart(ctx.theme, 170, fmt=lambda v: f"{v / 1000:.2f} L")
        lay.addWidget(self.chart)
        note = QLabel("The default goal is a common starting point, not medical advice. "
                      "Adjust it to what suits you.")
        note.setWordWrap(True)
        note.setProperty("role", "dim")
        lay.addStretch(1)
        lay.addWidget(note)

    def reload(self) -> None:
        st = self.ctx.wellbeing.water_status()
        self.headline.setText(f"{st['servings']} of {st['goal']} servings today")
        self.sub.setText(f"{st['ml']} ml logged · goal {st['goal_ml']} ml ({st['serving_ml']} ml per serving)")
        days = clock.days_back(clock.today(), 14)
        hist = self.ctx.repo.water_history(days)
        t = self.ctx.theme
        values = [hist.get(d.isoformat(), 0) for d in days]
        colors = [t.c("water") if v >= st["goal_ml"] else t.c("water", 0.55) for v in values]
        self.chart.theme = t
        self.chart.set_data([d.strftime("%d") for d in days], values, colors, goal=st["goal_ml"])
