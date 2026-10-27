"""Export the procedural pixel art to PNG/ICO files under assets/.

Run:  python scripts/generate_assets.py
The application draws everything in code; these files are used for the
Windows executable icon and as a reference sprite sheet.
"""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPoint, QRect  # noqa: E402
from PySide6.QtGui import QColor, QGuiApplication, QImage, QPainter  # noqa: E402

from ui.pixel_art import (  # noqa: E402
    ICONS, STATES, app_icon, draw_pixel_image, draw_pixel_text, icon_image, sprite_image,
)


def main() -> None:
    app = QGuiApplication.instance() or QGuiApplication(sys.argv)
    (ROOT / "assets" / "characters").mkdir(parents=True, exist_ok=True)
    (ROOT / "assets" / "icons").mkdir(parents=True, exist_ok=True)

    scale, frames = 5, 8
    sheet = QImage(32 * scale * frames, (32 * scale + 24) * len(STATES), QImage.Format.Format_ARGB32)
    sheet.fill(QColor("#1d1826"))
    p = QPainter(sheet)
    for row, state in enumerate(STATES):
        y = row * (32 * scale + 24)
        draw_pixel_text(p, state.upper(), QPoint(6, y + 6), 2, QColor("#a99fbd"))
        for f in range(frames):
            img = sprite_image(state, f, "#c99ad6", "#8f9fd9", "#151020", "#d9a0b6")
            draw_pixel_image(p, img, QRect(f * 32 * scale, y + 24, 32 * scale, 32 * scale))
    p.end()
    sheet.save(str(ROOT / "assets" / "characters" / "pip_sprite_sheet.png"))

    names = list(ICONS)
    cols = 8
    rows = (len(names) + cols - 1) // cols
    sheet = QImage(cols * 72, rows * 72, QImage.Format.Format_ARGB32)
    sheet.fill(QColor("#1d1826"))
    p = QPainter(sheet)
    for i, name in enumerate(names):
        draw_pixel_image(p, icon_image(name, "#b9a6e8", "#151020"), QRect((i % cols) * 72 + 12, (i // cols) * 72 + 12, 48, 48))
    p.end()
    sheet.save(str(ROOT / "assets" / "icons" / "icon_sheet.png"))

    icon = app_icon()
    icon.pixmap(256, 256).save(str(ROOT / "assets" / "icons" / "pixeldesk.png"))
    icon.pixmap(256, 256).save(str(ROOT / "assets" / "icons" / "pixeldesk.ico"))
    print("Assets written to", ROOT / "assets")
    app.quit()


if __name__ == "__main__":
    main()
