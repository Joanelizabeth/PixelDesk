"""Habits, streaks, monthly heatmap, XP and badges."""
from __future__ import annotations

from datetime import date

from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QCheckBox, QGridLayout, QHBoxLayout, QLabel, QLineEdit, QProgressBar, QPushButton, QScrollArea, QVBoxLayout,
    QWidget,
)

from app import clock
from services.streak_service import (
    ACHIEVEMENTS, current_streak, longest_streak, month_grid, weekly_completion,
)

from .charts import MonthHeatmap
from .compact import DetailDialog
from .pixel_art import icon_pixmap
from .theme import ui_font


class StreaksDialog(DetailDialog):
    def __init__(self, ctx):
        super().__init__(ctx, "Streaks & habits", 640, 760)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        page = QWidget()
        page.setObjectName("page")
        scroll.setWidget(page)
        outer.addWidget(scroll)
        self.lay = QVBoxLayout(page)
        self.lay.setContentsMargins(18, 16, 18, 16)
        self.lay.setSpacing(10)

        self.headline = QLabel()
        self.headline.setFont(ui_font(14, QFont.Weight.DemiBold))
        self.subline = QLabel()
        self.subline.setProperty("role", "dim")
        self.lay.addWidget(self.headline)
        self.lay.addWidget(self.subline)

        self.level_label = QLabel()
        self.level_bar = QProgressBar()
        self.level_bar.setTextVisible(False)
        self.level_bar.setFixedHeight(6)
        self.lay.addWidget(self.level_label)
        self.lay.addWidget(self.level_bar)

        self.lay.addWidget(self._caption("Today's check-ins"))
        self.habit_grid = QGridLayout()
        self.habit_grid.setHorizontalSpacing(14)
        self.lay.addLayout(self.habit_grid)
        add_row = QHBoxLayout()
        self.new_habit = QLineEdit()
        self.new_habit.setPlaceholderText("New habit, e.g. “Read for 20 minutes”")
        self.new_habit.setMaxLength(60)
        self.new_habit.returnPressed.connect(self._add_habit)
        add = QPushButton("Add habit")
        add.clicked.connect(self._add_habit)
        add_row.addWidget(self.new_habit, 1)
        add_row.addWidget(add)
        self.lay.addLayout(add_row)
        hint = QLabel("Choose which habits count toward the overall streak in Settings › Habits. "
                      "A streak only ends after a whole day passes with no check-in.")
        hint.setProperty("role", "dim")
        hint.setWordWrap(True)
        self.lay.addWidget(hint)

        self.month_caption = self._caption("")
        self.lay.addWidget(self.month_caption)
        self.heatmap = MonthHeatmap(ctx.theme)
        self.lay.addWidget(self.heatmap)

        self.lay.addWidget(self._caption("Badges"))
        self.badges = QGridLayout()
        self.lay.addLayout(self.badges)
        self.lay.addStretch(1)

    def _caption(self, text: str) -> QLabel:
        lab = QLabel(text)
        lab.setProperty("role", "dim")
        return lab

    @staticmethod
    def _clear(grid: QGridLayout) -> None:
        while grid.count():
            item = grid.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def reload(self) -> None:
        repo, t = self.ctx.repo, self.ctx.theme
        today = clock.today()
        cur, longest = self.ctx.progress.overall_streak(today)
        habits = repo.list_habits()
        habit_days = {h.id: repo.habit_days(h.id) for h in habits}
        week = weekly_completion(habit_days, today)
        self.headline.setText(f"{cur}-day streak" if cur else "Start a streak today")
        self.subline.setText(f"Longest streak {longest} days · this week {week:.0%} of habit check-ins done")

        xp_on = self.ctx.settings["xp_enabled"]
        lvl, into, span, xp = self.ctx.progress.level()
        self.level_label.setVisible(xp_on)
        self.level_bar.setVisible(xp_on)
        self.level_label.setText(f"Level {lvl} · {xp} XP · {span - into} XP to level {lvl + 1}")
        self.level_bar.setMaximum(span)
        self.level_bar.setValue(into)

        self._clear(self.habit_grid)
        done_today = repo.habits_done_on(today)
        if not habits:
            self.habit_grid.addWidget(self._caption("No habits yet - add one below."), 0, 0)
        for row, h in enumerate(habits):
            box = QCheckBox(h.name)
            box.setChecked(h.id in done_today)
            box.toggled.connect(lambda on, hid=h.id: self._toggle(hid, on))
            days = habit_days[h.id]
            info = QLabel(f"{current_streak(days, today)} day streak · best {longest_streak(days)}"
                          + ("" if h.counts_toward_streak else " · not in overall streak"))
            info.setProperty("role", "dim")
            self.habit_grid.addWidget(box, row, 0)
            self.habit_grid.addWidget(info, row, 1)

        # month heatmap: number of habit check-ins per day
        counts: dict[date, int] = {}
        for days in habit_days.values():
            for d in days:
                if d.year == today.year and d.month == today.month:
                    counts[d] = counts.get(d, 0) + 1
        self.month_caption.setText(today.strftime("%B %Y"))
        self.heatmap.theme = t
        self.heatmap.set_data(month_grid(today.year, today.month), counts, max(1, len(habits)), today)

        self._clear(self.badges)
        unlocked = repo.achievements()
        for i, a in enumerate(ACHIEVEMENTS):
            have = a.key in unlocked
            w = QWidget()
            l = QHBoxLayout(w)
            l.setContentsMargins(0, 2, 0, 2)
            icon = QLabel()
            color = t.warning if have else t.border
            icon.setPixmap(icon_pixmap(a.icon if a.icon in ("star", "rocket", "code", "moon", "flame", "heart", "drop",
                                                            "walk") else "star", color, t.outline, 24))
            text = QLabel(f"<b>{a.title}</b><br><span style='color:{t.text_dim}'>{a.description}</span>")
            text.setEnabled(have)
            l.addWidget(icon)
            l.addWidget(text, 1)
            w.setToolTip("Unlocked " + clock.parse_ts(unlocked[a.key]).strftime("%d %b %Y") if have else "Locked")
            self.badges.addWidget(w, i // 2, i % 2)

    def _toggle(self, habit_id: int, on: bool) -> None:
        if self.ctx.progress.set_habit(habit_id, clock.today(), on) and on:
            cur, _ = self.ctx.progress.overall_streak()
            self.ctx.say("happy", f"Checked in! Streak: {cur} day{'s' if cur != 1 else ''}.", "streaks")
        self.ctx.notify_changed("habits")

    def _add_habit(self) -> None:
        name = self.new_habit.text().strip()
        if not name:
            return
        try:
            self.ctx.repo.add_habit(name)
        except Exception:
            self.new_habit.selectAll()
            return
        self.new_habit.clear()
        self.ctx.notify_changed("habits")
