"""Daily tasks: compact widget + full task manager window."""
from __future__ import annotations

from typing import Optional

from PySide6.QtCore import QDate, QRectF, Qt
from PySide6.QtGui import QBrush, QFont, QPainter, QPen
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDateEdit, QDialog, QDialogButtonBox, QFormLayout, QHBoxLayout, QHeaderView, QLabel,
    QLineEdit, QMessageBox, QProgressBar, QPushButton, QSpinBox, QTabWidget, QTreeWidget, QTreeWidgetItem,
    QVBoxLayout,
)

from app import clock
from database.repository import Task

from .compact import CompactPanel, DetailDialog
from .theme import stylesheet, ui_font

PRIORITIES = ["None", "Low", "Medium", "High"]


def task_meta(task: Task) -> str:
    bits = []
    if task.estimate_minutes:
        bits.append(f"est {clock.format_duration(task.estimate_minutes * 60)}")
    if task.focus_seconds:
        bits.append(f"{clock.format_duration(task.focus_seconds)} focused")
    if task.due_date:
        bits.append(f"due {task.due_date}")
    if task.category:
        bits.append(task.category)
    return " · ".join(bits)


class TasksCompact(CompactPanel):
    icon_name = "tasks"
    title = "Today's tasks"
    section = "tasks"

    def __init__(self, ctx, parent=None):
        super().__init__("tasks", ctx, parent)
        self.done = self.total = 0
        self.refresh()

    def refresh(self) -> None:
        parts = self.ctx.repo.tasks_for_day(clock.today())
        self.done = len(parts["done_today"])
        self.total = self.done + len(parts["pending"])
        est = sum((t.estimate_minutes or 0) for t in parts["pending"] + parts["done_today"]) * 60
        focused = self.ctx.repo.focus_summary(clock.today())["seconds"]
        self.value = f"{self.done} / {self.total} done" if self.total else "No tasks yet"
        self.sub = (f"{clock.format_duration(focused)} focused" + (f" · est {clock.format_duration(est)}" if est else "")
                    if self.total else "Click to plan your day")
        self.progress = self.done / self.total if self.total else 0.0
        self.progress_color = "success"
        self.update()

    def icon_color(self) -> str:
        return self.theme.success

    def paint_extra(self, p: QPainter) -> None:
        # a small progress ring on the right instead of a bar
        t = self.theme
        r = QRectF(self.W - 46, 18, 30, 30)
        p.setPen(QPen(t.c("border"), 4))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(r)
        if self.progress > 0:
            pen = QPen(t.c("success"), 4)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            p.setPen(pen)
            p.drawArc(r, 90 * 16, int(-360 * 16 * self.progress))


class TaskEditDialog(QDialog):
    def __init__(self, ctx, task: Optional[Task] = None, parent=None):
        super().__init__(parent)
        self.setStyleSheet(stylesheet(ctx.theme))
        self.setWindowTitle("Edit task" if task else "New task")
        self.setMinimumWidth(400)
        self.title = QLineEdit(task.title if task else "")
        self.title.setMaxLength(200)
        self.priority = QComboBox()
        self.priority.addItems(PRIORITIES)
        self.priority.setCurrentIndex(task.priority if task else 0)
        self.estimate = QSpinBox()
        self.estimate.setRange(0, 24 * 60)
        self.estimate.setSingleStep(5)
        self.estimate.setSuffix(" min")
        self.estimate.setSpecialValueText("No estimate")
        self.estimate.setValue(task.estimate_minutes or 0 if task else 0)
        self.has_due = QCheckBox("Due date")
        self.due = QDateEdit()
        self.due.setCalendarPopup(True)
        self.due.setDisplayFormat("yyyy-MM-dd")
        if task and task.due_date:
            self.has_due.setChecked(True)
            self.due.setDate(QDate.fromString(task.due_date, "yyyy-MM-dd"))
        else:
            self.due.setDate(QDate.currentDate())
        self.due.setEnabled(self.has_due.isChecked())
        self.has_due.toggled.connect(self.due.setEnabled)
        self.category = QComboBox()
        self.category.setEditable(True)
        cats = sorted({t.category for t in ctx.repo.list_all_tasks() if t.category})
        self.category.addItems([""] + cats)
        self.category.setCurrentText(task.category or "" if task else "")
        due_row = QHBoxLayout()
        due_row.addWidget(self.has_due)
        due_row.addWidget(self.due, 1)
        form = QFormLayout(self)
        form.addRow("Task", self.title)
        form.addRow("Priority", self.priority)
        form.addRow("Estimate", self.estimate)
        form.addRow("", due_row)
        form.addRow("Category", self.category)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        form.addRow(bb)
        self._bb = bb
        self.title.textChanged.connect(lambda s: bb.button(QDialogButtonBox.StandardButton.Save).setEnabled(bool(s.strip())))
        bb.button(QDialogButtonBox.StandardButton.Save).setEnabled(bool(self.title.text().strip()))

    def values(self) -> dict:
        return {
            "title": self.title.text().strip(),
            "priority": self.priority.currentIndex(),
            "estimate_minutes": self.estimate.value() or None,
            "due_date": self.due.date().toString("yyyy-MM-dd") if self.has_due.isChecked() else None,
            "category": self.category.currentText().strip() or None,
        }


class TasksDialog(DetailDialog):
    def __init__(self, ctx):
        super().__init__(ctx, "Tasks", 640, 640)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(18, 16, 18, 16)
        lay.setSpacing(10)

        self.headline = QLabel()
        self.headline.setFont(ui_font(13, QFont.Weight.DemiBold))
        self.progress = QProgressBar()
        self.progress.setTextVisible(False)
        self.progress.setFixedHeight(6)
        self.subline = QLabel()
        self.subline.setProperty("role", "dim")
        lay.addWidget(self.headline)
        lay.addWidget(self.progress)
        lay.addWidget(self.subline)

        add_row = QHBoxLayout()
        self.new_title = QLineEdit()
        self.new_title.setPlaceholderText("Add a task, e.g. “Solve three DSA problems”, then press Enter")
        self.new_title.setMaxLength(200)
        self.new_title.returnPressed.connect(self._add)
        self.new_priority = QComboBox()
        self.new_priority.addItems(PRIORITIES)
        self.new_priority.setToolTip("Priority")
        self.new_estimate = QSpinBox()
        self.new_estimate.setRange(0, 24 * 60)
        self.new_estimate.setSingleStep(5)
        self.new_estimate.setSuffix(" min")
        self.new_estimate.setSpecialValueText("est.")
        self.new_estimate.setToolTip("Estimated duration (optional)")
        add_btn = QPushButton("Add")
        add_btn.setProperty("accent", "true")
        add_btn.clicked.connect(self._add)
        add_row.addWidget(self.new_title, 1)
        add_row.addWidget(self.new_priority)
        add_row.addWidget(self.new_estimate)
        add_row.addWidget(add_btn)
        lay.addLayout(add_row)

        self.tabs = QTabWidget()
        self.todo = self._make_tree(["Task", "Priority", "Details"])
        self.done = self._make_tree(["Task", "Completed", "Details"])
        self.tabs.addTab(self.todo, "To do")
        self.tabs.addTab(self.done, "Completed")
        lay.addWidget(self.tabs, 1)

        btns = QHBoxLayout()
        for text, slot, tip in (
            ("Edit…", self._edit, "Edit the selected task (or double-click it)"),
            ("Delete", self._delete, "Delete the selected task"),
            ("Move up", lambda: self._move(-1), "Reorder"),
            ("Move down", lambda: self._move(1), "Reorder"),
        ):
            b = QPushButton(text)
            b.setToolTip(tip)
            b.clicked.connect(slot)
            btns.addWidget(b)
        btns.addStretch(1)
        start = QPushButton("Focus on selected")
        start.setToolTip("Start a focus session linked to this task")
        start.clicked.connect(self._focus_selected)
        btns.addWidget(start)
        lay.addLayout(btns)

        self.summary = QLabel()
        self.summary.setWordWrap(True)
        self.summary.setProperty("role", "dim")
        lay.addWidget(self.summary)
        note = QLabel("“Focused” counts only time in focus sessions you start for a task. "
                      "App screen time is tracked separately and is not treated as work.")
        note.setWordWrap(True)
        note.setProperty("role", "dim")
        lay.addWidget(note)
        self._loading = False

    def _make_tree(self, headers: list[str]) -> QTreeWidget:
        tree = QTreeWidget()
        tree.setHeaderLabels(headers)
        tree.setRootIsDecorated(False)
        tree.setUniformRowHeights(True)
        tree.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        tree.header().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        tree.header().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        tree.itemChanged.connect(self._item_changed)
        tree.itemDoubleClicked.connect(lambda *_: self._edit())
        return tree

    def reload(self) -> None:
        self._loading = True
        today = clock.today()
        parts = self.ctx.repo.tasks_for_day(today)
        t = self.ctx.theme
        self.todo.clear()
        for task in parts["pending"] + parts["upcoming"]:
            it = QTreeWidgetItem([task.title, PRIORITIES[task.priority] if task.priority else "", task_meta(task)])
            it.setData(0, Qt.ItemDataRole.UserRole, task.id)
            it.setFlags(it.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            it.setCheckState(0, Qt.CheckState.Unchecked)
            if task in parts["upcoming"]:
                for c in range(3):
                    it.setForeground(c, QBrush(t.c("text_dim")))
                it.setToolTip(0, "Upcoming - due later")
            if task.priority == 3:
                it.setForeground(1, QBrush(t.c("warning")))
            self.todo.addTopLevelItem(it)
        self.done.clear()
        for task in parts["done_today"] + sorted(parts["done_before"], key=lambda x: x.completed_at or "", reverse=True):
            when = clock.parse_ts(task.completed_at).strftime("%d %b %H:%M") if task.completed_at else ""
            it = QTreeWidgetItem([task.title, when, task_meta(task)])
            it.setData(0, Qt.ItemDataRole.UserRole, task.id)
            it.setFlags(it.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            it.setCheckState(0, Qt.CheckState.Checked)
            self.done.addTopLevelItem(it)
        self._loading = False

        done, total = len(parts["done_today"]), len(parts["done_today"]) + len(parts["pending"])
        self.headline.setText(f"{done} of {total} tasks done today" if total else "Nothing planned yet")
        self.progress.setMaximum(max(1, total))
        self.progress.setValue(done)
        est = sum((x.estimate_minutes or 0) for x in parts["pending"] + parts["done_today"]) * 60
        focus = self.ctx.repo.focus_summary(today)
        self.subline.setText(
            f"Estimated {clock.format_duration(est)} · recorded focus {clock.format_duration(focus['seconds'])} "
            f"({focus['completed']} completed sessions)")
        s = self.ctx.repo.end_of_day_summary(today)
        self.summary.setText(
            f"Today so far: {s['tasks_done']} tasks done · {clock.format_duration(s['focus_seconds'])} focused · "
            f"{s['water_servings']} water servings · {s['breaks']} movement breaks · "
            f"{clock.format_duration(s['active_seconds'])} active screen time observed")

    def _current(self) -> Optional[int]:
        tree = self.todo if self.tabs.currentIndex() == 0 else self.done
        it = tree.currentItem()
        return it.data(0, Qt.ItemDataRole.UserRole) if it else None

    def _add(self) -> None:
        title = self.new_title.text().strip()
        if not title:
            return
        self.ctx.repo.add_task(title, priority=self.new_priority.currentIndex(),
                               estimate_minutes=self.new_estimate.value() or None)
        self.new_title.clear()
        self.new_priority.setCurrentIndex(0)
        self.new_estimate.setValue(0)
        self.ctx.notify_changed("tasks")

    def _item_changed(self, item: QTreeWidgetItem, column: int) -> None:
        if self._loading or column != 0:
            return
        task_id = item.data(0, Qt.ItemDataRole.UserRole)
        done = item.checkState(0) == Qt.CheckState.Checked
        if self.ctx.progress.complete_task(task_id, done):
            if done:
                parts = self.ctx.repo.tasks_for_day(clock.today())
                left = len(parts["pending"])
                msg = "All done for today - wonderful!" if left == 0 else f"Nice! {left} to go."
                self.ctx.say("happy", msg, "tasks")
            self.ctx.notify_changed("tasks")

    def _edit(self) -> None:
        task_id = self._current()
        task = self.ctx.repo.get_task(task_id) if task_id else None
        if not task:
            return
        dlg = TaskEditDialog(self.ctx, task, self)
        if dlg.exec():
            self.ctx.repo.update_task(task.id, **dlg.values())
            self.ctx.notify_changed("tasks")

    def _delete(self) -> None:
        task_id = self._current()
        task = self.ctx.repo.get_task(task_id) if task_id else None
        if not task:
            return
        if QMessageBox.question(self, "Delete task", f"Delete “{task.title}”?") == QMessageBox.StandardButton.Yes:
            self.ctx.repo.delete_task(task.id)
            self.ctx.repo.revoke_xp(f"task:{task.id}")
            self.ctx.notify_changed("tasks")

    def _move(self, delta: int) -> None:
        if self.tabs.currentIndex() != 0:
            return
        it = self.todo.currentItem()
        if not it:
            return
        ids = [self.todo.topLevelItem(i).data(0, Qt.ItemDataRole.UserRole) for i in range(self.todo.topLevelItemCount())]
        i = ids.index(it.data(0, Qt.ItemDataRole.UserRole))
        j = i + delta
        if not 0 <= j < len(ids):
            return
        ids[i], ids[j] = ids[j], ids[i]
        # keep completed tasks after open ones in the stored order
        rest = [t.id for t in self.ctx.repo.list_all_tasks() if t.id not in ids]
        self.ctx.repo.reorder_tasks(ids + rest)
        self.ctx.notify_changed("tasks")
        self.todo.setCurrentItem(self.todo.topLevelItem(j))

    def _focus_selected(self) -> None:
        task_id = self._current()
        if not task_id or self.tabs.currentIndex() != 0:
            return
        timer = self.ctx.focus.timer
        if timer.state.value == "idle":
            self.ctx.focus.start_focus(task_id)
        elif timer.phase.value == "focus":
            self.ctx.focus.set_task(task_id)
            self.ctx.say("working", "Linked the running session to this task.")
        else:
            QMessageBox.information(self, "Break in progress",
                                    "A break is running. Reset the timer first to start a focus session.")
            return
        self.ctx.notify_changed("focus")
