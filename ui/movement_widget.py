"""Movement breaks: estimated desk time, reminder actions and break countdown."""
from __future__ import annotations

from PySide6.QtCore import QTimer
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from app import clock
from services.reminder_service import MovementState

from .compact import CompactPanel, DetailDialog
from .theme import ui_font


class MovementCompact(CompactPanel):
    icon_name = "walk"
    title = "Movement"
    section = "movement"

    def __init__(self, ctx, parent=None):
        super().__init__("movement", ctx, parent)
        wb = ctx.wellbeing
        self.start_btn = self.make_button("Start 5-min break", "Start a movement break", wb.start_break, accent=True)
        self.later_btn = self.make_button("Later", "Remind me later", wb.snooze_movement)
        self.dismiss_btn = self.make_button("Dismiss", "Dismiss this reminder", wb.dismiss_movement)
        self.end_btn = self.make_button("End break", "End the break early", wb.cancel_break)
        self.start_btn.setGeometry(14, 58, 134, 26)
        self.later_btn.setGeometry(152, 58, 70, 26)
        self.dismiss_btn.setGeometry(self.W - 30, 8, 22, 22)
        self.dismiss_btn.setText("×")
        self.end_btn.setGeometry(self.W - 92, 30, 80, 24)
        self._tick = QTimer(self)
        self._tick.setInterval(1000)
        self._tick.timeout.connect(self._countdown)
        self.refresh()

    def icon_color(self) -> str:
        return self.theme.success

    def _countdown(self) -> None:
        if self.ctx.wellbeing.movement_state == MovementState.ON_BREAK:
            self.refresh()
        else:
            self._tick.stop()

    def refresh(self) -> None:
        wb = self.ctx.wellbeing
        tr = wb.movement
        state = wb.movement_state
        minutes = int(self.ctx.settings["movement_break_min"])
        self.start_btn.setText(f"Start {minutes}-min break")
        self.start_btn.setVisible(state == MovementState.DUE)
        self.later_btn.setVisible(state == MovementState.DUE)
        self.dismiss_btn.setVisible(state == MovementState.DUE)
        self.end_btn.setVisible(state == MovementState.ON_BREAK)
        if state == MovementState.ON_BREAK:
            self.title = "Movement break"
            self.value = clock.format_mmss(tr.break_remaining(clock.now()))
            self.sub = "Walk or stretch - I'll wait."
            total = max(1.0, tr.config.break_min * 60)
            self.progress = 1 - tr.break_remaining(clock.now()) / total
            if not self._tick.isActive():
                self._tick.start()
        elif state == MovementState.DUE:
            self.title = "Time to move"
            self.value = ""
            self.sub = ""
            self.progress = 0
        else:
            self.title = "Desk time (estimated)"
            self.value = f"{clock.format_duration(tr.desk_seconds)}"
            if not tr.config.enabled:
                self.sub = "Reminders off"
            elif tr.snoozed_until and tr.desk_seconds >= tr.interval_seconds:
                self.sub = f"Snoozed until {tr.snoozed_until.strftime('%H:%M')}"
            else:
                self.sub = f"Break reminder at {clock.format_duration(tr.interval_seconds)}"
            self.progress = tr.progress
        self.progress_color = "success" if state == MovementState.ON_BREAK else "warning" if tr.progress > 0.85 else "accent"
        tip = ("Estimated from keyboard and mouse activity. Pixel Desk cannot tell whether you are "
               "sitting or walking.")
        if not wb.idle_available:
            tip += " Idle detection is unavailable, so time Pixel Desk is running is used instead."
        self.setToolTip(tip)
        self.update()

    def paint_extra(self, p) -> None:
        if self.ctx.wellbeing.movement_state == MovementState.DUE:
            t = self.theme
            p.setFont(ui_font(10, QFont.Weight.DemiBold))
            p.setPen(t.c("text"))
            p.drawText(56, 44, "Stretch your legs?")
            return
        super().paint_extra(p)


class MovementDialog(DetailDialog):
    def __init__(self, ctx):
        super().__init__(ctx, "Movement", 480, 360)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(18, 16, 18, 16)
        self.headline = QLabel()
        self.headline.setFont(ui_font(13, QFont.Weight.DemiBold))
        self.body = QLabel()
        self.body.setWordWrap(True)
        self.history = QLabel()
        self.history.setWordWrap(True)
        self.history.setProperty("role", "dim")
        note = QLabel(
            "How this works: Pixel Desk adds up time while you are using the computer. If the keyboard and mouse "
            "are untouched for the idle-reset period, it assumes you stepped away and starts over. After the "
            "configured interval it suggests a short walk or stretch. It is an estimate - Pixel Desk cannot "
            "know whether you are physically sitting.")
        note.setWordWrap(True)
        note.setProperty("role", "dim")
        self.actions = QWidget()
        row = QHBoxLayout(self.actions)
        row.setContentsMargins(0, 4, 0, 4)
        wb = ctx.wellbeing
        self.start_btn = QPushButton()
        self.start_btn.setProperty("accent", "true")
        self.start_btn.clicked.connect(wb.start_break)
        later = QPushButton("Remind me later")
        later.clicked.connect(wb.snooze_movement)
        dismiss = QPushButton("Dismiss")
        dismiss.clicked.connect(wb.dismiss_movement)
        self.end_btn = QPushButton("End break early")
        self.end_btn.clicked.connect(wb.cancel_break)
        for b in (self.start_btn, later, dismiss, self.end_btn):
            row.addWidget(b)
        row.addStretch(1)
        self._due_buttons = (self.start_btn, later, dismiss)
        wb.movement_changed.connect(lambda: self.reload() if self.isVisible() else None)
        lay.addWidget(self.headline)
        lay.addWidget(self.body)
        lay.addWidget(self.actions)
        lay.addWidget(self.history)
        lay.addStretch(1)
        lay.addWidget(note)

    def reload(self) -> None:
        wb = self.ctx.wellbeing
        tr = wb.movement
        s = self.ctx.settings
        state = wb.movement_state
        if state == MovementState.ON_BREAK:
            self.headline.setText(f"On a movement break - {clock.format_mmss(tr.break_remaining(clock.now()))} left")
        elif state == MovementState.DUE:
            self.headline.setText("Time for a short walk or stretch")
        else:
            self.headline.setText(f"Estimated desk time: {clock.format_duration(tr.desk_seconds)}")
        self.start_btn.setText(f"Start {s['movement_break_min']}-minute break")
        for b in self._due_buttons:
            b.setVisible(state == MovementState.DUE)
        self.end_btn.setVisible(state == MovementState.ON_BREAK)
        self.body.setText(
            f"Reminder after {s['movement_interval_min']} min of activity · break {s['movement_break_min']} min · "
            f"snooze {s['movement_snooze_min']} min · resets after {s['movement_idle_reset_min']} idle min.")
        breaks = self.ctx.repo.movement_breaks_on(clock.today())
        done = [b for b in breaks if b["status"] == "completed"]
        lines = [f"Completed breaks today: {len(done)}"]
        for b in breaks[-6:]:
            lines.append(f"  {clock.parse_ts(b['started_at']).strftime('%H:%M')} - {b['status'].replace('_', ' ')}")
        self.history.setText("\n".join(lines))
