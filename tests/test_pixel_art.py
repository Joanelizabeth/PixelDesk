from ui.pixel_art import FONT, ICONS, STATES, build_frame, sprite_image


def test_icons_are_12x12():
    for name, rows in ICONS.items():
        assert len(rows) == 12, name
        assert all(len(r) == 12 for r in rows), name


def test_font_glyphs_are_7_rows_and_rectangular():
    for ch, rows in FONT.items():
        assert len(rows) == 7, ch
        assert len({len(r) for r in rows}) == 1, ch


def test_every_state_renders_frames(qapp):
    for state in STATES + ("wave",):
        for frame in range(12):
            grid = build_frame(state, frame)
            assert any(c for row in grid.cells for c in row)
        img = sprite_image(state, 0, "#c99ad6", "#8f9fd9", "#151020", "#d9a0b6")
        assert img.width() == 32 and img.height() == 32
