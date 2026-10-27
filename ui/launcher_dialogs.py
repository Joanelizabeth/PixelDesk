"""Dialog for adding/editing a launcher entry (native file/folder pickers)."""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

from PySide6.QtCore import QSize
from PySide6.QtWidgets import (
    QButtonGroup, QComboBox, QDialog, QDialogButtonBox, QFileDialog, QFormLayout, QGridLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QToolButton, QVBoxLayout, QWidget,
)

from app.config import SUGGESTED_LAUNCHER_LABELS
from database.repository import LauncherItem
from services.launcher_service import validate_entry

from .pixel_art import LAUNCHER_ICON_CHOICES, qicon
from .theme import stylesheet

APP_FILTER = (
    "Applications and shortcuts (*.exe *.lnk *.appref-ms *.url)" if sys.platform == "win32" else "All files (*)"
)


def guess_icon(label: str, kind: str) -> str:
    low = label.lower()
    table = [
        (("college", "uni", "school", "class"), "cap"), (("project", "fitquest"), "rocket"),
        (("python", "code", "dev", "src"), "code"), (("note",), "note"), (("resource", "book", "doc"), "book"),
        (("personal",), "heart"), (("screenshot", "photo"), "camera"), (("picture", "image"), "image"),
        (("download",), "download"), (("music",), "music"), (("game", "video"), "game"),
    ]
    for words, icon in table:
        if any(w in low for w in words):
            return icon
    return "folder" if kind == "folder" else "app"


class LauncherItemDialog(QDialog):
    def __init__(self, ctx, kind: str = "folder", item: Optional[LauncherItem] = None, parent=None):
        super().__init__(parent)
        self.ctx = ctx
        t = ctx.theme
        self.setStyleSheet(stylesheet(t))
        self.setWindowTitle("Edit shortcut" if item else ("Add folder" if kind == "folder" else "Add application"))
        self.setMinimumWidth(460)
        self._icon = item.icon if item else ("folder" if kind == "folder" else "app")
        self._icon_touched = item is not None

        self.label = QComboBox()
        self.label.setEditable(True)
        self.label.addItems([""] + SUGGESTED_LAUNCHER_LABELS)
        self.label.setCurrentText(item.label if item else "")
        self.label.lineEdit().setPlaceholderText("Name shown on the wheel")
        self.label.lineEdit().setMaxLength(60)
        self.label.currentTextChanged.connect(self._auto_icon)

        self.kind = QComboBox()
        self.kind.addItem("Folder", "folder")
        self.kind.addItem("Application / shortcut", "app")
        self.kind.setCurrentIndex(0 if (item.kind if item else kind) == "folder" else 1)
        self.kind.currentIndexChanged.connect(self._validate)

        self.path = QLineEdit(item.path if item else "")
        self.path.setPlaceholderText("Choose with Browse…")
        self.path.textChanged.connect(self._validate)
        browse = QPushButton("Browse…")
        browse.clicked.connect(self._browse)
        path_row = QHBoxLayout()
        path_row.addWidget(self.path, 1)
        path_row.addWidget(browse)

        icons = QWidget()
        grid = QGridLayout(icons)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setSpacing(4)
        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        for i, name in enumerate(LAUNCHER_ICON_CHOICES):
            b = QToolButton()
            b.setCheckable(True)
            b.setIcon(qicon(name, t.accent, t.outline, 24))
            b.setIconSize(QSize(24, 24))
            b.setToolTip(name.title())
            b.setChecked(name == self._icon)
            b.clicked.connect(lambda _=False, n=name: self._pick_icon(n))
            self._group.addButton(b)
            grid.addWidget(b, i // 9, i % 9)

        self.error = QLabel("")
        self.error.setProperty("role", "dim")
        self.error.setWordWrap(True)

        form = QFormLayout()
        form.addRow("Name", self.label)
        form.addRow("Type", self.kind)
        form.addRow("Path", path_row)
        form.addRow("Icon", icons)

        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)

        note = QLabel("Pixel Desk only stores a shortcut. Your files are never moved, renamed or deleted.")
        note.setProperty("role", "dim")
        note.setWordWrap(True)

        lay = QVBoxLayout(self)
        lay.addLayout(form)
        lay.addWidget(self.error)
        lay.addWidget(note)
        lay.addWidget(self.buttons)
        self._validate()

    def _pick_icon(self, name: str) -> None:
        self._icon = name
        self._icon_touched = True

    def _auto_icon(self, text: str) -> None:
        if self._icon_touched:
            return
        icon = guess_icon(text, self.kind.currentData())
        self._icon = icon
        for b in self._group.buttons():
            b.setChecked(b.toolTip().lower() == icon)

    def _browse(self) -> None:
        start = self.path.text() or str(Path.home())
        if self.kind.currentData() == "folder":
            chosen = QFileDialog.getExistingDirectory(self, "Choose a folder", start)
        else:
            chosen, _ = QFileDialog.getOpenFileName(self, "Choose an application or shortcut", start, APP_FILTER)
        if chosen:
            self.path.setText(str(Path(chosen)))
            if not self.label.currentText().strip():
                self.label.setCurrentText(Path(chosen).stem if self.kind.currentData() == "app" else Path(chosen).name)

    def _validate(self) -> None:
        err = validate_entry(self.kind.currentData(), self.path.text().strip())
        if not self.path.text().strip():
            err = "Choose a folder or application."
        self.error.setText(err or "")
        self.buttons.button(QDialogButtonBox.StandardButton.Save).setEnabled(err is None)

    def accept(self) -> None:
        if not self.label.currentText().strip():
            p = Path(self.path.text().strip())
            self.label.setCurrentText(p.stem or p.name or "Shortcut")
        super().accept()

    def values(self) -> tuple[str, str, str, str]:
        return (self.label.currentText().strip()[:60], self.kind.currentData(), self.path.text().strip(), self._icon)
