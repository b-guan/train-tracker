"""Split-flap (Solari board) animation for a grid of character cells.

Renderer-agnostic: it animates `Cell` grids, so the terminal board and a future
LED display can share it. Every cell that changes rotates forward through the
flap drum, one flap at a time, until it lands on its new character. Animation
is driven by wall-clock time, so frames can be drawn at any rate.
"""
from __future__ import annotations

import random
import re
import time
from typing import Callable, NamedTuple

# Order of the flaps on each drum. A cell flips forward (wrapping) toward its target.
DRUM = " ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789.,-:/'()&+<>!?"
_DRUM_POS = {ch: i for i, ch in enumerate(DRUM)}


class Cell(NamedTuple):
    char: str
    style: str = ""  # ANSI SGR prefix (or any renderer-specific style key)


Grid = list[list[Cell]]


def flap_sequence(start: str, target: str, max_flips: int = 10) -> list[str]:
    """Characters a flap shows going from `start` to `target`, inclusive of both ends.

    Long trips around the drum are shortened to the last `max_flips` flaps, the
    way a real board looks once it has spun up.
    """
    if start == target:
        return [target]
    if target not in _DRUM_POS:
        return [start, target]
    j = _DRUM_POS[target]
    distance = (j - _DRUM_POS[start]) % len(DRUM) if start in _DRUM_POS else max_flips
    distance = min(distance, max_flips)
    steps = [DRUM[(j - d) % len(DRUM)] for d in range(distance, -1, -1)]
    return steps if steps[0] == start else [start] + steps


class SplitFlap:
    """Tracks what each cell shows and animates it toward the latest target grid.

    flip_time: seconds per flap.
    stagger:   extra delay per column after the first changed cell in a row, so
               a whole changed row ripples left to right.
    jitter:    random per-cell delay (seconds) so flaps don't move in lockstep.
    """

    def __init__(self, flip_time: float = 0.04, max_flips: int = 10, stagger: float = 0.008,
                 jitter: float = 0.05, clock: Callable[[], float] = time.monotonic,
                 rng: random.Random | None = None):
        self.flip_time = flip_time
        self.max_flips = max_flips
        self.stagger = stagger
        self.jitter = jitter
        self.clock = clock
        self.rng = rng or random.Random()
        self._target: Grid | None = None
        self._anims: dict[tuple[int, int], tuple[list[str], float]] = {}

    @property
    def animating(self) -> bool:
        return bool(self._anims)

    def set_target(self, grid: Grid) -> None:
        now = self.clock()
        if self._target is None:
            # Intro: punctuation and borders appear at once, letters and digits flap in.
            shown = [[Cell(" " if c.char.isalnum() else c.char, c.style) for c in row] for row in grid]
        else:
            shown = self.frame(now)
        self._anims = {}
        for r, row in enumerate(grid):
            old_row = shown[r] if r < len(shown) else []
            first_change = None
            for c, cell in enumerate(row):
                old = old_row[c].char if c < len(old_row) else " "
                if old == cell.char:
                    continue
                if first_change is None:
                    first_change = c
                delay = (c - first_change) * self.stagger + self.rng.uniform(0, self.jitter)
                self._anims[(r, c)] = (flap_sequence(old, cell.char, self.max_flips), now + delay)
        self._target = [list(row) for row in grid]

    def frame(self, now: float | None = None) -> Grid:
        """The grid as it looks at `now`; finished animations are dropped."""
        if self._target is None:
            return []
        now = self.clock() if now is None else now
        grid = [list(row) for row in self._target]
        for (r, c), (seq, start) in list(self._anims.items()):
            step = int((now - start) / self.flip_time) if now >= start else 0
            if step >= len(seq) - 1:
                del self._anims[(r, c)]
                continue
            grid[r][c] = Cell(seq[step], grid[r][c].style)
        return grid


# --- ANSI <-> cells (terminal renderer) ----------------------------------------

_SGR = re.compile(r"\x1b\[[0-9;]*m")
_RESET = "\x1b[0m"


def parse_ansi(line: str) -> list[Cell]:
    """Split a line containing SGR color codes into styled cells."""
    cells, style, pos = [], "", 0
    for m in _SGR.finditer(line):
        cells.extend(Cell(ch, style) for ch in line[pos:m.start()])
        style = "" if m.group() == _RESET else style + m.group()
        pos = m.end()
    cells.extend(Cell(ch, style) for ch in line[pos:])
    return cells


def to_ansi(row: list[Cell]) -> str:
    out, style = [], ""
    for cell in row:
        if cell.style != style:
            out.append(_RESET + cell.style if style else cell.style)
            style = cell.style
        out.append(cell.char)
    if style:
        out.append(_RESET)
    return "".join(out)
