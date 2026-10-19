import io

from mta_tracker import __main__ as cli
from mta_tracker.arrivals import Arrival
from mta_tracker.display import AsciiBoard, BoardState
from mta_tracker.display import styles as S
from mta_tracker.display.led import PAGE_TRAIL, LedBoard
from mta_tracker.display.panel import PanelConfig

NOW = 1_800_000_000


def trains(direction, n, prefix):
    return [Arrival("1", direction, f"{prefix}{i}", NOW + 60 * (i + 1), f"{prefix}{i}", "127") for i in range(n)]


# 6 northbound (two full pages of 3), 2 southbound (only one page)
ARRIVALS = trains("N", 6, "North ") + trains("S", 2, "South ")


def heads(state, direction, limit):
    return [a.headsign for a in state.by_direction(direction, limit)]


def test_pages_split_the_soonest_and_next_trains():
    first = BoardState("X", ARRIVALS, NOW, page=0, pages=2)
    second = BoardState("X", ARRIVALS, NOW, page=1, pages=2)
    assert heads(first, "N", 3) == ["North 0", "North 1", "North 2"]
    assert heads(second, "N", 3) == ["North 3", "North 4", "North 5"]
    # Southbound has no second page, so it keeps showing its first page.
    assert heads(second, "S", 3) == ["South 0", "South 1"]
    assert second.page_shown("S", 3) == 0 and second.page_count("S", 3) == 1
    assert second.page_count("N", 3) == 2


def test_partial_second_page():
    state = BoardState("X", trains("N", 4, "N"), NOW, page=1, pages=2)
    assert heads(state, "N", 3) == ["N3"]
    assert state.page_count("N", 3) == 2


def test_no_paging_by_default():
    state = BoardState("X", ARRIVALS, NOW)
    assert state.page_count("N", 3) == 1 and heads(state, "N", 3) == ["North 0", "North 1", "North 2"]


def test_terminal_shows_page_indicator_only_when_paging(index):
    board = AsciiBoard(index.routes, rows=3, color=False, clear=False, stream=io.StringIO())
    text = "\n".join(board.format(BoardState("X", ARRIVALS, NOW, updated_at=NOW, page=1, pages=2)))
    north_title = next(line for line in text.splitlines() if "NORTHBOUND" in line)
    south_title = next(line for line in text.splitlines() if "SOUTHBOUND" in line)
    assert north_title.rstrip("| ").endswith("2/2") and "/" not in south_title
    assert "North 3" in text and "North 0" not in text and "South 0" in text
    plain = "\n".join(board.format(BoardState("X", ARRIVALS, NOW, updated_at=NOW)))
    assert "1/2" not in plain


def test_led_panel_pages(index):
    board = LedBoard(PanelConfig("64x64", 2), routes=index.routes, pulse=False)
    lines = ["".join(c.char for c in row) for row in board.layout(
        BoardState("X", ARRIVALS, NOW, updated_at=NOW, page=1, pages=2))]
    assert any("North 3" in line for line in lines) and not any("North 0" in line for line in lines)


class FakeClock:
    def __init__(self):
        self.t = 5000.0

    def time(self):
        return self.t

    def sleep(self, seconds):
        self.t += seconds


class ClockTerminal:
    """Advances the fake clock on every key wait; presses q after `stop_after` seconds."""

    def __init__(self, clock, stop_after):
        self.clock, self.stop_at = clock, clock.t + stop_after
        self.stream = io.StringIO()

    def read_key(self, timeout=None):
        self.clock.t += timeout or 0
        return "q" if self.clock.t >= self.stop_at else None


def test_run_loop_alternates_pages(index, monkeypatch):
    clock = FakeClock()
    monkeypatch.setattr(cli, "time", clock)
    monkeypatch.setattr(cli.config, "PAGES", 2)
    monkeypatch.setattr("mta_tracker.feeds.FeedPoller.poll", lambda self: [])
    shown = []

    class Recorder:
        animating = False

        def render(self, state):
            shown.append((round(state.now - 5000), state.page, state.pages))

        def tick(self):
            pass

        def close(self):
            pass

    monkeypatch.setattr(cli, "build_board", lambda *a, **k: Recorder())
    args = cli.parse_args(["--page-seconds", "8"])
    assert cli.run(index, [index.complex_for("127")], args, ClockTerminal(clock, 20)) == "quit"
    pages = {t: p for t, p, _ in shown}
    assert pages[0] == 0 and pages[7] == 0 and pages[8] == 1 and pages[15] == 1 and pages[16] == 0
    assert all(n == 2 for _, _, n in shown)

    shown.clear()
    args = cli.parse_args(["--page-seconds", "0"])
    cli.run(index, [index.complex_for("127")], args, ClockTerminal(clock, 20))
    assert {p for _, p, _ in shown} == {0} and {n for _, _, n in shown} == {1}


RED = (0xD8, 0x22, 0x33)  # the 1 train's color from routes.txt


def rule_pixels(board):
    y = board.y0 + board._separators[0] * board.cell_h - 1
    return [board.image.getpixel((x, y)) for x in range(board.panel.width)]


def test_led_page_dot_crosses_the_rule_as_the_page_runs_down(index):
    clock = FakeClock()
    board = LedBoard(PanelConfig("64x64", 2), routes=index.routes, pulse=False, clock=clock.time)

    def dot_x():  # every test train is a 1 train, so the dot is the 1's red
        return [x for x, color in enumerate(rule_pixels(board)) if color == RED]

    board.render(BoardState("X", ARRIVALS, NOW, updated_at=NOW, pages=2, page_elapsed=0, page_seconds=8))
    assert board.animating and dot_x() == [board.x0]
    clock.t += 4
    board.tick()
    right = board.x0 + board.cols * board.cell_w - 1
    assert dot_x() == [round((board.x0 + right) / 2)]
    clock.t += 4
    board.tick()
    assert dot_x() == [right]

    # A trail fades out behind the dot, never ahead of it.
    y = board.y0 + board._separators[0] * board.cell_h - 1
    trail = [board.image.getpixel((right - i, y))[0] for i in range(PAGE_TRAIL + 1)]
    assert trail == sorted(trail, reverse=True) and trail[0] == RED[0] and 60 < trail[-1] < RED[0]

    # No dot when nothing would flip: paging off, or every direction fits on one page.
    board.render(BoardState("X", ARRIVALS, NOW, updated_at=NOW))
    assert not board.animating and dot_x() == []
    board.render(BoardState("X", ARRIVALS[:2], NOW, updated_at=NOW, pages=2, page_seconds=8))
    assert dot_x() == []


def test_led_page_dot_takes_the_soonest_trains_line_colors(index):
    clock = FakeClock()
    board = LedBoard(PanelConfig("64x64", 2), routes=index.routes, pulse=False, clock=clock.time)
    color = {r: tuple(int(index.routes[r].color[i:i + 2], 16) for i in (0, 2, 4)) for r in ("1", "A")}

    def arrivals(a_eta):
        return trains("N", 6, "North ") + [Arrival("A", "S", "Far Rockaway", NOW + a_eta, "a", "A27")]

    def head_and_trail():
        board.render(BoardState("X", arrivals(a_eta), NOW, updated_at=NOW, pages=2, page_seconds=8,
                                page_elapsed=4))
        x = round((board.x0 + board.x0 + board.cols * board.cell_w - 1) / 2)
        return rule_pixels(board)[x - PAGE_TRAIL:x + 1][::-1]  # dot first

    a_eta = 30  # the A is "Now", ahead of the 1 at 1m
    head = head_and_trail()
    assert head[0] == color["A"] and all(b > r for r, _, b in head[1:3])  # all blue
    a_eta = 90  # same minute as the 1: the trail alternates between both lines
    head = head_and_trail()
    assert head[0] == color["1"]
    assert head[1][2] > head[1][0] and head[2][0] > head[2][2]  # A blue, then 1 red


def test_led_numbers_trains_by_arrival_order_while_paging(index):
    board = LedBoard(PanelConfig("64x64", 2), routes=index.routes, pulse=False)

    def rows(page, pages=2):
        grid = board.layout(BoardState("X", ARRIVALS, NOW, updated_at=NOW, page=page, pages=pages))
        return [("".join(c.char for c in row), row[0].style) for row in grid]

    first, second = rows(0), rows(1)
    assert [line[:3] for line, _ in first[1:4]] == ["11 ", "21 ", "31 "]  # ordinal, then the 1's bullet
    assert [line[:2] for line, _ in second[1:4]] == ["41", "51", "61"]
    assert second[4][0].startswith("11 South 0")  # southbound has no page 2: still numbered from 1
    assert all(style == S.DIM for _, style in first[1:4])
    assert all(line.endswith("m") and len(line) == board.cols for line, _ in second[1:4])
    assert rows(0, pages=1)[1][0].startswith("1 North 0")  # not paging: no numbers
