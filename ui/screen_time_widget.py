"""Screen time observed by Pixel Desk: compact widget + report window."""
from __future__ import annotations

from datetime import timedelta

from PySide6.QtCore import QFileInfo, QRectF, QSize, Qt
from PySide6.QtGui import QFont, QPainter
from PySide6.QtWidgets import (
    QComboBox, QFileIconProvider, QHBoxLayout, QHeaderView, QLabel, QPushButton, QTreeWidget, QTreeWidgetItem,
    QVBoxLayout,
)

from app import clock
from app.config import APP_CATEGORIES

from .charts import BarChart, HourlyTimeline, StackedBar
from .compact import CompactPanel, DetailDialog
from .theme import ui_font

CATEGORY_COLORS = {"productive": "accent", "learning": "success", "communication": "water",
                   "entertainment": "accent2", "other": "text_dim"}

STATUS_TEXT = {
    "active": ("Monitoring", "success"),
    "idle": ("Idle - not counted as active", "text_dim"),
    "locked": ("Locked - not counted", "text_dim"),
    "paused": ("Paused", "warning"),
    "unavailable": ("Monitoring unavailable", "warning"),
}


def monitor_label(ctx) -> tuple[str, str]:
    st = ctx.monitor_status
    if not ctx.settings["monitoring_enabled"]:
        return STATUS_TEXT["paused"]
    if st is None:
        return ("Starting…", "text_dim") if ctx.probe_available else STATUS_TEXT["unavailable"]
    return STATUS_TEXT.get(st.state.value, ("", "text_dim"))


class ScreenTimeCompact(CompactPanel):
    icon_name = "screen"
    title = "Screen time today"
    section = "screen_time"

    def __init__(self, ctx, parent=None):
        super().__init__("screen_time", ctx, parent)
        self.pause_btn = self.make_button("Pause", "Pause or resume screen-time monitoring", self._toggle)
        self.pause_btn.setGeometry(self.W - 66, 10, 56, 22)
        self.refresh()

    def _toggle(self) -> None:
        self.ctx.settings.set("monitoring_enabled", not self.ctx.settings["monitoring_enabled"])

    def refresh(self) -> None:
        today = clock.today()
        usage = self.ctx.repo.daily_usage(today)
        apps = self.ctx.repo.app_usage_for(today)
        active = usage["active_seconds"]
        cats = self.ctx.repo.category_totals(today)
        focused = cats["productive"] + cats["learning"]
        self.value = clock.format_duration(active)
        status, _ = monitor_label(self.ctx)
        if status not in ("Monitoring", "Starting…"):
            self.sub = status
        elif apps:
            self.sub = f"Top: {apps[0].display_name} · {focused / active:.0%} productive" if active else ""
        else:
            self.sub = "Nothing observed yet today"
        self.progress = focused / active if active else 0
        self.pause_btn.setText("Resume" if not self.ctx.settings["monitoring_enabled"] else "Pause")
        self.update()

    def update_status(self) -> None:
        self.refresh()

    def paint_extra(self, p: QPainter) -> None:
        super().paint_extra(p)
        t = self.theme
        text, color = monitor_label(self.ctx)
        # status dot on the icon badge; the full text is in the tooltip/sub-line
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(t.c("panel"))
        p.drawEllipse(QRectF(36, 38, 12, 12))
        p.setBrush(t.c(color))
        p.drawEllipse(QRectF(38, 40, 8, 8))
        self.setToolTip(f"{text}. Time observed by Pixel Desk while it runs.")


class ScreenTimeDialog(DetailDialog):
    def __init__(self, ctx):
        super().__init__(ctx, "Screen time", 700, 760)
        self._icons = QFileIconProvider()
        lay = QVBoxLayout(self)
        lay.setContentsMargins(18, 16, 18, 16)
        lay.setSpacing(8)

        top = QHBoxLayout()
        self.headline = QLabel()
        self.headline.setFont(ui_font(14, QFont.Weight.DemiBold))
        top.addWidget(self.headline, 1)
        self.pause = QPushButton()
        self.pause.clicked.connect(lambda: ctx.settings.set("monitoring_enabled", not ctx.settings["monitoring_enabled"]))
        top.addWidget(self.pause)
        lay.addLayout(top)
        self.subline = QLabel()
        self.subline.setProperty("role", "dim")
        self.subline.setWordWrap(True)
        lay.addWidget(self.subline)

        lay.addWidget(self._caption("By category (today)"))
        self.categories = StackedBar(ctx.theme)
        lay.addWidget(self.categories)
        lay.addWidget(self._caption("Timeline (today) - active and idle per hour"))
        self.timeline = HourlyTimeline(ctx.theme)
        lay.addWidget(self.timeline)
        lay.addWidget(self._caption("Last 7 days - active time"))
        self.week = BarChart(ctx.theme, 130, fmt=clock.format_duration)
        lay.addWidget(self.week)

        apps_row = QHBoxLayout()
        apps_row.addWidget(self._caption("Applications"), 1)
        self.range = QComboBox()
        self.range.addItems(["Today", "Last 7 days"])
        self.range.currentIndexChanged.connect(self.reload)
        apps_row.addWidget(self.range)
        lay.addLayout(apps_row)
        self.apps = QTreeWidget()
        self.apps.setHeaderLabels(["Application", "Time", "Category"])
        self.apps.setRootIsDecorated(False)
        self.apps.setIconSize(QSize(18, 18))
        self.apps.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.apps.header().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.apps.header().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        lay.addWidget(self.apps, 1)
        note = QLabel("Time observed by Pixel Desk while it was running. Only the foreground application's "
                      "name is recorded - never window titles, keystrokes, screenshots or page contents. "
                      "Change a category with the drop-down; reports update immediately.")
        note.setWordWrap(True)
        note.setProperty("role", "dim")
        lay.addWidget(note)

    def _caption(self, text: str) -> QLabel:
        lab = QLabel(text)
        lab.setProperty("role", "dim")
        return lab

    def reload(self) -> None:
        t = self.ctx.theme
        for chart in (self.categories, self.timeline, self.week):
            chart.theme = t
        today = clock.today()
        usage = self.ctx.repo.daily_usage(today)
        yesterday = self.ctx.repo.daily_usage(today - timedelta(days=1))
        active = usage["active_seconds"]
        self.headline.setText(f"{clock.format_duration(active)} active today")
        diff = active - yesterday["active_seconds"]
        compare = (f"{clock.format_duration(abs(diff))} {'more' if diff >= 0 else 'less'} than yesterday"
                   if yesterday["active_seconds"] else "No data for yesterday")
        since = (f"Observed since {clock.parse_ts(usage['first_observed']).strftime('%H:%M')}"
                 if usage["first_observed"] else "Nothing observed yet today")
        status, _ = monitor_label(self.ctx)
        self.subline.setText(f"{since} · idle {clock.format_duration(usage['idle_seconds'])} · {compare} · {status}")
        self.pause.setText("Resume monitoring" if not self.ctx.settings["monitoring_enabled"] else "Pause monitoring")

        cats = self.ctx.repo.category_totals(today)
        self.categories.set_data([(c.title(), cats[c], t.c(CATEGORY_COLORS[c])) for c in APP_CATEGORIES])
        self.timeline.set_data(self.ctx.repo.hourly_usage(today))
        days = clock.days_back(today, 7)
        rng = self.ctx.repo.daily_usage_range(days)
        self.week.set_data([d.strftime("%a") for d in days],
                           [rng.get(d.isoformat(), {}).get("active_seconds", 0.0) for d in days],
                           [t.c("accent") if d == today else t.c("accent", 0.6) for d in days])

        start = today if self.range.currentIndex() == 0 else today - timedelta(days=6)
        self.apps.clear()
        for app in self.ctx.repo.app_usage_for(start, today)[:40]:
            it = QTreeWidgetItem([app.display_name, clock.format_duration(app.seconds), ""])
            it.setToolTip(0, app.exe)
            if app.exe_path:
                it.setIcon(0, self._icons.icon(QFileInfo(app.exe_path)))
            self.apps.addTopLevelItem(it)
            combo = QComboBox()
            combo.addItems([c.title() for c in APP_CATEGORIES])
            combo.setCurrentIndex(APP_CATEGORIES.index(app.category))
            combo.currentIndexChanged.connect(lambda i, exe=app.exe: self._set_category(exe, i))
            self.apps.setItemWidget(it, 2, combo)

    def _set_category(self, exe: str, index: int) -> None:
        self.ctx.repo.set_app_category(exe, APP_CATEGORIES[index])
        self.ctx.notify_changed("usage")
