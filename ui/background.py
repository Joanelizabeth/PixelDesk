"""The plain, dark gradient background with subtle texture, faint stars and a
few restrained pixel accents. Rendered once per size and cached."""
from __future__ import annotations

import random
from pathlib import Path

from PySide6.QtCore import QPointF, QRect, QRectF, QSize, Qt
from PySide6.QtGui import QColor, QImage, QLinearGradient, QPainter, QPixmap, QRadialGradient

from .theme import Theme

_cache: dict[tuple, QPixmap] = {}


def _noise_tile(dark: bool) -> QImage:
    rnd = random.Random(7)
    tile = QImage(96, 96, QImage.Format.Format_ARGB32_Premultiplied)
    tile.fill(Qt.GlobalColor.transparent)
    for _ in range(900):
        x, y = rnd.randrange(96), rnd.randrange(96)
        a = rnd.randint(4, 11)
        tile.setPixelColor(x, y, QColor(255, 255, 255, a) if dark else QColor(60, 40, 90, a))
    return tile


def render_background(size: QSize, theme: Theme, brightness: float = 1.0, custom_image: str = "") -> QPixmap:
    key = (size.width(), size.height(), theme.key, round(brightness, 2), custom_image)
    if key in _cache:
        return _cache[key]
    if len(_cache) > 6:
        _cache.clear()
    w, h = max(1, size.width()), max(1, size.height())
    pm = QPixmap(w, h)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)

    custom = QImage(custom_image) if custom_image and Path(custom_image).is_file() else QImage()
    if not custom.isNull():
        scaled = custom.scaled(w, h, Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                               Qt.TransformationMode.SmoothTransformation)
        p.drawImage(QRect(0, 0, w, h), scaled, QRect((scaled.width() - w) // 2, (scaled.height() - h) // 2, w, h))
        # A soft scrim keeps widgets readable on any picture.
        p.fillRect(0, 0, w, h, theme.c("bg_bottom", 0.45))
    else:
        grad = QLinearGradient(QPointF(0, 0), QPointF(w * 0.35, h))
        grad.setColorAt(0.0, theme.c("bg_top"))
        grad.setColorAt(1.0, theme.c("bg_bottom"))
        p.fillRect(0, 0, w, h, grad)
        # Two very soft glows: one behind the wheel, one behind the companion.
        for cx, cy, r, alpha in ((0.24, 0.48, 0.55, 0.38), (0.80, 0.38, 0.42, 0.22)):
            glow = QRadialGradient(QPointF(w * cx, h * cy), max(w, h) * r)
            glow.setColorAt(0.0, theme.c("bg_glow", alpha))
            glow.setColorAt(1.0, theme.c("bg_glow", 0.0))
            p.fillRect(0, 0, w, h, glow)
        p.fillRect(0, 0, w, h, _noise_tile(theme.dark))

        rnd = random.Random(42)
        star = theme.c("star")
        p.setPen(Qt.PenStyle.NoPen)
        px = max(2, round(min(w, h) / 540))
        count = int(w * h / 9000)
        for _ in range(count):
            x, y = rnd.random() * w, rnd.random() * h * 0.92
            star.setAlphaF(rnd.uniform(0.08, 0.32) if theme.dark else rnd.uniform(0.25, 0.5))
            p.setBrush(star)
            p.drawRect(QRectF(int(x), int(y), px * (1 if rnd.random() < 0.85 else 2), px))
        # A handful of tiny pixel "plus" sparkles.
        for _ in range(max(6, count // 40)):
            x, y = int(rnd.random() * w), int(rnd.random() * h * 0.8)
            star.setAlphaF(rnd.uniform(0.25, 0.5) if theme.dark else 0.6)
            p.setBrush(star)
            p.drawRect(x, y, px, px)
            p.drawRect(x - px, y, px, px)
            p.drawRect(x + px, y, px, px)
            p.drawRect(x, y - px, px, px)
            p.drawRect(x, y + px, px, px)
        # Pixel horizon: two layers of gentle, stepped hills along the bottom edge.
        import math

        step = px * 4
        for layer, (alpha, amp, base_h, freq, phase) in enumerate(((0.22, 0.022, 0.018, 2.1, 0.7),
                                                                      (0.38, 0.014, 0.010, 3.3, 2.1))):
            p.setBrush(theme.c("bg_glow", alpha if theme.dark else alpha + 0.2))
            for i in range(0, w + step, step):
                t = i / max(1, w)
                height = (base_h + amp * (0.5 + 0.5 * math.sin(t * math.pi * freq + phase))) * h
                height = int(height // px * px)
                p.drawRect(i, h - height, step, height)

    if brightness != 1.0:
        if brightness < 1.0:
            p.fillRect(0, 0, w, h, QColor(0, 0, 0, int(255 * min(0.8, 1.0 - brightness))))
        else:
            p.fillRect(0, 0, w, h, QColor(255, 255, 255, int(255 * min(0.35, (brightness - 1.0) * 0.5))))
    p.end()
    _cache[key] = pm
    return pm
