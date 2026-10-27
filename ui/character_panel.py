"""The companion's framed scene, speech bubble and focus timer."""
from __future__ import annotations

import random
import time
from datetime import datetime
from typing import Optional

from PySide6.QtCore import QPoint, QRect, QRectF, QSize, Qt, QTimer
from PySide6.QtGui import QFont, QFontMetrics, QLinearGradient, QMouseEvent, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QComboBox, QHBoxLayout, QToolButton, QWidget

from app import clock
from services.focus_timer import Phase, TimerState
from services.idle_detector import ActivityState
from services.reminder_service import MovementState

from .panel import Panel
from .pixel_art import draw_pixel_image, draw_pixel_text, icon_image, pixel_text_width, qicon, sprite_image
from .theme import blend, stylesheet, ui_font

FRIENDLY_LINES = [
    "Hi! I'm keeping you company.",
    "One small step at a time.",
    "You're doing better than you think.",
    "Remember to blink - I do!",
    "Tiny progress is still progress.",
    "Need a focus session? Press play.",
    "I believe in you!",
]


class CharacterPanel(Panel):
    W, H = 300, 440

    def __init__(self, ctx, parent=None):
        super().__init__("character", ctx, parent)
        self.setFixedSize(self.W, self.H)
        self.setMouseTracking(True)
        self._frame = 0
        self._temp_state: Optional[str] = None
        self._temp_until = 0.0
        self._bubble = ""
        self._bubble_action = ""
        self._bubble_until = 0.0
        self._last_spoke = time.monotonic()
        self._hover_bubble = False
        self._chip_rects: list = []
        self._stats = {"streak": 0, "level": 1, "focus": {"completed": 0, "seconds": 0}}

        self._anim = QTimer(self)
        self._anim.setInterval(190)
        self._anim.timeout.connect(self._advance)
        self._anim.start()

        # controls -----------------------------------------------------------
        self.task_box = QComboBox(self)
        self.task_box.setToolTip("Link the focus session to a task")
        self.task_box.setAccessibleName("Focus task")
        self.task_box.currentIndexChanged.connect(self._task_chosen)
        self.play = QToolButton(self)
        self.play.setIconSize(QSize(22, 22))
        self.play.setAccessibleName("Start or pause focus timer")
        self.play.clicked.connect(self._toggle)
        self.reset_btn = QToolButton(self)
        self.reset_btn.setIconSize(QSize(22, 22))
        self.reset_btn.setToolTip("Reset timer (an unfinished session gets no completion credit)")
        self.reset_btn.setAccessibleName("Reset focus timer")
        self.reset_btn.clicked.connect(lambda: self.ctx.focus.reset())

        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(6)
        row.addWidget(self.task_box, 1)
        row.addWidget(self.play)
        row.addWidget(self.reset_btn)
        holder = QWidget(self)
        holder.setLayout(row)
        holder.setGeometry(16, self.H - 50, self.W - 32, 34)

        ctx.focus.changed.connect(self.update)
        ctx.focus.changed.connect(self._sync_controls)
        ctx.focus.started.connect(self._on_focus_started)
        ctx.focus.session_finished.connect(self._on_session_finished)
        ctx.signals.companion.connect(self.say)
        ctx.focus.session_finished.connect(lambda _r: self.refresh())
        ctx.focus.session_cancelled.connect(lambda _r: self.refresh())
        self.apply_theme()
        self.refresh()

    # -- theming / data --------------------------------------------------------
    def apply_theme(self) -> None:
        t = self.theme
        self.setStyleSheet(stylesheet(t))
        self.reset_btn.setIcon(qicon("stop", t.text_dim, t.outline, 22))
        self._sync_controls()
        self.update()

    def reload_tasks(self) -> None:
        current = self.ctx.focus.timer.task_id
        parts = self.ctx.repo.tasks_for_day(clock.today())
        self.task_box.blockSignals(True)
        self.task_box.clear()
        self.task_box.addItem("No task linked", None)
        for task in parts["pending"] + parts["upcoming"]:
            self.task_box.addItem(task.title, task.id)
        idx = self.task_box.findData(current) if current is not None else 0
        self.task_box.setCurrentIndex(max(0, idx))
        self.task_box.blockSignals(False)

    def refresh(self) -> None:
        self.reload_tasks()
        self._stats = {
            "streak": self.ctx.progress.overall_streak()[0],
            "level": self.ctx.progress.level()[0],
            "focus": self.ctx.repo.focus_summary(clock.today()),
        }
        self.update()

    def _task_chosen(self) -> None:
        self.ctx.focus.set_task(self.task_box.currentData())

    def _toggle(self) -> None:
        self.ctx.focus.toggle(self.task_box.currentData())

    def _sync_controls(self) -> None:
        t = self.theme
        running = self.ctx.focus.timer.state == TimerState.RUNNING
        self.play.setIcon(qicon("pause" if running else "play", t.accent, t.outline, 22))
        self.play.setToolTip("Pause" if running else ("Resume" if self.ctx.focus.timer.state == TimerState.PAUSED
                                                      else "Start focus session"))
        self.task_box.setEnabled(self.ctx.focus.timer.phase == Phase.FOCUS)

    # -- companion behaviour -------------------------------------------------------
    def say(self, state: str, message: str, action: str = "", seconds: float = 14.0) -> None:
        s = self.ctx.settings
        if state and state != "idle" and s["animations_enabled"]:
            self._temp_state = state
            self._temp_until = time.monotonic() + (6.0 if state in ("happy", "achievement", "wave") else seconds)
        if message and s["character_messages"]:
            self._bubble = message
            self._bubble_action = action
            self._bubble_until = time.monotonic() + seconds
            self._last_spoke = time.monotonic()
        self.update()

    def _on_focus_started(self) -> None:
        if self.ctx.focus.timer.phase == Phase.FOCUS:
            task = self.task_box.currentText() if self.task_box.currentData() else ""
            self.say("working", f"Focusing on “{task}”. I'll keep quiet." if task else "Focus time! I'll keep quiet.")

    def _on_session_finished(self, record) -> None:
        if record.kind == "focus":
            if self.ctx.settings["focus_celebration"]:
                self.say("achievement", "Session complete! Stretch, sip some water, breathe.", "")
        else:
            self.say("idle", "Break's over. Ready when you are.")

    def base_state(self) -> str:
        movement = self.ctx.wellbeing.movement_state
        if movement in (MovementState.DUE, MovementState.ON_BREAK):
            return "movement"
        timer = self.ctx.focus.timer
        if timer.state == TimerState.RUNNING:
            return "working" if timer.phase == Phase.FOCUS else "idle"
        st = self.ctx.monitor_status
        hour = datetime.now().hour
        if (st is not None and st.state in (ActivityState.IDLE, ActivityState.LOCKED)) or 1 <= hour < 5:
            return "sleepy"
        return "idle"

    def current_state(self) -> str:
        if self._temp_state and time.monotonic() < self._temp_until:
            return self._temp_state
        self._temp_state = None
        return self.base_state()

    def _advance(self) -> None:
        if not self.isVisible():
            return
        s = self.ctx.settings
        if s["animations_enabled"] and not s["reduced_motion"]:
            self._frame = (self._frame + 1) % 10_000
        if self._bubble and time.monotonic() > self._bubble_until:
            self._bubble = ""
        self.update()

    # -- geometry -----------------------------------------------------------
    def _scene_rect(self) -> QRectF:
        return QRectF(16, 44, self.W - 32, 232)

    def _sprite_rect(self) -> QRect:
        sr = self._scene_rect()
        size = 160
        return QRect(int(sr.center().x() - size / 2), int(sr.bottom() - size - 6), size, size)

    def _bubble_rect(self) -> QRectF:
        if not self._bubble:
            return QRectF()
        f = ui_font(9)
        fm = QFontMetrics(f)
        sr = self._scene_rect()
        width = sr.width() - 24
        text_rect = fm.boundingRect(QRect(0, 0, int(width - 20), 200), Qt.TextFlag.TextWordWrap, self._bubble)
        h = min(text_rect.height(), fm.lineSpacing() * 3) + 16
        return QRectF(sr.left() + 12, sr.top() + 10, width, h)

    # -- painting -----------------------------------------------------------
    def paint_content(self, p: QPainter) -> None:
        t = self.theme
        s = self.ctx.settings
        # header: name, level and streak chips
        p.setFont(ui_font(10.5, QFont.Weight.DemiBold))
        p.setPen(t.c("text"))
        p.drawText(QRectF(18, 12, 140, 24), Qt.AlignmentFlag.AlignVCenter, s["character_name"] or "Pip")
        self._paint_chips(p)

        sr = self._scene_rect()
        path = QPainterPath()
        path.addRoundedRect(sr, 10, 10)
        hour = datetime.now().hour
        sky = QLinearGradient(sr.topLeft(), sr.bottomLeft())
        if 6 <= hour < 18:
            sky.setColorAt(0, blend(t.c("bg_glow"), t.c("accent"), 0.25))
            sky.setColorAt(1, t.c("bg_glow"))
        else:
            sky.setColorAt(0, t.c("bg_bottom"))
            sky.setColorAt(1, t.c("bg_glow"))
        p.fillPath(path, sky)
        p.save()
        p.setClipPath(path)
        # tiny stars + moon/sun in the scene
        rnd = random.Random(3)
        p.setPen(Qt.PenStyle.NoPen)
        twinkle = (self._frame // 6) % 4
        for i in range(18):
            x, y = sr.left() + rnd.random() * sr.width(), sr.top() + rnd.random() * sr.height() * 0.55
            a = 0.25 + (0.4 if i % 4 == twinkle else 0.0)
            p.setBrush(t.c("star", a))
            p.drawRect(QRectF(int(x), int(y), 2, 2))
        orb = "moon" if not (6 <= hour < 18) else "star"
        draw_pixel_image(p, icon_image(orb, t.warning, t.outline), QRect(int(sr.right() - 44), int(sr.top() + 14), 24, 24))
        # floor
        p.setBrush(t.c("panel", 0.9))
        floor_y = sr.bottom() - 18
        p.drawRect(QRectF(sr.left(), floor_y, sr.width(), 18))
        p.setBrush(t.c("border", 0.9))
        for x in range(int(sr.left()), int(sr.right()), 12):
            p.drawRect(x, int(floor_y), 6, 2)
        # sprite
        state = self.current_state()
        img = sprite_image(state, self._frame % 48, s["character_hair"], s["character_outfit"], t.outline, t.accent2)
        draw_pixel_image(p, img, self._sprite_rect())
        p.restore()
        p.setPen(QPen(t.c("border"), 1))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawPath(path)
        # pixel corner brackets
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(t.c("accent", 0.8))
        for cx, cy, dx, dy in ((sr.left(), sr.top(), 1, 1), (sr.right(), sr.top(), -1, 1),
                               (sr.left(), sr.bottom(), 1, -1), (sr.right(), sr.bottom(), -1, -1)):
            p.drawRect(QRectF(cx - (3 if dx < 0 else 0), cy - (3 if dy < 0 else 0), 10 * dx, 3 * dy).normalized())
            p.drawRect(QRectF(cx - (3 if dx < 0 else 0), cy - (3 if dy < 0 else 0), 3 * dx, 10 * dy).normalized())

        self._paint_bubble(p)
        self._paint_timer(p)

    def _paint_chips(self, p: QPainter) -> None:
        t = self.theme
        cur = self._stats["streak"]
        x = self.W - 18
        chips = [("flame", f"{cur}", "Day streak - click for habits", t.warning)]
        if self.ctx.settings["xp_enabled"]:
            lvl = self._stats["level"]
            chips.insert(0, ("star", f"LV{lvl}", "Level", t.accent))
        self._chip_rects = []
        for icon, text, tip, color in reversed(chips):
            w = pixel_text_width(text, 2) + 30
            rect = QRectF(x - w, 14, w, 22)
            p.setBrush(t.c("bg_bottom", 0.55))
            p.setPen(QPen(t.c("border"), 1))
            p.drawRoundedRect(rect, 11, 11)
            draw_pixel_image(p, icon_image(icon, color, t.outline), QRect(int(rect.left() + 6), int(rect.top() + 5), 12, 12))
            draw_pixel_text(p, text, QPoint(int(rect.left() + 22), int(rect.top() + 4)), 2, t.c("text"))
            self._chip_rects.append((rect, tip))
            x -= w + 6

    def _paint_bubble(self, p: QPainter) -> None:
        if not self._bubble:
            return
        t = self.theme
        r = self._bubble_rect()
        path = QPainterPath()
        path.addRoundedRect(r, 8, 8)
        tail = QPainterPath()
        sx = self._sprite_rect().center().x()
        tail.moveTo(sx - 6, r.bottom() - 1)
        tail.lineTo(sx + 6, r.bottom() - 1)
        tail.lineTo(sx - 2, r.bottom() + 10)
        tail.closeSubpath()
        path = path.united(tail)
        fill = t.c("star") if t.dark else t.c("panel")
        p.setBrush(fill)
        p.setPen(QPen(t.c("accent") if self._hover_bubble else t.c("outline"), 1.5))
        p.drawPath(path)
        p.setFont(ui_font(9))
        p.setPen(t.c("outline") if t.dark else t.c("text"))
        p.drawText(r.adjusted(10, 8, -10, -6), Qt.TextFlag.TextWordWrap | Qt.AlignmentFlag.AlignLeft, self._bubble)
        if self._bubble_action:
            p.setBrush(t.c("accent2"))
            p.setPen(Qt.PenStyle.NoPen)
            p.drawRect(QRectF(r.right() - 9, r.bottom() - 9, 4, 4))

    def _paint_timer(self, p: QPainter) -> None:
        t = self.theme
        timer = self.ctx.focus.timer
        top = 290
        phase = "FOCUS" if timer.phase == Phase.FOCUS else "BREAK"
        if timer.state == TimerState.PAUSED:
            phase += " - PAUSED"
        color = t.c("accent") if timer.phase == Phase.FOCUS else t.c("success")
        draw_pixel_text(p, phase, QPoint(18, top), 2, t.c("text_dim"))
        txt = clock.format_mmss(timer.remaining())
        scale = 5
        w = pixel_text_width(txt, scale)
        draw_pixel_text(p, txt, QPoint(int((self.W - w) / 2), top + 22), scale, t.c("text"), shadow=t.c("outline", 0.7))
        # progress
        bar = QRectF(18, top + 68, self.W - 36, 6)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(t.c("border", 0.8))
        p.drawRoundedRect(bar, 3, 3)
        prog = timer.progress()
        if prog > 0:
            p.setBrush(color)
            p.drawRoundedRect(QRectF(bar.left(), bar.top(), max(6.0, bar.width() * prog), bar.height()), 3, 3)
        # today's focus summary
        summary = self._stats["focus"]
        p.setFont(ui_font(8.5))
        p.setPen(t.c("text_dim"))
        p.drawText(QRectF(18, top + 78, self.W - 36, 18), Qt.AlignmentFlag.AlignLeft,
                   f"Today: {summary['completed']} sessions · {clock.format_duration(summary['seconds'])} focused")

    # -- interaction -------------------------------------------------------------
    def mouseMoveEvent(self, e: QMouseEvent) -> None:  # noqa: N802
        if not self._edit_mode:
            pos = e.position()
            over_bubble = bool(self._bubble) and self._bubble_rect().contains(pos)
            over_sprite = self._sprite_rect().contains(pos.toPoint())
            over_chip = any(r.contains(pos) for r, _ in self._chip_rects)
            if over_bubble != self._hover_bubble:
                self._hover_bubble = over_bubble
                self.update()
            self.setCursor(Qt.CursorShape.PointingHandCursor if (over_bubble and self._bubble_action) or over_sprite
                           or over_chip else Qt.CursorShape.ArrowCursor)
            for r, tip in self._chip_rects:
                if r.contains(pos):
                    self.setToolTip(tip)
                    break
            else:
                self.setToolTip("Click me!" if over_sprite else "")
        super().mouseMoveEvent(e)

    def mouseReleaseEvent(self, e: QMouseEvent) -> None:  # noqa: N802
        if self._edit_mode or e.button() != Qt.MouseButton.LeftButton:
            super().mouseReleaseEvent(e)
            return
        pos = e.position()
        if self._bubble and self._bubble_rect().contains(pos):
            if self._bubble_action:
                self.ctx.signals.open_section.emit(self._bubble_action)
            self._bubble = ""
            self.update()
        elif self._sprite_rect().contains(pos.toPoint()):
            self.say("wave", random.choice(FRIENDLY_LINES), "", seconds=7)
        elif any(r.contains(pos) for r, _ in self._chip_rects):
            self.ctx.signals.open_section.emit("streaks")
        super().mouseReleaseEvent(e)
