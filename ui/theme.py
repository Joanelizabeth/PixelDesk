"""Design tokens, fonts and the shared Qt stylesheet."""
from __future__ import annotations

import sys
from dataclasses import dataclass

from PySide6.QtGui import QColor, QFont


@dataclass(frozen=True)
class Theme:
    key: str
    label: str
    bg_top: str
    bg_bottom: str
    bg_glow: str
    panel: str
    border: str
    text: str
    text_dim: str
    accent: str      # soft lavender
    accent2: str     # dusty pink
    success: str     # muted sage
    water: str       # subdued sky blue
    warning: str     # warm amber
    outline: str     # pixel-art outline
    star: str
    dark: bool = True

    def c(self, name: str, alpha: float | None = None) -> QColor:
        col = QColor(getattr(self, name))
        if alpha is not None:
            col.setAlphaF(max(0.0, min(1.0, alpha)))
        return col


THEMES: dict[str, Theme] = {
    "dark_purple": Theme(
        "dark_purple", "Dark purple", "#211b2c", "#100d16", "#3b2d55", "#1f1929", "#4a3f60",
        "#f3ede1", "#a99fbd", "#b9a6e8", "#d9a0b6", "#9cc4a0", "#8ec1df", "#e6b56c", "#151020", "#e9e1ff",
    ),
    "midnight_blue": Theme(
        "midnight_blue", "Midnight blue", "#161d31", "#0a0e18", "#24365e", "#151c30", "#34446b",
        "#eef0f6", "#9ea8c4", "#a9b7f0", "#d6a3c2", "#9cc4ab", "#8ec5e6", "#e6b56c", "#0b1020", "#dfe7ff",
    ),
    "warm_charcoal": Theme(
        "warm_charcoal", "Warm charcoal", "#26211f", "#121010", "#3f322b", "#221d1b", "#4d433c",
        "#f4ece0", "#b2a596", "#c9b3e0", "#e0a99a", "#a7c49a", "#93c0d6", "#e8b366", "#151110", "#fff1dc",
    ),
    "muted_pastel": Theme(
        "muted_pastel", "Muted pastel (light)", "#ece6f2", "#d9d0e6", "#f6e6ee", "#f7f3fa", "#c7bcd6",
        "#2b2435", "#6c6080", "#7d68c4", "#c06e8c", "#5e9466", "#4a8fb8", "#b57a1e", "#3a3048", "#ffffff",
        dark=False,
    ),
}


def get_theme(key: str) -> Theme:
    return THEMES.get(key, THEMES["dark_purple"])


def ui_font(point_size: float = 10, weight: QFont.Weight = QFont.Weight.Normal) -> QFont:
    font = QFont()
    if sys.platform == "win32":
        font.setFamilies(["Segoe UI Variable Text", "Segoe UI", "Arial"])
    else:
        font.setFamilies(["Inter", "Noto Sans", "DejaVu Sans", "Arial"])
    font.setPointSizeF(point_size)
    font.setWeight(weight)
    font.setHintingPreference(QFont.HintingPreference.PreferNoHinting)
    return font


def blend(a: QColor, b: QColor, t: float) -> QColor:
    return QColor(
        int(a.red() + (b.red() - a.red()) * t),
        int(a.green() + (b.green() - a.green()) * t),
        int(a.blue() + (b.blue() - a.blue()) * t),
        int(a.alpha() + (b.alpha() - a.alpha()) * t),
    )


_CHECK_CACHE: dict[str, str] = {}


def _check_image(color: str) -> str:
    """A tiny pixel check mark for checkbox indicators (written once to the cache)."""
    if color in _CHECK_CACHE:
        return _CHECK_CACHE[color]
    from PySide6.QtGui import QImage

    from app.config import cache_dir

    rows = ["..........", "........##", ".......##.", "......##..", "##...##...",
            ".##.##....", "..###.....", "...#......", "..........", ".........."]
    img = QImage(10, 10, QImage.Format.Format_ARGB32)
    img.fill(0)
    for y, row in enumerate(rows):
        for x, ch in enumerate(row):
            if ch == "#":
                img.setPixelColor(x, y, QColor(color))
    path = cache_dir() / f"check_{color.strip('#')}.png"
    img.scaled(20, 20).save(str(path))
    _CHECK_CACHE[color] = path.as_posix()
    return _CHECK_CACHE[color]


def stylesheet(t: Theme) -> str:
    """Restrained styling for the standard controls used in panels and dialogs."""
    try:
        check = _check_image(t.outline)
    except Exception:  # pragma: no cover - cache dir unavailable
        check = ""
    check_rule = f"image: url({check});" if check else ""
    field_bg = "rgba(255,255,255,0.05)" if t.dark else "rgba(255,255,255,0.75)"
    hover_bg = "rgba(255,255,255,0.09)" if t.dark else "rgba(0,0,0,0.05)"
    dialog_bg = t.bg_top if t.dark else "#f5f1f9"
    return f"""
    QWidget {{ color: {t.text}; }}
    QDialog, QDialog QWidget#page {{ background: {dialog_bg}; }}
    QToolTip {{ background: {t.panel}; color: {t.text}; border: 1px solid {t.border}; padding: 4px 6px; }}
    QLabel[role="dim"] {{ color: {t.text_dim}; }}
    QLabel[role="title"] {{ font-weight: 600; }}
    QPushButton, QToolButton {{
        background: {field_bg}; border: 1px solid {t.border}; border-radius: 7px;
        padding: 5px 12px; color: {t.text};
    }}
    QPushButton:hover, QToolButton:hover {{ background: {hover_bg}; border-color: {t.accent}; }}
    QPushButton:pressed, QToolButton:pressed {{ background: {t.accent}; color: {t.outline}; }}
    QPushButton:focus, QToolButton:focus {{ border: 1px solid {t.accent}; }}
    QPushButton:disabled {{ color: {t.text_dim}; border-color: {t.border}; }}
    QPushButton[accent="true"] {{ background: {t.accent}; color: {t.outline}; border-color: {t.accent}; font-weight: 600; }}
    QPushButton[accent="true"]:hover {{ background: {t.accent2}; border-color: {t.accent2}; }}
    QPushButton[flat="true"] {{ background: transparent; border: 1px solid transparent; padding: 3px 6px; }}
    QPushButton[flat="true"]:hover {{ border-color: {t.border}; }}
    QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox, QDateEdit, QTimeEdit, QPlainTextEdit {{
        background: {field_bg}; border: 1px solid {t.border}; border-radius: 6px; padding: 4px 6px;
        selection-background-color: {t.accent}; selection-color: {t.outline};
    }}
    QLineEdit:focus, QSpinBox:focus, QComboBox:focus, QDateEdit:focus, QTimeEdit:focus {{ border-color: {t.accent}; }}
    QComboBox QAbstractItemView {{ background: {t.panel}; border: 1px solid {t.border};
        selection-background-color: {t.accent}; selection-color: {t.outline}; }}
    QListWidget, QTreeWidget, QTableWidget {{
        background: {field_bg}; border: 1px solid {t.border}; border-radius: 8px; padding: 4px;
        alternate-background-color: transparent;
    }}
    QListWidget::item, QTableWidget::item {{ padding: 4px; border-radius: 5px; }}
    QListWidget::item:selected, QTableWidget::item:selected {{ background: {t.accent}; color: {t.outline}; }}
    QHeaderView {{ background: transparent; border: none; }}
    QHeaderView::section {{ background: transparent; color: {t.text_dim}; border: none;
        border-bottom: 1px solid {t.border}; padding: 4px; }}
    QTableCornerButton::section {{ background: transparent; border: none; }}
    QTreeWidget::item {{ padding: 5px 2px; }}
    QTreeWidget::item:selected {{ background: {t.accent}; color: {t.outline}; }}
    QTreeWidget::indicator, QTableWidget::indicator, QListWidget::indicator {{
        width: 14px; height: 14px; border: 1px solid {t.border}; border-radius: 4px; background: {field_bg}; }}
    QTreeWidget::indicator:checked, QTableWidget::indicator:checked, QListWidget::indicator:checked {{
        background: {t.success}; border-color: {t.success}; {check_rule} }}
    QTabWidget::pane {{ border: 1px solid {t.border}; border-radius: 8px; top: -1px; }}
    QTabBar::tab {{ background: transparent; color: {t.text_dim}; padding: 6px 12px; border: none; }}
    QTabBar::tab:selected {{ color: {t.text}; border-bottom: 2px solid {t.accent}; }}
    QTabBar::tab:hover {{ color: {t.text}; }}
    QCheckBox::indicator {{ width: 14px; height: 14px; border: 1px solid {t.border}; border-radius: 4px; background: {field_bg}; }}
    QCheckBox::indicator:checked {{ background: {t.success}; border-color: {t.success}; {check_rule} }}
    QCheckBox:focus {{ color: {t.accent}; }}
    QSlider::groove:horizontal {{ height: 4px; background: {t.border}; border-radius: 2px; }}
    QSlider::handle:horizontal {{ width: 12px; height: 12px; margin: -5px 0; background: {t.accent}; border-radius: 6px; }}
    QScrollBar:vertical {{ width: 8px; background: transparent; }}
    QScrollBar::handle:vertical {{ background: {t.border}; border-radius: 4px; min-height: 24px; }}
    QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; }}
    QMenu {{ background: {t.panel}; border: 1px solid {t.border}; padding: 4px; }}
    QMenu::item {{ padding: 5px 18px; border-radius: 5px; }}
    QMenu::item:selected {{ background: {t.accent}; color: {t.outline}; }}
    QMenu::separator {{ height: 1px; background: {t.border}; margin: 4px 6px; }}
    QProgressBar {{ background: {t.border}; border: none; border-radius: 3px; height: 6px; text-align: center; }}
    QProgressBar::chunk {{ background: {t.accent}; border-radius: 3px; }}
    QGroupBox {{ border: 1px solid {t.border}; border-radius: 8px; margin-top: 12px; padding-top: 8px; }}
    QGroupBox::title {{ subcontrol-origin: margin; left: 10px; color: {t.text_dim}; }}
    """
