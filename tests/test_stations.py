"""Rotating the board through several stations."""
from mta_tracker import __main__ as cli
from mta_tracker import terminal as keys
from mta_tracker.arrivals import Arrival
from mta_tracker.display import BoardState
from mta_tracker.display.led import LedBoard
from mta_tracker.display.panel import PanelConfig

from test_paging import ClockTerminal, FakeClock
from test_picker import FakeTerminal, _ContextFor, type_text

NOW = 1_800_000_000


def test_rotation_order():
    # station 1: page 1 0-8, page 2 8-16; station 2: pages 16-32; then around again
    slot = lambda t: cli.rotation_slot(t, 2, 2, 8)[:2]
    assert [slot(t) for t in (0, 7.9, 8, 16, 24, 31.9, 32)] == [
        (0, 0), (0, 0), (0, 1), (1, 0), (1, 1), (1, 1), (0, 0)]
    assert cli.rotation_slot(9, 2, 2, 8).elapsed == 1
    # One station just alternates pages; without paging, stations take turns on their first page.
    assert [cli.rotation_slot(t, 1, 2, 8)[:2] for t in (0, 8, 16)] == [(0, 0), (0, 1), (0, 0)]
    assert [cli.rotation_slot(t, 2, 1, 8)[:2] for t in (0, 8, 16)] == [(0, 0), (1, 0), (0, 0)]


def test_run_loop_rotates_stations(index, monkeypatch):
    clock = FakeClock()
    monkeypatch.setattr(cli, "time", clock)
    monkeypatch.setattr(cli.config, "PAGES", 2)
    monkeypatch.setattr("mta_tracker.feeds.FeedPoller.poll", lambda self: [])
    shown = []

    class Recorder:
        animating = False

        def render(self, state):
            shown.append((round(state.now - 5000), state.station_name, state.page))

        def tick(self):
            pass

        def close(self):
            pass

    monkeypatch.setattr(cli, "build_board", lambda *a, **k: Recorder())
    stations = [index.complex_for("127"), index.complex_for("142")]
    args = cli.parse_args(["--page-seconds", "8"])
    cli.run(index, stations, args, ClockTerminal(clock, 45))
    at = {t: tuple(rest) for t, *rest in shown}
    first, second = stations[0].name, stations[1].name
    # two 8 s pages per station
    assert at[0] == (first, 0) and at[8] == (first, 1)
    assert at[16] == (second, 0) and at[24] == (second, 1) and at[32] == (first, 0)


def test_interactive_add_station(index, monkeypatch):
    """search -> board -> 'a' -> pick a second station -> board rotates both -> 'a', Esc -> board -> quit."""
    monkeypatch.setattr("mta_tracker.feeds.FeedPoller.poll", lambda self: [])
    term = FakeTerminal(type_text("times") + [keys.ENTER, None, "a"] + type_text("south") +
                        [keys.ENTER, None, "a", keys.ESC, None, "q"])
    boards = []
    real_run = cli.run
    monkeypatch.setattr(cli, "run", lambda index, stations, *a, **k: (
        boards.append([cx.name for cx in stations]), real_run(index, stations, *a, **k))[1])
    monkeypatch.setattr(cli.keys, "RawTerminal", lambda: _ContextFor(term))
    args = cli.parse_args(["--rows", "2", "--no-color", "--no-animation"])
    assert cli.interactive(index, args) == 0
    first, second = index.complex_for("127").name, index.complex_for("142").name
    assert boards == [[first], [first, second], [first, second]]
    assert "ADD A STATION" in "".join(term.output)


def test_also_flag_adds_stations_headless(index, monkeypatch):
    seen = []
    monkeypatch.setattr(cli, "load_index", lambda refresh=False: index)
    monkeypatch.setattr(cli, "run", lambda index, stations, *a, **k: seen.append([cx.id for cx in stations]))
    monkeypatch.setattr("sys.stdin.isatty", lambda: False)
    assert cli.main(["times sq", "--also", "south ferry", "--once"]) == 0
    assert seen == [["127", "142"]]


def test_led_page_dot_times_the_switch_to_the_next_station(index):
    clock = FakeClock()
    board = LedBoard(PanelConfig("64x64", 2), routes=index.routes, pulse=False, clock=clock.time)
    a_now = [Arrival("A", "S", "Far Rockaway", NOW + 30, "a", "A27"),
             Arrival("1", "N", "Van Cortlandt Park", NOW + 200, "b", "127")]
    blue = tuple(int(index.routes["A"].color[i:i + 2], 16) for i in (0, 2, 4))

    def rule():
        y = board.y0 + board._separators[0] * board.cell_h - 1
        return [board.image.getpixel((x, y)) for x in range(128)]

    # One page per station, but the next station is coming: the dot runs, in the soonest train's color.
    board.render(BoardState("X", a_now, NOW, updated_at=NOW, page_seconds=8, page_elapsed=4, rotating=True))
    assert board.animating and blue in rule()
    # A single station with one page never changes, so there's no dot.
    board.render(BoardState("X", a_now, NOW, updated_at=NOW, page_seconds=8, page_elapsed=4))
    assert blue not in rule()


def test_run_loop_times_station_switches_without_paging(index, monkeypatch):
    clock = FakeClock()
    monkeypatch.setattr(cli, "time", clock)
    monkeypatch.setattr(cli.config, "PAGES", 1)
    monkeypatch.setattr("mta_tracker.feeds.FeedPoller.poll", lambda self: [])
    shown = []

    class Recorder:
        animating = False

        def render(self, state):
            shown.append((round(state.now - 5000), state.station_name, state.page_seconds, state.rotating))

        def tick(self):
            pass

        def close(self):
            pass

    monkeypatch.setattr(cli, "build_board", lambda *a, **k: Recorder())
    stations = [index.complex_for("127"), index.complex_for("142")]
    cli.run(index, stations, cli.parse_args(["--page-seconds", "8"]), ClockTerminal(clock, 20))
    at = {t: tuple(rest) for t, *rest in shown}
    assert at[0] == (stations[0].name, 8, True) and at[8] == (stations[1].name, 8, True)
    assert at[16][0] == stations[0].name
    shown.clear()
    cli.run(index, stations[:1], cli.parse_args(["--page-seconds", "8"]), ClockTerminal(clock, 5))
    assert {(s, r) for _, _, s, r in shown} == {(0.0, False)}
