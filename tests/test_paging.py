import io

from mta_tracker import __main__ as cli
from mta_tracker.arrivals import Arrival
from mta_tracker.display import AsciiBoard, BoardState
from mta_tracker.display.led import LedBoard
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
    assert cli.run(index, index.complex_for("127"), args, ClockTerminal(clock, 20)) == "quit"
    pages = {t: p for t, p, _ in shown}
    assert pages[0] == 0 and pages[7] == 0 and pages[8] == 1 and pages[15] == 1 and pages[16] == 0
    assert all(n == 2 for _, _, n in shown)

    shown.clear()
    args = cli.parse_args(["--page-seconds", "0"])
    cli.run(index, index.complex_for("127"), args, ClockTerminal(clock, 20))
    assert {p for _, p, _ in shown} == {0} and {n for _, _, n in shown} == {1}
