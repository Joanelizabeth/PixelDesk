"""Settings window. Every change is saved immediately."""
from __future__ import annotations

import sqlite3
from datetime import timedelta

from PySide6.QtCore import QSize, Qt, QTime, QUrl
from PySide6.QtGui import QColor, QDesktopServices, QGuiApplication
from PySide6.QtWidgets import (
    QCheckBox, QColorDialog, QComboBox, QFileDialog, QFormLayout, QGroupBox, QHBoxLayout, QHeaderView, QLabel,
    QLineEdit, QListWidget, QListWidgetItem, QMessageBox, QPlainTextEdit, QPushButton, QScrollArea, QSlider, QSpinBox,
    QTabWidget, QTableWidget, QTableWidgetItem, QTimeEdit, QVBoxLayout, QWidget,
)

from app import clock
from app.config import APP_CATEGORIES, IS_WINDOWS, PANEL_IDS, backup_dir, data_dir, log_dir

from .compact import DetailDialog
from .launcher_dialogs import LauncherItemDialog
from .pixel_art import icon_pixmap
from .theme import THEMES

PANEL_NAMES = {"wheel": "Radial launcher", "clock": "Clock & greeting", "character": "Companion & focus timer",
               "tasks": "Tasks", "water": "Water", "movement": "Movement", "screen_time": "Screen time"}

TAB_KEYS = ["general", "appearance", "launcher", "focus", "wellbeing", "screen_time", "habits", "data"]


def _note(text: str) -> QLabel:
    lab = QLabel(text)
    lab.setWordWrap(True)
    lab.setProperty("role", "dim")
    return lab


class SettingsDialog(DetailDialog):
    def __init__(self, ctx):
        super().__init__(ctx, "Settings", 700, 680)
        self.s = ctx.settings
        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 12, 14, 12)
        self.tabs = QTabWidget()
        lay.addWidget(self.tabs)
        builders = [self._general, self._appearance, self._launcher, self._focus, self._wellbeing,
                    self._screen_time, self._habits, self._data]
        titles = ["General", "Appearance", "Launcher", "Focus", "Wellbeing", "Screen time", "Habits", "Data"]
        for build, title in zip(builders, titles):
            page = QWidget()
            page.setObjectName("page")
            build(page)
            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setFrameShape(QScrollArea.Shape.NoFrame)
            scroll.setWidget(page)
            self.tabs.addTab(scroll, title)
        foot = QHBoxLayout()
        foot.addWidget(_note("Changes are saved automatically."), 1)
        close = QPushButton("Close")
        close.clicked.connect(self.close)
        foot.addWidget(close)
        lay.addLayout(foot)

    def show_tab(self, key: str) -> None:
        if key in TAB_KEYS:
            self.tabs.setCurrentIndex(TAB_KEYS.index(key))

    # -- binding helpers -------------------------------------------------------
    def _check(self, key: str, text: str) -> QCheckBox:
        box = QCheckBox(text)
        box.setChecked(bool(self.s[key]))
        box.toggled.connect(lambda v: self.s.set(key, bool(v)))
        return box

    def _spin(self, key: str, lo: int, hi: int, suffix: str = "", step: int = 1) -> QSpinBox:
        sp = QSpinBox()
        sp.setRange(lo, hi)
        sp.setSingleStep(step)
        sp.setSuffix(suffix)
        sp.setValue(int(self.s[key]))
        sp.valueChanged.connect(lambda v: self.s.set(key, int(v)))
        return sp

    def _time(self, key: str) -> QTimeEdit:
        te = QTimeEdit()
        te.setDisplayFormat("HH:mm")
        hh, mm = (self.s[key] or "00:00").split(":")
        te.setTime(QTime(int(hh), int(mm)))
        te.timeChanged.connect(lambda t: self.s.set(key, t.toString("HH:mm")))
        return te

    def _slider(self, key: str, lo: float, hi: float) -> QSlider:
        sl = QSlider(Qt.Orientation.Horizontal)
        sl.setRange(int(lo * 100), int(hi * 100))
        sl.setValue(int(float(self.s[key]) * 100))
        sl.valueChanged.connect(lambda v: self.s.set(key, round(v / 100, 2)))
        return sl

    def _combo(self, key: str, options: list[tuple[str, object]]) -> QComboBox:
        cb = QComboBox()
        for label, value in options:
            cb.addItem(label, value)
        idx = cb.findData(self.s[key])
        cb.setCurrentIndex(max(0, idx))
        cb.currentIndexChanged.connect(lambda _i: self.s.set(key, cb.currentData()))
        return cb

    # -- tabs ----------------------------------------------------------------------
    def _general(self, page: QWidget) -> None:
        form = QFormLayout(page)
        name = QLineEdit(self.s["user_name"])
        name.setPlaceholderText("Used in the greeting (optional)")
        name.setMaxLength(40)
        name.editingFinished.connect(lambda: self.s.set("user_name", name.text().strip()))
        form.addRow("Your name", name)
        msgs = QPlainTextEdit("\n".join(self.s["greeting_messages"]))
        msgs.setFixedHeight(96)
        msgs.textChanged.connect(lambda: self.s.set(
            "greeting_messages", [m.strip() for m in msgs.toPlainText().splitlines() if m.strip()][:30]))
        form.addRow("Messages", msgs)
        form.addRow("", _note("One message per line; the clock rotates through them."))

        mode = self._combo("display_mode", [("Desktop companion (widgets on the desktop)", "desktop"),
                                             ("Normal window", "window")])
        form.addRow("Display mode", mode)
        bg = self._combo("desktop_background", [
            ("Keep my current wallpaper", "none"),
            ("Use the Pixel Desk background as wallpaper (recommended)", "wallpaper"),
            ("Live layer behind icons (experimental)", "live"),
        ])
        bg.setEnabled(IS_WINDOWS)
        form.addRow("Desktop background", bg)
        form.addRow("", _note(
            "Desktop mode keeps widgets above your icons but below every app. Desktop icons stay clickable "
            "anywhere a widget isn't - drag widgets with Edit layout to keep icons clear. When Pixel Desk sets "
            "the wallpaper, your previous wallpaper is remembered and restored if you switch back."))
        screens = QComboBox()
        for i, sc in enumerate(QGuiApplication.screens()):
            g = sc.geometry()
            screens.addItem(f"{i + 1}: {sc.name()} ({g.width()}×{g.height()})", i)
        screens.setCurrentIndex(min(int(self.s["screen_index"]), max(0, screens.count() - 1)))
        screens.currentIndexChanged.connect(lambda i: self.s.set("screen_index", int(i)))
        form.addRow("Screen", screens)

        startup = QCheckBox("Start Pixel Desk when I sign in to Windows")
        startup.setChecked(self.ctx.startup.is_enabled())
        startup.setEnabled(self.ctx.startup.supported)

        def toggle_startup(on: bool) -> None:
            ok, msg = self.ctx.startup.set_enabled(on)
            if not ok:
                QMessageBox.warning(self, "Start with Windows", msg)
                startup.blockSignals(True)
                startup.setChecked(self.ctx.startup.is_enabled())
                startup.blockSignals(False)
            self.s.set("start_with_windows", self.ctx.startup.is_enabled())

        startup.toggled.connect(toggle_startup)
        form.addRow("Startup", startup)
        form.addRow("", _note("Adds a single entry under your user's Run key. To remove it, untick this box or "
                              "disable “PixelDesk” in Task Manager › Startup apps."))
        form.addRow("Notifications", self._check("notifications_native", "Show Windows notifications"))
        form.addRow("", self._check("sounds_enabled", "Play a soft chime with reminders"))
        form.addRow("Gamification", self._check("xp_enabled", "Earn XP and levels"))

    def _appearance(self, page: QWidget) -> None:
        form = QFormLayout(page)
        form.addRow("Theme", self._combo("theme", [(t.label, k) for k, t in THEMES.items()]))
        form.addRow("Background brightness", self._slider("background_brightness", 0.5, 1.5))
        form.addRow("Widget opacity", self._slider("widget_opacity", 0.35, 1.0))
        row = QHBoxLayout()
        path = QLineEdit(self.s["custom_background"])
        path.setReadOnly(True)
        path.setPlaceholderText("Plain gradient (default)")
        pick = QPushButton("Choose…")
        clear = QPushButton("Clear")

        def choose() -> None:
            f, _ = QFileDialog.getOpenFileName(self, "Background image", "", "Images (*.png *.jpg *.jpeg *.bmp *.webp)")
            if f:
                path.setText(f)
                self.s.set("custom_background", f)

        pick.clicked.connect(choose)
        clear.clicked.connect(lambda: (path.clear(), self.s.set("custom_background", "")))
        row.addWidget(path, 1)
        row.addWidget(pick)
        row.addWidget(clear)
        form.addRow("Background image", row)
        form.addRow("Wheel size", self._combo("wheel_size", [("Small", "small"), ("Medium", "medium"), ("Large", "large")]))
        form.addRow("Motion", self._check("animations_enabled", "Animations"))
        form.addRow("", self._check("reduced_motion", "Reduced motion (no idle animation or wheel easing)"))
        form.addRow("Companion", self._check("character_messages", "Speech-bubble messages"))
        cname = QLineEdit(self.s["character_name"])
        cname.setMaxLength(20)
        cname.editingFinished.connect(lambda: self.s.set("character_name", cname.text().strip() or "Pip"))
        form.addRow("Companion name", cname)
        colors = QHBoxLayout()
        for key, label in (("character_hair", "Hair colour"), ("character_outfit", "Outfit colour")):
            b = QPushButton(label)
            b.setStyleSheet(f"QPushButton {{ border-left: 14px solid {self.s[key]}; }}")

            def pick_color(_=False, k=key, btn=b) -> None:
                c = QColorDialog.getColor(QColor(self.s[k]), self, "Choose colour")
                if c.isValid():
                    self.s.set(k, c.name())
                    btn.setStyleSheet(f"QPushButton {{ border-left: 14px solid {c.name()}; }}")

            b.clicked.connect(pick_color)
            colors.addWidget(b)
        colors.addStretch(1)
        form.addRow("", colors)

        vis_box = QGroupBox("Visible widgets")
        vis = QVBoxLayout(vis_box)
        visible = self.s["widgets_visible"]
        for pid in PANEL_IDS:
            cb = QCheckBox(PANEL_NAMES[pid])
            cb.setChecked(visible.get(pid, True))

            def set_vis(on: bool, p=pid) -> None:
                v = self.s["widgets_visible"]
                v[p] = bool(on)
                self.s.set("widgets_visible", v)

            cb.toggled.connect(set_vis)
            vis.addWidget(cb)
        form.addRow(vis_box)
        btns = QHBoxLayout()
        edit = QPushButton("Edit layout (drag widgets)")
        edit.clicked.connect(lambda: self.ctx.signals.layout_edit_changed.emit(True))
        reset = QPushButton("Reset layout")
        reset.clicked.connect(lambda: self.s.set("layout", {}))
        btns.addWidget(edit)
        btns.addWidget(reset)
        btns.addStretch(1)
        form.addRow(btns)

    def _launcher(self, page: QWidget) -> None:
        lay = QVBoxLayout(page)
        self.launch_list = QListWidget()
        self.launch_list.setIconSize(QSize(24, 24))
        self.launch_list.itemDoubleClicked.connect(lambda *_: self._edit_launcher())
        lay.addWidget(self.launch_list, 1)
        row = QHBoxLayout()
        for text, slot in (("Add folder…", lambda: self._add_launcher("folder")),
                           ("Add application…", lambda: self._add_launcher("app")),
                           ("Edit…", self._edit_launcher), ("Remove", self._remove_launcher),
                           ("Up", lambda: self._move_launcher(-1)), ("Down", lambda: self._move_launcher(1))):
            b = QPushButton(text)
            b.clicked.connect(slot)
            row.addWidget(b)
        lay.addLayout(row)
        lay.addWidget(_note("Removing an entry only removes the shortcut from the wheel. Folders and files on disk "
                            "are never changed. Items whose path no longer exists are marked and can be edited."))
        self._reload_launcher()

    def _reload_launcher(self) -> None:
        from services.launcher_service import validate_entry

        t = self.ctx.theme
        self.launch_list.clear()
        for item in self.ctx.repo.list_launcher_items():
            err = validate_entry(item.kind, item.path)
            it = QListWidgetItem(f"{item.label}    —    {item.path}" + ("   (not found)" if err else ""))
            it.setIcon(icon_pixmap(item.icon, t.accent if item.kind == "folder" else t.accent2, t.outline, 24))
            it.setData(Qt.ItemDataRole.UserRole, item.id)
            if err:
                it.setToolTip(err)
            self.launch_list.addItem(it)

    def _selected_launcher(self):
        it = self.launch_list.currentItem()
        if not it:
            return None
        lid = it.data(Qt.ItemDataRole.UserRole)
        return next((i for i in self.ctx.repo.list_launcher_items() if i.id == lid), None)

    def _add_launcher(self, kind: str) -> None:
        dlg = LauncherItemDialog(self.ctx, kind=kind, parent=self)
        if dlg.exec():
            label, kind, path, icon = dlg.values()
            self.ctx.repo.add_launcher_item(label, kind, path, icon)
            self.ctx.notify_changed("launcher")

    def _edit_launcher(self) -> None:
        item = self._selected_launcher()
        if item:
            dlg = LauncherItemDialog(self.ctx, item=item, parent=self)
            if dlg.exec():
                label, kind, path, icon = dlg.values()
                self.ctx.repo.update_launcher_item(item.id, label=label, path=path, icon=icon, kind=kind)
                self.ctx.notify_changed("launcher")

    def _remove_launcher(self) -> None:
        item = self._selected_launcher()
        if item:
            self.ctx.repo.delete_launcher_item(item.id)
            self.ctx.notify_changed("launcher")

    def _move_launcher(self, delta: int) -> None:
        row = self.launch_list.currentRow()
        ids = [self.launch_list.item(i).data(Qt.ItemDataRole.UserRole) for i in range(self.launch_list.count())]
        j = row + delta
        if row < 0 or not 0 <= j < len(ids):
            return
        ids[row], ids[j] = ids[j], ids[row]
        self.ctx.repo.reorder_launcher_items(ids)
        self.ctx.notify_changed("launcher")
        self.launch_list.setCurrentRow(j)

    def _focus(self, page: QWidget) -> None:
        form = QFormLayout(page)
        form.addRow("Focus length", self._spin("focus_minutes", 1, 180, " min"))
        form.addRow("Break length", self._spin("break_minutes", 1, 60, " min"))
        form.addRow("", self._check("auto_start_breaks", "Start the break automatically after a focus session"))
        form.addRow("", self._check("auto_start_focus", "Start the next focus session automatically after a break"))
        form.addRow("", self._check("focus_notifications", "Notify me when a session ends"))
        form.addRow("", self._check("focus_celebration", "Celebrate completed sessions"))
        form.addRow("", _note("Durations apply to the next session. Resetting a session early stores it as "
                              "cancelled: its minutes count as focus time for the task, but it earns no "
                              "completion credit or XP."))

    def _wellbeing(self, page: QWidget) -> None:
        lay = QVBoxLayout(page)
        quiet = QGroupBox("Quiet hours (no water or movement reminders)")
        qf = QFormLayout(quiet)
        qf.addRow("", self._check("quiet_hours_enabled", "Enable quiet hours"))
        qrow = QHBoxLayout()
        qrow.addWidget(self._time("quiet_start"))
        qrow.addWidget(QLabel("to"))
        qrow.addWidget(self._time("quiet_end"))
        qrow.addStretch(1)
        qf.addRow("From", qrow)
        lay.addWidget(quiet)

        water = QGroupBox("Water")
        wf = QFormLayout(water)
        wf.addRow("Daily goal", self._spin("water_goal_servings", 1, 30, " servings"))
        wf.addRow("Serving size", self._spin("water_serving_ml", 50, 1000, " ml", 50))
        wf.addRow("", self._check("water_reminders", "Remind me to drink"))
        wf.addRow("Every", self._spin("water_interval_min", 10, 360, " min", 5))
        wf.addRow("Snooze", self._spin("water_snooze_min", 5, 120, " min", 5))
        wf.addRow("", _note("Eight servings is only a common default; it is not medical advice."))
        lay.addWidget(water)

        move = QGroupBox("Movement (estimated desk time)")
        mf = QFormLayout(move)
        mf.addRow("", self._check("movement_reminders", "Suggest a walk or stretch"))
        mf.addRow("After active time of", self._spin("movement_interval_min", 15, 240, " min", 5))
        mf.addRow("Break length", self._spin("movement_break_min", 1, 30, " min"))
        mf.addRow("Snooze", self._spin("movement_snooze_min", 5, 60, " min", 5))
        mf.addRow("Reset after idle", self._spin("movement_idle_reset_min", 1, 60, " min"))
        lay.addWidget(move)
        lay.addStretch(1)

    def _screen_time(self, page: QWidget) -> None:
        lay = QVBoxLayout(page)
        form = QFormLayout()
        form.addRow("", self._check("monitoring_enabled", "Record foreground application time"))
        form.addRow("Idle after", self._spin("idle_threshold_min", 1, 60, " min"))
        form.addRow("Keep app details for", self._spin("usage_retention_days", 7, 3650, " days", 30))
        lay.addLayout(form)
        lay.addWidget(_note("Pixel Desk records which application is in the foreground and for how long. It never "
                            "records window titles, keystrokes, typed text, screenshots or browser contents. "
                            "Idle and locked time are never counted as app usage."))
        lay.addWidget(QLabel("Application categories"))
        self.app_table = QTableWidget(0, 2)
        self.app_table.setHorizontalHeaderLabels(["Application", "Category"])
        self.app_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.app_table.verticalHeader().setVisible(False)
        lay.addWidget(self.app_table, 1)
        self._reload_apps()

    def _reload_apps(self) -> None:
        apps = self.ctx.repo.list_apps()
        self.app_table.setRowCount(len(apps))
        for r, app in enumerate(apps):
            item = QTableWidgetItem(app["display_name"])
            item.setToolTip(app["exe"])
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.app_table.setItem(r, 0, item)
            combo = QComboBox()
            combo.addItems([c.title() for c in APP_CATEGORIES])
            combo.setCurrentIndex(APP_CATEGORIES.index(app["category"]))
            combo.currentIndexChanged.connect(
                lambda i, exe=app["exe"]: (self.ctx.repo.set_app_category(exe, APP_CATEGORIES[i]),
                                           self.ctx.notify_changed("usage")))
            self.app_table.setCellWidget(r, 1, combo)
        if not apps:
            self.app_table.setRowCount(1)
            self.app_table.setItem(0, 0, QTableWidgetItem("No applications observed yet."))

    def _habits(self, page: QWidget) -> None:
        lay = QVBoxLayout(page)
        self.habit_table = QTableWidget(0, 3)
        self.habit_table.setHorizontalHeaderLabels(["Habit", "Counts toward streak", "Active"])
        self.habit_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.habit_table.verticalHeader().setVisible(False)
        self.habit_table.itemChanged.connect(self._habit_renamed)
        lay.addWidget(self.habit_table, 1)
        row = QHBoxLayout()
        self.habit_name = QLineEdit()
        self.habit_name.setPlaceholderText("New habit")
        self.habit_name.setMaxLength(60)
        add = QPushButton("Add")
        add.clicked.connect(self._add_habit)
        self.habit_name.returnPressed.connect(self._add_habit)
        delete = QPushButton("Delete selected")
        delete.clicked.connect(self._delete_habit)
        row.addWidget(self.habit_name, 1)
        row.addWidget(add)
        row.addWidget(delete)
        lay.addLayout(row)
        lay.addWidget(_note("Double-click a name to rename it. Deleting a habit also deletes its check-in history. "
                            "Inactive habits are hidden from check-ins but keep their history."))
        self._reload_habits()

    def _reload_habits(self) -> None:
        self._habits_loading = True
        habits = self.ctx.repo.list_habits(include_inactive=True)
        self.habit_table.setRowCount(len(habits))
        for r, h in enumerate(habits):
            name = QTableWidgetItem(h.name)
            name.setData(Qt.ItemDataRole.UserRole, h.id)
            self.habit_table.setItem(r, 0, name)
            for col, attr in ((1, "counts_toward_streak"), (2, "active")):
                cb = QCheckBox()
                cb.setChecked(getattr(h, attr))
                cb.toggled.connect(lambda on, hid=h.id, a=attr: (self.ctx.repo.update_habit(hid, **{a: on}),
                                                                 self.ctx.notify_changed("habits")))
                self.habit_table.setCellWidget(r, col, cb)
        self._habits_loading = False

    def _habit_renamed(self, item: QTableWidgetItem) -> None:
        if getattr(self, "_habits_loading", False) or item.column() != 0:
            return
        try:
            self.ctx.repo.update_habit(item.data(Qt.ItemDataRole.UserRole), name=item.text())
            self.ctx.notify_changed("habits")
        except (ValueError, sqlite3.IntegrityError):
            QMessageBox.warning(self, "Habits", "That name is empty or already used.")
            self._reload_habits()

    def _add_habit(self) -> None:
        name = self.habit_name.text().strip()
        if not name:
            return
        try:
            self.ctx.repo.add_habit(name)
        except sqlite3.IntegrityError:
            QMessageBox.warning(self, "Habits", "You already have a habit with that name.")
            return
        self.habit_name.clear()
        self.ctx.notify_changed("habits")

    def _delete_habit(self) -> None:
        row = self.habit_table.currentRow()
        if row < 0:
            return
        item = self.habit_table.item(row, 0)
        if QMessageBox.question(self, "Delete habit", f"Delete “{item.text()}” and its history?") == \
                QMessageBox.StandardButton.Yes:
            self.ctx.repo.delete_habit(item.data(Qt.ItemDataRole.UserRole))
            self.ctx.notify_changed("habits")

    def _data(self, page: QWidget) -> None:
        lay = QVBoxLayout(page)
        form = QFormLayout()
        loc = QLineEdit(str(data_dir()))
        loc.setReadOnly(True)
        form.addRow("Data folder", loc)
        lay.addLayout(form)
        row = QHBoxLayout()
        open_btn = QPushButton("Open data folder")
        open_btn.clicked.connect(lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(data_dir()))))
        logs = QPushButton("Open logs")
        logs.clicked.connect(lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(log_dir()))))
        row.addWidget(open_btn)
        row.addWidget(logs)
        row.addStretch(1)
        lay.addLayout(row)

        box = QGroupBox("Backup & restore")
        bl = QVBoxLayout(box)
        brow = QHBoxLayout()
        backup = QPushButton("Back up now…")
        backup.clicked.connect(self._backup)
        restore = QPushButton("Restore from backup…")
        restore.clicked.connect(self._restore)
        brow.addWidget(backup)
        brow.addWidget(restore)
        brow.addStretch(1)
        bl.addLayout(brow)
        bl.addWidget(_note("A backup is a single .db file containing tasks, habits, settings and history. "
                           "Restoring replaces the current data (a safety copy is kept) and restarts Pixel Desk."))
        lay.addWidget(box)

        box2 = QGroupBox("Retention")
        rl = QVBoxLayout(box2)
        purge = QPushButton("Remove app details older than the retention period now")
        purge.clicked.connect(self._purge)
        rl.addWidget(purge)
        rl.addWidget(_note("Daily totals are kept; only per-application and hourly details are removed."))
        lay.addWidget(box2)
        lay.addStretch(1)

    def _backup(self) -> None:
        default = backup_dir() / f"pixeldesk-backup-{clock.now().strftime('%Y%m%d-%H%M')}.db"
        path, _ = QFileDialog.getSaveFileName(self, "Save backup", str(default), "Pixel Desk backup (*.db)")
        if path:
            try:
                self.ctx.repo.db.backup_to(path)
                QMessageBox.information(self, "Backup", f"Backup saved to\n{path}")
            except Exception as exc:  # noqa: BLE001 - surfaced to the user
                QMessageBox.warning(self, "Backup failed", str(exc))

    def _restore(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Restore backup", str(backup_dir()), "Pixel Desk backup (*.db)")
        if not path:
            return
        if QMessageBox.question(self, "Restore backup",
                                "Replace all current Pixel Desk data with this backup? A safety copy of the "
                                "current data is kept in the data folder.") != QMessageBox.StandardButton.Yes:
            return
        ok, msg = self.ctx.app.restore_backup(path)
        if not ok:
            QMessageBox.warning(self, "Restore failed", msg)

    def _purge(self) -> None:
        cutoff = clock.today() - timedelta(days=int(self.s["usage_retention_days"]))
        n = self.ctx.repo.purge_usage_before(cutoff)
        QMessageBox.information(self, "Retention", f"Removed {n} app-usage rows older than {cutoff.isoformat()}.")
        self.ctx.notify_changed("usage")

    def reload(self) -> None:
        self._reload_launcher()
        self._reload_apps()
        self._reload_habits()
