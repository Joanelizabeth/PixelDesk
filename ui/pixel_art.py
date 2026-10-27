"""Original pixel art, generated in code: launcher icons, a 5x7 bitmap font for
the clock/timer, and the procedural chibi companion ("Pip").

Everything is drawn into small QImages and scaled with nearest-neighbour
sampling, so pixels stay crisp at any size.
"""
from __future__ import annotations

from functools import lru_cache
from typing import Optional

from PySide6.QtCore import QPoint, QRect, Qt
from PySide6.QtGui import QColor, QIcon, QImage, QPainter, QPixmap

# ============================================================== icons (12x12)
# o = outline, a = main, b = main (darker), c = main (lighter), w = white-ish, x = accent
ICONS: dict[str, list[str]] = {
    "folder": [
        "............", "............", ".oooo.......", "oaaaaoooooo.", "oaaaaaaaaaao", "occcccccccco",
        "obbbbbbbbbbo", "obbbbbbbbbbo", "obbbbbbbbbbo", "obbbbbbbbbbo", "oooooooooooo", "............",
    ],
    "book": [
        "............", ".oooooooooo.", ".obaaaaaaao.", ".obaccccaao.", ".obaaaaaaao.", ".obaccaaaao.",
        ".obaaaaaaao.", ".obaaaaaaao.", ".obaaaaaaao.", ".obwwwwwwwo.", ".oooooooooo.", "............",
    ],
    "note": [
        "............", "..ooooooo...", "..owwwwwoo..", "..owwwwwowo.", "..owaaaawwo.", "..owwwwwwwo.",
        "..owaaaaawo.", "..owwwwwwwo.", "..owaaawwwo.", "..owwwwwwwo.", "..ooooooooo.", "............",
    ],
    "star": [
        ".....oo.....", "....oaao....", "....oaao....", "oooooaaooooo", "oaaaaacaaaao", ".oaaacaaaao.",
        "..oaaaaaao..", "..oaaaaaao..", ".oaaaooaaao.", ".oaao..oaao.", "oaoo....ooao", "oo........oo",
    ],
    "heart": [
        "............", ".oooo..oooo.", "oaacaooaaaao", "oacaaaaaaaao", "oaaaaaaaaaao", "oaaaaaaaaaao",
        ".oaaaaaaaao.", "..oaaaaaao..", "...oaaaao...", "....oaao....", ".....oo.....", "............",
    ],
    "music": [
        "......oo....", "......oao...", "......oaao..", "......oaoao.", "......oao.o.", "......oao...",
        "......oao...", "...oooaao...", "..oaaaaao...", "..oacaaao...", "...oaaao....", "....ooo.....",
    ],
    "image": [
        "............", "oooooooooooo", "obbbbbbbbbbo", "obbbbbbbxxbo", "obbbbbbbxxbo", "obbbbabbbbbo",
        "obbbaaabbbbo", "obbaaaaabbao", "obaaaaaaaaao", "oaaaaaaaaaao", "oooooooooooo", "............",
    ],
    "download": [
        ".....oo.....", "....oaao....", "....oaao....", "....oaao....", "....oaao....", ".ooooaaoooo.",
        "..oaaaaaao..", "...oaaaao...", "o...oaao...o", "oo...oo...oo", "oaaaaaaaaaao", "oooooooooooo",
    ],
    "game": [
        "............", "............", "..oooooooo..", ".oaaaaaaaao.", "oaawaaaaxaao", "oawwwaaxaxao",
        "oaawaaaaxaao", "oaaaaooaaaao", "oaaao..oaaao", ".ooo....ooo.", "............", "............",
    ],
    "globe": [
        "............", "....oooo....", "..ooaaaaoo..", ".oaaccaaaao.", ".oaccccaaao.", "oaaccccaaaao",
        "oaaaccaaacao", "oaaaaaacccao", ".oaaaaaccao.", ".oaaaaaaaao.", "..ooaaaaoo..", "....oooo....",
    ],
    "gear": [
        "....oooo....", "..o.oaao.o..", ".oaooaaooao.", "..oaaaaaao..", "ooaaaooaaaoo", "oaaao..oaaao",
        "oaaao..oaaao", "ooaaaooaaaoo", "..oaaaaaao..", ".oaooaaooao.", "..o.oaao.o..", "....oooo....",
    ],
    "camera": [
        "............", "............", "...oooo.....", "oooaaaaooooo", "oaaaooooaxao", "oaaowwwoaaao",
        "oaaowcwoaaao", "oaaowwwoaaao", "oaaaoooaaaao", "oaaaaaaaaaao", "oooooooooooo", "............",
    ],
    "rocket": [
        ".....oo.....", "....oaao....", "...oaaaao...", "...oawwao...", "...oawwao...", "...oaaaao...",
        "..ooaaaaoo..", ".oxoaaaaoxo.", ".oxooooooxo.", ".oo.oxxo.oo.", ".....xx.....", "......x.....",
    ],
    "cap": [
        "............", "............", ".....oo.....", "...ooaaoo...", ".ooaaaaaaoo.", "oaaaaaaaaaao",
        ".ooaaaaaaoxo", "..oabbbbaoxo", "..obbbbbbo.x", "..obbbbbbo..", "...oooooo...", "............",
    ],
    "code": [
        "............", "oooooooooooo", "obbbbbbbbbbo", "oooooooooooo", "oaaaaaaaaaao", "oacaaaaaaaao",
        "oaacaaaaaaao", "oacaaaaaaaao", "oaaaaccccaao", "oaaaaaaaaaao", "oooooooooooo", "............",
    ],
    "app": [
        "............", "oooooooooooo", "owbxbbbbbbbo", "oooooooooooo", "oaaaaaaaaaao", "oacccaaaaaao",
        "oaaaaaaaaaao", "oacccccaaaao", "oaaaaaaaaaao", "oaaaaaaaaaao", "oooooooooooo", "............",
    ],
    "moon": [
        "...ooooo....", ".ooaaaao....", ".oaaaao.....", "oaaaao......", "oaaao.......", "oaaao.......",
        "oaaao.......", "oaaaao.....o", ".oaaaaao..oo", ".ooaaaaaaao.", "...ooaaaoo..", ".....ooo....",
    ],
    "flame": [
        ".....o......", ".....oo.....", "....oaao....", "....oaao.o..", "...oaaaaoao.", "..oaaaaaaao.",
        "..oaaxxaaao.", ".oaaxxxxaao.", ".oaxxwwxxao.", ".oaxwwwwxao.", "..oaxwwxao..", "...oooooo...",
    ],
    "drop": [
        ".....oo.....", "....oaao....", "....oaao....", "...oaaaao...", "...oaaaao...", "..oaaaaaao..",
        "..owaaaaao..", ".oawaaaaaao.", ".oawaaaaaao.", ".oaawaaaaao.", "..oaaaaaao..", "...oooooo...",
    ],
    "walk": [
        "....oooo....", "...oaaaao...", "...oaaaao...", "o...oooo...o", "oao.oaao.oao", ".oaooaaooao.",
        "..oaaaaaao..", "....oaao....", "...oaooao...", "..oao..oao..", ".oao....oao.", ".oo......oo.",
    ],
    "tasks": [
        "....oooo....", ".oooaaaaooo.", ".owwoooowwo.", ".owwwwwwwwo.", ".owwwwwwawo.", ".owwwwwawwo.",
        ".owawwawwwo.", ".owwaawwwwo.", ".owwwwwwwwo.", ".owwwwwwwwo.", ".oooooooooo.", "............",
    ],
    "screen": [
        "............", "oooooooooooo", "obbbbbbbbbbo", "obcbbbbbbbbo", "obbbbbbbbbbo", "obbbbbbbbbbo",
        "obbbbbbbbbbo", "oooooooooooo", ".....oo.....", "....oaao....", "...oooooo...", "............",
    ],
    "play": [
        "............", "..oo........", "..oaoo......", "..oaaaoo....", "..oaaaaaoo..", "..oaaaaaaao.",
        "..oaaaaaaao.", "..oaaaaaoo..", "..oaaaoo....", "..oaoo......", "..oo........", "............",
    ],
    "pause": [
        "............", "..oooo.oooo.", "..oaao.oaao.", "..oaao.oaao.", "..oaao.oaao.", "..oaao.oaao.",
        "..oaao.oaao.", "..oaao.oaao.", "..oaao.oaao.", "..oaao.oaao.", "..oooo.oooo.", "............",
    ],
    "stop": [
        "............", "............", "..oooooooo..", "..oaaaaaao..", "..oaccccao..", "..oacaaaao..",
        "..oacaaaao..", "..oaaaaaao..", "..oaaaaaao..", "..oooooooo..", "............", "............",
    ],
    "plus": [
        "............", "....oooo....", "....oaao....", "....oaao....", ".ooooaaoooo.", ".oaaaaaaaao.",
        ".oaaaaaaaao.", ".ooooaaoooo.", "....oaao....", "....oaao....", "....oooo....", "............",
    ],
}

LAUNCHER_ICON_CHOICES = [
    "folder", "book", "note", "code", "cap", "rocket", "star", "heart", "music", "image", "camera",
    "download", "game", "globe", "gear", "app", "moon",
]


def _shade(color: QColor, factor: float) -> QColor:
    return color.darker(int(100 / factor)) if factor < 1 else color.lighter(int(100 * factor))


@lru_cache(maxsize=512)
def icon_image(name: str, main: str, outline: str, accent: str = "#d9a0b6") -> QImage:
    rows = ICONS.get(name, ICONS["app"])
    base = QColor(main)
    palette = {
        "o": QColor(outline), "a": base, "b": _shade(base, 0.78), "c": _shade(base, 1.25),
        "w": QColor("#fbf6ec"), "x": QColor(accent),
    }
    img = QImage(12, 12, QImage.Format.Format_ARGB32_Premultiplied)
    img.fill(Qt.GlobalColor.transparent)
    for y, row in enumerate(rows):
        for x, ch in enumerate(row):
            if ch in palette:
                img.setPixelColor(x, y, palette[ch])
    return img


def draw_pixel_image(p: QPainter, img: QImage, target: QRect) -> None:
    p.save()
    p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, False)
    p.drawImage(target, img)
    p.restore()


def icon_pixmap(name: str, main: str, outline: str, size: int = 24, accent: str = "#d9a0b6") -> QPixmap:
    img = icon_image(name, main, outline, accent)
    return QPixmap.fromImage(img.scaled(size, size, Qt.AspectRatioMode.IgnoreAspectRatio,
                                        Qt.TransformationMode.FastTransformation))


def qicon(name: str, main: str, outline: str, size: int = 24) -> QIcon:
    return QIcon(icon_pixmap(name, main, outline, size))


# ============================================================== 5x7 bitmap font
FONT: dict[str, list[str]] = {
    "0": [".###.", "#...#", "#..##", "#.#.#", "##..#", "#...#", ".###."],
    "1": ["..#..", ".##..", "..#..", "..#..", "..#..", "..#..", ".###."],
    "2": [".###.", "#...#", "....#", "...#.", "..#..", ".#...", "#####"],
    "3": ["####.", "....#", "....#", ".###.", "....#", "....#", "####."],
    "4": ["...#.", "..##.", ".#.#.", "#..#.", "#####", "...#.", "...#."],
    "5": ["#####", "#....", "####.", "....#", "....#", "#...#", ".###."],
    "6": ["..##.", ".#...", "#....", "####.", "#...#", "#...#", ".###."],
    "7": ["#####", "....#", "...#.", "..#..", ".#...", ".#...", ".#..."],
    "8": [".###.", "#...#", "#...#", ".###.", "#...#", "#...#", ".###."],
    "9": [".###.", "#...#", "#...#", ".####", "....#", "...#.", ".##.."],
    ":": ["..", "##", "##", "..", "##", "##", ".."],
    ".": ["..", "..", "..", "..", "..", "##", "##"],
    "-": ["....", "....", "....", "####", "....", "....", "...."],
    "/": ["....#", "...#.", "...#.", "..#..", ".#...", ".#...", "#...."],
    "+": [".....", "..#..", "..#..", "#####", "..#..", "..#..", "....."],
    "!": ["#", "#", "#", "#", "#", ".", "#"],
    "%": ["##..#", "##..#", "...#.", "..#..", ".#...", "#..##", "#..##"],
    " ": ["...", "...", "...", "...", "...", "...", "..."],
    "A": [".###.", "#...#", "#...#", "#####", "#...#", "#...#", "#...#"],
    "B": ["####.", "#...#", "#...#", "####.", "#...#", "#...#", "####."],
    "C": [".###.", "#...#", "#....", "#....", "#....", "#...#", ".###."],
    "D": ["####.", "#...#", "#...#", "#...#", "#...#", "#...#", "####."],
    "E": ["#####", "#....", "#....", "####.", "#....", "#....", "#####"],
    "F": ["#####", "#....", "#....", "####.", "#....", "#....", "#...."],
    "G": [".###.", "#...#", "#....", "#.###", "#...#", "#...#", ".####"],
    "H": ["#...#", "#...#", "#...#", "#####", "#...#", "#...#", "#...#"],
    "I": [".###.", "..#..", "..#..", "..#..", "..#..", "..#..", ".###."],
    "J": ["..###", "...#.", "...#.", "...#.", "...#.", "#..#.", ".##.."],
    "K": ["#...#", "#..#.", "#.#..", "##...", "#.#..", "#..#.", "#...#"],
    "L": ["#....", "#....", "#....", "#....", "#....", "#....", "#####"],
    "M": ["#...#", "##.##", "#.#.#", "#.#.#", "#...#", "#...#", "#...#"],
    "N": ["#...#", "#...#", "##..#", "#.#.#", "#..##", "#...#", "#...#"],
    "O": [".###.", "#...#", "#...#", "#...#", "#...#", "#...#", ".###."],
    "P": ["####.", "#...#", "#...#", "####.", "#....", "#....", "#...."],
    "Q": [".###.", "#...#", "#...#", "#...#", "#.#.#", "#..#.", ".##.#"],
    "R": ["####.", "#...#", "#...#", "####.", "#.#..", "#..#.", "#...#"],
    "S": [".####", "#....", "#....", ".###.", "....#", "....#", "####."],
    "T": ["#####", "..#..", "..#..", "..#..", "..#..", "..#..", "..#.."],
    "U": ["#...#", "#...#", "#...#", "#...#", "#...#", "#...#", ".###."],
    "V": ["#...#", "#...#", "#...#", "#...#", "#...#", ".#.#.", "..#.."],
    "W": ["#...#", "#...#", "#...#", "#.#.#", "#.#.#", "#.#.#", ".#.#."],
    "X": ["#...#", "#...#", ".#.#.", "..#..", ".#.#.", "#...#", "#...#"],
    "Y": ["#...#", "#...#", ".#.#.", "..#..", "..#..", "..#..", "..#.."],
    "Z": ["#####", "....#", "...#.", "..#..", ".#...", "#....", "#####"],
}


def pixel_text_width(text: str, scale: int, spacing: int = 1) -> int:
    widths = [len(FONT.get(ch.upper(), FONT[" "])[0]) for ch in text]
    return (sum(widths) + spacing * max(0, len(widths) - 1)) * scale


def draw_pixel_text(p: QPainter, text: str, origin: QPoint, scale: int, color: QColor,
                    shadow: Optional[QColor] = None, spacing: int = 1) -> int:
    """Draw text in the bitmap font; returns the drawn width."""
    p.save()
    p.setPen(Qt.PenStyle.NoPen)
    passes = [(shadow, scale // 2 or 1)] if shadow is not None else []
    passes.append((color, 0))
    width = 0
    for col, off in passes:
        x = origin.x() + off
        p.setBrush(col)
        for ch in text:
            glyph = FONT.get(ch.upper(), FONT[" "])
            for gy, row in enumerate(glyph):
                for gx, bit in enumerate(row):
                    if bit == "#":
                        p.drawRect(x + gx * scale, origin.y() + off + gy * scale, scale, scale)
            x += (len(glyph[0]) + spacing) * scale
        width = x - origin.x() - off - spacing * scale
    p.restore()
    return width


# ============================================================== companion sprite
SPRITE_W = SPRITE_H = 32

STATES = ("idle", "working", "happy", "sleepy", "water", "movement", "achievement")


class _Grid:
    def __init__(self) -> None:
        self.cells: list[list[Optional[str]]] = [[None] * SPRITE_W for _ in range(SPRITE_H)]

    def px(self, x: int, y: int, c: Optional[str]) -> None:
        if 0 <= x < SPRITE_W and 0 <= y < SPRITE_H:
            self.cells[y][x] = c

    def rect(self, x0: int, y0: int, x1: int, y1: int, c: Optional[str]) -> None:
        for y in range(y0, y1 + 1):
            for x in range(x0, x1 + 1):
                self.px(x, y, c)

    def ellipse(self, cx: float, cy: float, rx: float, ry: float, c: str) -> None:
        for y in range(SPRITE_H):
            for x in range(SPRITE_W):
                if ((x - cx) / rx) ** 2 + ((y - cy) / ry) ** 2 <= 1.0:
                    self.px(x, y, c)

    def line(self, x0: int, y0: int, x1: int, y1: int, c: str, thick: int = 2) -> None:
        steps = max(abs(x1 - x0), abs(y1 - y0), 1)
        for i in range(steps + 1):
            x = round(x0 + (x1 - x0) * i / steps)
            y = round(y0 + (y1 - y0) * i / steps)
            self.rect(x, y, x + thick - 1, y + thick - 1, c)

    def outline(self, color: str = "o") -> None:
        filled = [[c is not None for c in row] for row in self.cells]
        for y in range(SPRITE_H):
            for x in range(SPRITE_W):
                if filled[y][x]:
                    continue
                for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    nx, ny = x + dx, y + dy
                    if 0 <= nx < SPRITE_W and 0 <= ny < SPRITE_H and filled[ny][nx]:
                        self.cells[y][x] = color
                        break


def _arms(g: _Grid, pose: str, dy: int, frame: int) -> None:
    sy = 19 + dy  # shoulder row
    if pose == "down":
        g.rect(9, sy, 10, sy + 4, "t")
        g.rect(9, sy + 5, 10, sy + 5, "s")
        g.rect(21, sy, 22, sy + 4, "t")
        g.rect(21, sy + 5, 22, sy + 5, "s")
    elif pose == "swing":
        a, b = (0, 1) if frame % 2 == 0 else (1, 0)
        g.line(10, sy, 9 - a, sy + 4, "t")
        g.rect(9 - a, sy + 5, 10 - a, sy + 5, "s")
        g.line(21, sy, 22 + b, sy + 4, "t")
        g.rect(22 + b, sy + 5, 23 + b, sy + 5, "s")
    elif pose == "up":
        g.line(10, sy, 7, sy - 7, "t")
        g.rect(6, sy - 9, 7, sy - 8, "s")
        g.line(21, sy, 24, sy - 7, "t")
        g.rect(24, sy - 9, 25, sy - 8, "s")
    elif pose == "stretch":
        g.line(10, sy, 9, sy - 10, "t")
        g.rect(9, sy - 12, 10, sy - 11, "s")
        g.line(21, sy, 22, sy - 10, "t")
        g.rect(21, sy - 12, 22, sy - 11, "s")
    elif pose == "wave":
        g.rect(9, sy, 10, sy + 4, "t")
        g.rect(9, sy + 5, 10, sy + 5, "s")
        tip = 25 if frame % 2 == 0 else 24
        g.line(21, sy, 23, sy - 5, "t")
        g.rect(tip - 1, sy - 8, tip, sy - 6, "s")
    elif pose == "glass":
        g.rect(9, sy, 10, sy + 4, "t")
        g.rect(9, sy + 5, 10, sy + 5, "s")
        if frame % 8 < 5:  # holding the glass out
            g.line(21, sy, 23, sy - 2, "t")
            g.rect(23, sy - 4, 24, sy - 3, "s")
            g.rect(23, sy - 9, 26, sy - 5, "g")
            g.rect(23, sy - 9, 26, sy - 9, "G")
        else:  # sipping
            g.line(21, sy, 20, sy - 2, "t")
            g.rect(19, sy - 4, 20, sy - 3, "s")
            g.rect(18, sy - 8, 21, sy - 5, "g")
            g.rect(18, sy - 8, 21, sy - 8, "G")
    elif pose == "type":
        lift_l = 1 if frame % 2 == 0 else 0
        lift_r = 1 - lift_l
        g.rect(9, sy, 10, sy + 3, "t")
        g.rect(21, sy, 22, sy + 3, "t")
        g.rect(9, sy + 4 - lift_l, 10, sy + 4 - lift_l, "s")
        g.rect(21, sy + 4 - lift_r, 22, sy + 4 - lift_r, "s")


def _body(g: _Grid, dy: int, eyes: str, mouth: str, arms: str, legs: str, frame: int) -> None:
    # hair (back) and face
    g.ellipse(15.5, 10.5 + dy, 9.2, 8.6, "h")
    g.rect(7, 12 + dy, 24, 18 + dy, "h")
    g.rect(10, 8 + dy, 21, 17 + dy, "s")
    g.px(10, 17 + dy, "h")
    g.px(21, 17 + dy, "h")
    g.rect(10, 7 + dy, 21, 9 + dy, "h")
    for x in (10, 11, 12, 15, 16, 19, 20, 21):
        g.px(x, 10 + dy, "h")
    for x, y in ((12, 5), (13, 4), (14, 4), (15, 4)):
        g.px(x, y + dy, "H")
    # eyes
    if eyes == "open":
        for x in (12, 18):
            g.rect(x, 12 + dy, x + 1, 14 + dy, "e")
            g.px(x, 12 + dy, "w")
    elif eyes == "blink":
        for x in (12, 18):
            g.rect(x, 14 + dy, x + 1, 14 + dy, "e")
    elif eyes == "happy":
        for x in (11, 18):
            g.px(x, 13 + dy, "e")
            g.px(x + 1, 12 + dy, "e")
            g.px(x + 2, 13 + dy, "e")
    elif eyes == "sleepy":
        for x in (11, 18):
            g.px(x, 13 + dy, "e")
            g.px(x + 1, 14 + dy, "e")
            g.px(x + 2, 13 + dy, "e")
    elif eyes == "focus":
        for x in (12, 18):
            g.rect(x, 13 + dy, x + 1, 14 + dy, "e")
            g.px(x + 1, 13 + dy, "w")
    # cheeks + mouth
    for x in (10, 11, 20, 21):
        g.px(x, 15 + dy, "c")
    if mouth == "smile":
        g.px(15, 16 + dy, "m")
        g.px(16, 16 + dy, "m")
    elif mouth == "open":
        g.rect(15, 15 + dy, 16, 16 + dy, "m")
    elif mouth == "small":
        g.px(16, 16 + dy, "m")
    # neck, torso
    g.rect(14, 18 + dy, 17, 18 + dy, "S")
    g.rect(11, 19 + dy, 20, 25, "t")
    g.rect(11, 19 + dy, 11, 25, "T")
    g.rect(11, 25, 20, 25, "T")
    g.px(14, 19 + dy, "w")
    g.px(17, 19 + dy, "w")
    g.px(16, 22 + dy, "x")
    _arms(g, arms, dy, frame)
    # legs
    if legs == "walk":
        up_left = frame % 2 == 0
        g.rect(12, 26, 14, 27 if up_left else 28, "p")
        g.rect(17, 26, 19, 28 if up_left else 27, "p")
        g.rect(11, 28 if up_left else 29, 14, 28 if up_left else 29, "b")
        g.rect(17, 29 if up_left else 28, 20, 29 if up_left else 28, "b")
    elif legs == "jump":
        g.rect(12, 26, 14, 27, "p")
        g.rect(17, 26, 19, 27, "p")
        g.rect(11, 28, 14, 28, "b")
        g.rect(17, 28, 20, 28, "b")
    else:
        g.rect(12, 26, 14, 28, "p")
        g.rect(17, 26, 19, 28, "p")
        g.rect(11, 29, 14, 29, "b")
        g.rect(17, 29, 20, 29, "b")


def _sparkle(g: _Grid, x: int, y: int, c: str = "y") -> None:
    g.px(x, y, c)
    g.px(x - 1, y, c)
    g.px(x + 1, y, c)
    g.px(x, y - 1, c)
    g.px(x, y + 1, c)


def build_frame(state: str, frame: int) -> _Grid:
    g = _Grid()
    blink = frame % 23 == 22
    if state == "working":
        _body(g, 0, "blink" if blink else "focus", "small", "type", "stand", frame)
        g.rect(3, 25, 28, 26, "d")  # desk
        g.rect(9, 19, 22, 24, "l")  # laptop lid (back)
        g.rect(9, 19, 22, 19, "L")
        g.px(15, 21, "x")
        g.px(16, 21, "x")
        g.rect(3, 27, 28, 27, "D")
        g.outline()
        # hands resting on the keyboard edge in front of the lid
        lift = frame % 2
        g.rect(8, 23 + lift, 9, 24 + lift, "s")
        g.rect(22, 24 - lift, 23, 25 - lift, "s")
    elif state == "happy":
        dy = -2 if frame % 2 == 0 else 0
        _body(g, dy, "happy", "open", "up", "jump" if dy else "stand", frame)
        g.outline()
        for (x, y) in ((4, 6), (27, 4)) if frame % 2 == 0 else ((5, 12), (27, 10)):
            _sparkle(g, x, y, "x")
    elif state == "sleepy":
        dy = 1 if (frame // 4) % 2 else 0
        _body(g, dy, "sleepy", "small", "down", "stand", frame)
        g.outline()
        k = frame % 9
        for i, (zx, zy) in enumerate(((23, 6), (26, 3), (29, 0))):
            if i <= k // 3:
                g.rect(zx, zy, zx + 2, zy, "z")
                g.px(zx + 1, zy + 1, "z")
                g.rect(zx, zy + 2, zx + 2, zy + 2, "z")
    elif state == "water":
        _body(g, 0, "blink" if blink else ("happy" if frame % 8 >= 5 else "open"), "smile", "glass", "stand", frame)
        g.outline()
        if frame % 8 < 5:
            g.px(27, 8 + (frame % 3), "g")
    elif state == "movement":
        if (frame // 6) % 2 == 0:
            _body(g, -1 if frame % 2 else 0, "happy", "open", "stretch", "stand", frame)
        else:
            _body(g, 0, "open", "smile", "swing", "walk", frame)
        g.outline()
    elif state == "achievement":
        dy = -1 if frame % 2 == 0 else 0
        _body(g, dy, "happy", "open", "up", "stand", frame)
        # a star held up in the right hand
        for row, xs in enumerate(((26,), (25, 26, 27), (24, 25, 26, 27, 28), (25, 26, 27), (25, 27))):
            for x in xs:
                g.px(x, 4 + dy + row, "y")
        g.outline()
        pts = ((3, 4), (29, 13), (5, 16)) if frame % 2 == 0 else ((22, 2), (3, 10), (28, 17))
        for x, y in pts:
            _sparkle(g, x, y, "x")
    elif state == "wave":
        _body(g, 0, "happy", "smile", "wave", "stand", frame)
        g.outline()
    else:  # idle: slow breathing + occasional blink
        dy = 1 if (frame // 5) % 2 else 0
        _body(g, dy, "blink" if blink else "open", "smile", "down", "stand", frame)
        g.outline()
    return g


def sprite_palette(hair: str, outfit: str, outline: str, accent: str = "#d9a0b6") -> dict[str, QColor]:
    h, t = QColor(hair), QColor(outfit)
    return {
        "o": QColor(outline), "h": h, "H": h.lighter(125), "s": QColor("#f8dccb"), "S": QColor("#e6b9a6"),
        "e": QColor("#2a2040"), "w": QColor("#fffaf0"), "c": QColor("#f0a0b4"), "m": QColor("#a8475f"),
        "t": t, "T": t.darker(125), "p": QColor("#4b4466"), "b": QColor("#2a2040"),
        "l": QColor("#d4cfe0"), "L": QColor("#9d97b3"), "g": QColor("#9fd3ef"), "G": QColor("#f4fbff"),
        "d": QColor("#6f5c82"), "D": QColor("#4d405c"), "y": QColor("#f2c46b"), "z": QColor("#c9b8f2"),
        "x": QColor(accent),
    }


@lru_cache(maxsize=256)
def sprite_image(state: str, frame: int, hair: str, outfit: str, outline: str, accent: str) -> QImage:
    grid = build_frame(state, frame)
    pal = sprite_palette(hair, outfit, outline, accent)
    img = QImage(SPRITE_W, SPRITE_H, QImage.Format.Format_ARGB32_Premultiplied)
    img.fill(Qt.GlobalColor.transparent)
    for y, row in enumerate(grid.cells):
        for x, key in enumerate(row):
            if key is not None:
                img.setPixelColor(x, y, pal[key])
    return img


def app_icon(size: int = 256) -> QIcon:
    """The Pixel Desk app icon: the companion's face on a lavender tile."""
    icon = QIcon()
    for s in (16, 24, 32, 48, 64, 128, 256):
        pm = QPixmap(s, s)
        pm.fill(Qt.GlobalColor.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setBrush(QColor("#2a2140"))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawRoundedRect(0, 0, s, s, s * 0.22, s * 0.22)
        img = sprite_image("idle", 0, "#c99ad6", "#8f9fd9", "#151020", "#d9a0b6").copy(4, 1, 24, 22)
        target = QRect(int(s * 0.08), int(s * 0.1), int(s * 0.84), int(s * 0.84 * 22 / 24))
        draw_pixel_image(p, img, target)
        p.end()
        icon.addPixmap(pm)
    return icon
