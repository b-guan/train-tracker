import random
import re

import pytest
from PIL import Image

from mta_tracker import __main__ as cli
from mta_tracker.arrivals import Arrival
from mta_tracker.display import AsciiBoard, BoardState, MultiDisplay, SplitFlap
from mta_tracker.display import styles as S
from mta_tracker.display.fonts import load_font
from mta_tracker.display.led import LedBoard, format_led_eta, short_headsign
from mta_tracker.display.matrix import preview_image
from mta_tracker.display.panel import PRESETS, PanelConfig, panel_table, parse_pitch

NOW = 1_800_000_000


class FakeClock:
    def __init__(self, t=0.0):
        self.t = t

    def __call__(self):
        return self.t


def state(arrivals, **kw):
    return BoardState("Times Sq-42 St", arrivals, NOW, updated_at=NOW, **kw)


ARRIVALS = [
    Arrival("1", "N", "Van Cortlandt Park-242 St", NOW + 130, "a", "127"),
    Arrival("6X", "N", "Pelham Bay Park", NOW + 250, "b", "127"),
    Arrival("A", "S", "Far Rockaway-Mott Av", NOW + 20, "c", "A27"),
    Arrival("1", "S", "South Ferry", NOW + 720, "d", "127"),
]


# -- panel geometry -------------------------------------------------------------

def test_panel_geometry_and_physical_size():
    p = PanelConfig("64x64", chain=2, pitch_mm=2.5)
    assert (p.width, p.height) == (128, 64)
    assert p.size_mm == (320, 160)
    assert p.describe() == "128x64 px (2x 64x64 modules, P2.5) - 320 x 160 mm (12.6 x 6.3 in)"
    tall = PanelConfig("64x32", chain=2, parallel=2, pitch_mm=4)
    assert (tall.width, tall.height, tall.modules) == (128, 64, 4)
    assert PanelConfig(pitch_mm=2.5).true_size_pixel_px() == 9  # 2.5 mm at 96 dpi


def test_panel_validation():
    with pytest.raises(ValueError):
        PanelConfig("100x50")
    with pytest.raises(ValueError):
        PanelConfig(chain=0)
    assert parse_pitch("P3") == 3.0 and parse_pitch("2.5") == 2.5
    with pytest.raises(ValueError):
        parse_pitch("2.7")


def test_panel_table_lists_every_preset():
    table = panel_table()
    for name in PRESETS:
        assert name in table
    assert "320 x 160" in table  # 128x64 at P2.5


def test_cli_panel_from_args_overrides_preset():
    args = cli.parse_args(["--panel", "128x32", "--pitch", "P3"])
    p = cli.panel_from_args(args)
    assert (p.module, p.chain, p.width, p.height, p.pitch_mm) == ("64x32", 2, 128, 32, 3.0)
    args = cli.parse_args(["--panel", "128x64", "--module", "64x32", "--parallel", "2"])
    p = cli.panel_from_args(args)
    assert (p.width, p.height) == (128, 64)


# -- fonts and text fitting ------------------------------------------------------------

def test_bdf_font_glyphs():
    font = load_font("5x7")
    assert (font.width, font.height) == (5, 7)
    a = font.mask("A")
    rows = ["".join("#" if a.getpixel((x, y)) else "." for x in range(5)) for y in range(7)]
    assert rows[:4] == [".##..", "#..#.", "#..#.", "####."]
    with pytest.raises(ValueError):
        load_font("7x99")


def test_short_headsign():
    assert short_headsign("South Ferry", 18) == "South Ferry"
    assert short_headsign("Coney Island-Stillwell Av", 18) == "Coney Island"
    assert short_headsign("34 St-Hudson Yards", 10) == "Hudson Yar"
    assert short_headsign("Van Cortlandt Park-242 St", 16) == "Van Cortlandt Pk"
    assert format_led_eta(20) == "Now" and format_led_eta(130) == "2m" and format_led_eta(9000) == "99m"


# -- layout ------------------------------------------------------------------------------

def text(grid):
    return ["".join(c.char for c in row) for row in grid]


def test_layout_128x64(index):
    board = LedBoard(PanelConfig("64x64", 2), routes=index.routes, pulse=False)
    assert (board.cols, board.rows, board.font.name) == (25, 8, "5x7")
    grid = board.layout(state(ARRIVALS))
    lines = text(grid)
    assert len(grid) == 8 and all(len(r) == 25 for r in grid)
    assert lines[0].startswith("Times Sq-42 St") and re.search(r" \d{1,2}:\d\d$", lines[0])  # clock
    assert lines[1] == "1 Van Cortlandt Park   2m"
    assert lines[2].startswith("6 Pelham Bay Park")
    assert lines[4] == "A Far Rockaway        Now"
    assert board._separators == [4]  # southbound group starts on row 4
    assert grid[1][0].style == S.route_style("1") and grid[1][1].style == S.route_style("1")
    assert {c.style for c in grid[1][-2:]} == {S.ETA} and {c.style for c in grid[4][-3:]} == {S.NOW}


def test_layout_small_panel_drops_header_and_placeholders(index):
    board = LedBoard(PanelConfig("64x32", 1), routes=index.routes)
    assert (board.cols, board.rows, board.font.name) == (16, 4, "4x6")
    assert not board.show_header
    lines = text(board.layout(BoardState("X", [], NOW)))
    assert lines[0].strip() == "Loading..." and lines[2].strip() == "Loading..."
    lines = text(board.layout(state([])))
    assert lines[0].strip() == "No trains"


# -- rasterizing -------------------------------------------------------------------------

def test_rasterize_draws_bullets_text_and_separator(index):
    board = LedBoard(PanelConfig("64x64", 2), routes=index.routes, pulse=False)
    img = board.rasterize(board.layout(state(ARRIVALS)))
    assert img.size == (128, 64)
    red = (0xD8, 0x22, 0x33)  # the 1 train's color from routes.txt
    bullet = [img.getpixel((x, y)) for x in range(board.x0, board.x0 + 9) for y in range(8, 15)]
    assert red in bullet
    ink = [img.getpixel((x, y)) for x in range(20, 100) for y in range(8, 15)]
    assert (200, 200, 200) in ink  # headsign text
    assert img.getpixel((board.x0, 4 * board.cell_h - 1)) == (60, 60, 60)  # dotted rule


def test_alert_badge_marks_only_alerted_lines(index):
    board = LedBoard(PanelConfig("64x64", 2), routes=index.routes, pulse=False)
    img = board.rasterize(board.layout(state(ARRIVALS, alerted_routes=frozenset({"6"}))))
    red = (255, 50, 40)

    def right_of_bullet(row):  # the spare pixels between the bullet and the headsign
        y = board.y0 + row * board.cell_h
        return [img.getpixel((x, y + dy)) for x in range(board.x0 + 7, board.x0 + 10) for dy in range(3)]

    assert red in right_of_bullet(2)      # 6X express: a "6" alert covers it
    assert red not in right_of_bullet(1)  # 1 train, no alert
    y = board.y0 + 2 * board.cell_h
    assert all(img.getpixel((board.x0 + 6, y + dy)) == (0, 0, 0) for dy in range(3))  # black moat


def test_alert_badge_on_small_letter_bullets(index):
    board = LedBoard(PanelConfig("64x32", 1), routes=index.routes, pulse=False)  # 4x6: no circles
    img = board.rasterize(board.layout(state(ARRIVALS, alerted_routes=frozenset({"1"}))))
    x = board.x0 + board.font.width
    assert img.getpixel((x, board.y0)) == (255, 50, 40)


def test_now_pulses_on_the_panel(index):
    clock = FakeClock(0.0)
    board = LedBoard(PanelConfig("64x64", 2), routes=index.routes, clock=clock)
    board.render(state(ARRIVALS))
    assert board.pulsing and board.animating
    region = (board.x0 + 22 * board.cell_w, 4 * board.cell_h, board.x0 + 25 * board.cell_w, 5 * board.cell_h - 1)
    def colors():
        crop = board.image.crop(region)
        return {crop.getpixel((x, y)) for x in range(crop.width) for y in range(crop.height)} - {(0, 0, 0)}

    bright = colors()
    clock.t = S.PULSE_PERIOD / 2
    board.tick()
    dim = colors()
    assert bright == {S.AMBER_RGB} and dim and max(max(c) for c in dim) < 60


def test_split_flap_on_the_panel_settles_on_target(index):
    clock = FakeClock(100.0)
    flap = SplitFlap(clock=clock, rng=random.Random(0))
    board = LedBoard(PanelConfig("64x64", 2), routes=index.routes, animator=flap, pulse=False, clock=clock)
    board.render(state(ARRIVALS))
    assert board.animating
    clock.t += 5
    board.tick()
    assert not board.animating
    assert text(flap.frame()) == text(board._target)


def test_preview_image_draws_round_leds():
    frame = Image.new("RGB", (4, 2), (0, 0, 0))
    frame.putpixel((1, 0), (255, 0, 0))
    out = preview_image(frame, pixel_size=10)
    assert out.size == (40, 20)
    assert out.getpixel((15, 5)) == (255, 0, 0)    # LED center
    assert out.getpixel((10, 0)) == (18, 18, 18)   # corner between LEDs is background
    assert out.getpixel((35, 5)) == (34, 34, 34)   # unlit LED is faintly visible


# -- displays & CLI ------------------------------------------------------------------------

def test_terminal_layout_is_semantic(index):
    board = AsciiBoard(index.routes, rows=2, color=True, clear=False)
    grid = board.layout(state(ARRIVALS))
    styles = {c.style for row in grid for c in row}
    assert {S.route_style("1"), S.ETA, S.NOW, S.HEADER, S.DIM, S.RULE} <= styles
    assert not any("\x1b" in c.style for row in grid for c in row)


def test_multi_display_forwards():
    calls = []

    class Rec:
        def __init__(self, name, animating):
            self.name, self.animating = name, animating

        def render(self, s):
            calls.append((self.name, "render"))

        def tick(self):
            calls.append((self.name, "tick"))

        def close(self):
            calls.append((self.name, "close"))

    multi = MultiDisplay([Rec("a", False), Rec("b", True)])
    assert multi.animating
    multi.render(None)
    multi.tick()
    multi.close()
    assert calls == [("a", "render"), ("b", "render"), ("a", "tick"), ("b", "tick"), ("a", "close"), ("b", "close")]


def test_snapshot_writes_life_size_png(index, monkeypatch, tmp_path):
    monkeypatch.setattr("mta_tracker.feeds.FeedPoller.poll", lambda self: [])
    out = tmp_path / "board.png"
    args = cli.parse_args(["--snapshot", str(out), "--panel", "128x32", "--pitch", "3"])
    panel = cli.panel_from_args(args)
    assert cli.snapshot(index, index.complex_for("127"), args, panel) == 0
    img = Image.open(out)
    assert img.size == (128 * 11, 32 * 11)  # 3 mm pitch -> 11 screen px per LED at 96 dpi
