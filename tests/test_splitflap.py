import io
import random

from mta_tracker.arrivals import Arrival
from mta_tracker.display import AsciiBoard, BoardState, SplitFlap
from mta_tracker.display.splitflap import Cell, flap_sequence, parse_ansi, to_ansi


class FakeClock:
    def __init__(self):
        self.t = 100.0

    def __call__(self):
        return self.t


def text(grid):
    return ["".join(c.char for c in row) for row in grid]


def grid_of(*lines):
    return [[Cell(ch) for ch in line] for line in lines]


def make_flap(clock):
    return SplitFlap(flip_time=0.04, max_flips=10, stagger=0.01, jitter=0.02, clock=clock,
                     rng=random.Random(0))


def test_flap_sequence_walks_forward_through_the_drum():
    assert flap_sequence("A", "D") == ["A", "B", "C", "D"]
    assert flap_sequence("3", "3") == ["3"]
    seq = flap_sequence(" ", "T", max_flips=5)  # long trip is shortened
    assert seq == [" ", "O", "P", "Q", "R", "S", "T"]
    assert flap_sequence("x", "|") == ["x", "|"]  # characters not on the drum just swap


def test_intro_flaps_letters_in_but_shows_borders_immediately():
    clock = FakeClock()
    flap = make_flap(clock)
    flap.set_target(grid_of("+--+", "|AB|"))
    first = text(flap.frame())
    assert first == ["+--+", "|  |"]
    assert flap.animating
    clock.t += 5
    assert text(flap.frame()) == ["+--+", "|AB|"] and not flap.animating


def test_only_changed_cells_flap_and_pass_through_intermediate_letters():
    clock = FakeClock()
    flap = make_flap(clock)
    flap.set_target(grid_of("3 min"))
    clock.t += 5
    flap.frame()
    flap.set_target(grid_of("5 min"))
    seen = set()
    for _ in range(40):
        clock.t += 0.01
        row = text(flap.frame())[0]
        assert row.endswith(" min")  # unchanged cells never move
        seen.add(row[0])
    assert {"3", "4", "5"} <= seen
    assert not flap.animating


def test_retarget_mid_animation_converges_on_latest_text():
    clock = FakeClock()
    flap = make_flap(clock)
    flap.set_target(grid_of("AAAA"))
    clock.t += 0.1
    flap.set_target(grid_of("ZZZZ"))
    clock.t += 5
    assert text(flap.frame()) == ["ZZZZ"]


def test_ansi_round_trip_keeps_styles():
    line = "| \x1b[48;2;1;2;3m\x1b[38;2;0;0;0m A \x1b[0m Astoria \x1b[2m1 min\x1b[0m |"
    cells = parse_ansi(line)
    assert "".join(c.char for c in cells) == "|  A  Astoria 1 min |"
    assert cells[3].style == "\x1b[48;2;1;2;3m\x1b[38;2;0;0;0m" and cells[0].style == ""
    assert to_ansi(cells) == line


def test_board_animates_to_final_text():
    clock = FakeClock()
    out = io.StringIO()
    board = AsciiBoard(width=40, rows=1, color=True, clear=True, stream=out, animator=make_flap(clock))
    now = 1_800_000_000
    state = BoardState("Times Sq-42 St", [Arrival("1", "N", "Van Cortlandt", now + 180, "t", "127")],
                       now, updated_at=now)
    board.render(state)
    assert board.animating and "VAN CORTLANDT" not in out.getvalue().upper().replace("\x1b", "")
    while board.animating:
        clock.t += 1 / 30
        board.tick()
    last_frame = out.getvalue().rsplit("\x1b[H", 1)[-1]
    assert "TIMES SQ-42 ST" in last_frame and "Van Cortlandt" in last_frame and "3 min" in last_frame


def test_board_without_clear_never_animates():
    board = AsciiBoard(clear=False, stream=io.StringIO(), animator=SplitFlap())
    assert board.animator is None and not board.animating


def _now_board(clock, **kw):
    board = AsciiBoard(width=40, rows=1, color=True, clear=True, stream=io.StringIO(), clock=clock, **kw)
    now = 1_800_000_000
    arrivals = [Arrival("1", "N", "Van Cortlandt", now + 20, "a", "127"),
                Arrival("2", "S", "Flatbush Av", now + 300, "b", "127")]
    board.render(BoardState("Times Sq", arrivals, now, updated_at=now))
    return board


def _styles_of(board, word):
    """Styles of the cells spelling `word` in the most recent frame."""
    frame = board.stream.getvalue().rsplit("\x1b[H", 1)[-1]
    for line in frame.split("\n"):
        cells = parse_ansi(line)
        chars = "".join(c.char for c in cells)
        if word in chars:
            i = chars.index(word)
            return {c.style for c in cells[i:i + len(word)]}
    raise AssertionError(f"{word!r} not on board")


def test_pulse_level_cycles_between_floor_and_full():
    from mta_tracker.display.ascii import PULSE_FLOOR, PULSE_PERIOD, pulse_level
    assert pulse_level(0) == 1.0
    assert abs(pulse_level(PULSE_PERIOD / 2) - PULSE_FLOOR) < 1e-9
    assert pulse_level(PULSE_PERIOD) == 1.0


def test_now_fades_while_other_etas_stay_steady():
    clock = FakeClock()
    clock.t = 0.0
    board = _now_board(clock)
    assert board.pulsing and board.animating
    bright, steady = _styles_of(board, "Now"), _styles_of(board, "5 min")
    assert bright == {"\x1b[38;2;255;176;0m"}
    clock.t = 0.8  # half a period: dimmest point
    board.tick()
    dim = _styles_of(board, "Now")
    assert dim != bright and dim == {"\x1b[38;2;31;21;0m"}
    assert _styles_of(board, "5 min") == steady


def test_no_pulse_without_color_or_when_disabled():
    assert not _now_board(FakeClock(), pulse=False).animating
    plain = AsciiBoard(color=False, clear=True, stream=io.StringIO())
    assert not plain.pulse
