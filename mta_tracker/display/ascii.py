"""Fixed-size ASCII arrival board for the terminal."""
from __future__ import annotations

import sys
import time
from typing import Mapping, TextIO

from ..stops import Route
from . import styles as S
from .base import BoardState
from .splitflap import Cell, Grid, SplitFlap, to_ansi
from .styles import PULSE_FLOOR, PULSE_PERIOD, pulse_level  # noqa: F401  (re-exported)

DIRECTION_TITLES = {"N": "NORTHBOUND", "S": "SOUTHBOUND"}

_RESET = "\x1b[0m"
_HOME, _CLEAR_SCREEN, _CLEAR_EOL, _CLEAR_BELOW = "\x1b[H", "\x1b[2J", "\x1b[K", "\x1b[J"
_HIDE_CURSOR, _SHOW_CURSOR = "\x1b[?25l", "\x1b[?25h"
_DIM = "\x1b[2m"
_ALERT = "\x1b[38;2;255;80;80m"


def _fg(rgb) -> str:
    return "\x1b[38;2;%d;%d;%dm" % tuple(rgb)


def _rgb(hex_color: str, background: bool) -> str:
    r, g, b = (int(hex_color[i:i + 2], 16) for i in (0, 2, 4))
    return f"\x1b[{48 if background else 38};2;{r};{g};{b}m"


_AMBER = _fg(S.AMBER_RGB)


def badge_text(route: Route | None, route_id: str, color: bool) -> str:
    """Three visible characters: (A) for local, <6> for express, SIR as-is."""
    label = route.label if route else route_id
    express = route.express if route else False
    if len(label) == 1:
        return f"<{label}>" if express else (f" {label} " if color else f"({label})")
    return label[:3].ljust(3)


def route_badge(route: Route | None, route_id: str = "", color: bool = True) -> str:
    """The badge as an ANSI string (used by the station picker)."""
    text = badge_text(route, route_id, color)
    if color and route:
        return _rgb(route.color, True) + _rgb(route.text_color, False) + text + _RESET
    return text


def format_eta(seconds: float) -> str:
    minutes = S.minutes_until(seconds)
    return "Now" if minutes == 0 else f"{minutes} min"


class AsciiBoard:
    """Renders a BoardState as a box of constant width and height.

    `layout()` produces a grid of semantically styled cells; drawing maps those
    styles to ANSI colors. Each direction always gets `rows` lines so the
    layout never jumps around.
    """

    ETA_WIDTH = 6

    def __init__(self, routes: Mapping[str, Route] | None = None, width: int = 46, rows: int = 4,
                 color: bool = True, clear: bool = True, stream: TextIO | None = None,
                 hint: str = "", animator: SplitFlap | None = None, pulse: bool = True,
                 clock=time.monotonic):
        self.routes = routes or {}
        # Split-flap transitions need in-place redraws, so they only apply when clearing.
        self.animator = animator if clear else None
        # "Now" fades in and out; needs color and in-place redraws.
        self.pulse = pulse and color and clear
        self.clock = clock
        self.hint = hint  # right-aligned on the status line, e.g. key bindings
        self.width = max(width, 30)
        self.rows = rows
        self.color = color
        self.clear = clear
        self.stream = stream or sys.stdout
        self._first_frame = True
        self._target: Grid = []
        self._has_now = False

    @property
    def inner(self) -> int:
        return self.width - 2

    # -- layout (semantic) -----------------------------------------------------

    def _boxed(self, content: list[Cell]) -> list[Cell]:
        content = content[:self.inner] + S.cells(" " * max(0, self.inner - len(content)))
        return [Cell("|", S.RULE)] + content + [Cell("|", S.RULE)]

    def _rule(self) -> list[Cell]:
        return S.cells("+" + "-" * self.inner + "+", S.RULE)

    def _arrival_row(self, arrival, now: float) -> list[Cell]:
        eta = format_eta(arrival.time - now)
        dest_width = self.inner - 3 - self.ETA_WIDTH - 4  # " XXX dest eta "
        badge = badge_text(self.routes.get(arrival.route_id), arrival.route_id, self.color)
        return self._boxed(
            S.cells(" ")
            + S.cells(badge, S.route_style(arrival.route_id))
            + S.cells(" " + arrival.headsign[:dest_width].ljust(dest_width) + " ")
            + S.cells(eta.rjust(self.ETA_WIDTH), S.NOW if eta == "Now" else S.ETA)
            + S.cells(" ")
        )

    def layout(self, state: BoardState) -> Grid:
        clock = time.strftime("%I:%M:%S %p", time.localtime(state.now))
        name_width = self.inner - len(clock) - 3
        header = f" {state.station_name.upper()[:name_width].ljust(name_width)} {clock} "

        grid = [self._rule(), self._boxed(S.cells(header, S.HEADER)), self._rule()]
        for direction in state.directions:
            title = " " + DIRECTION_TITLES.get(direction, direction)
            count = state.page_count(direction, self.rows)
            if count > 1:  # e.g. "1/2", right-aligned above the ETA column
                page = f"{state.page_shown(direction, self.rows) + 1}/{count} "
                title = title.ljust(self.inner - len(page)) + page
            grid.append(self._boxed(S.cells(title, S.DIM)))
            upcoming = state.by_direction(direction, self.rows)
            grid.extend(self._arrival_row(a, state.now) for a in upcoming)
            if not upcoming:
                msg = "   Loading..." if state.updated_at is None and not state.error else "   No trains scheduled"
                grid.append(self._boxed(S.cells(msg)))
            grid.extend(self._boxed([]) for _ in range(self.rows - max(1, len(upcoming))))
        grid.append(self._rule())

        if state.error:
            age = f" {int(state.now - state.updated_at)}s old" if state.updated_at else ""
            status, style = f" STALE{age}: {state.error}", S.ALERT
        elif state.updated_at:
            status = " Updated " + time.strftime("%I:%M:%S %p", time.localtime(state.updated_at))
            style = S.DIM
        else:
            status, style = " Fetching...", S.DIM
        status = status[:self.inner]
        if self.hint and len(status) + len(self.hint) + 2 <= self.inner:
            status = status.ljust(self.inner - len(self.hint) - 1)
            grid.append(self._boxed(S.cells(status, style) + S.cells(self.hint + " ", S.DIM)))
        else:
            grid.append(self._boxed(S.cells(status, style)))
        grid.append(self._rule())
        return grid

    # -- styles -> ANSI ----------------------------------------------------------

    def _ansi(self, style: str, now_color: str) -> str:
        if not self.color or not style:
            return ""
        route_id = S.route_of(style)
        if route_id is not None:
            route = self.routes.get(route_id)
            return _rgb(route.color, True) + _rgb(route.text_color, False) if route else ""
        return {S.DIM: _DIM, S.ETA: _AMBER, S.NOW: now_color, S.ALERT: _ALERT}.get(style, "")

    def _to_lines(self, grid: Grid) -> list[str]:
        now_color = _AMBER
        if self.pulsing:
            level = pulse_level(self.clock())
            now_color = _fg(round(v * level) for v in S.AMBER_RGB)
        cache: dict[str, str] = {}
        lines = []
        for row in grid:
            styled = []
            for cell in row:
                if cell.style not in cache:
                    cache[cell.style] = self._ansi(cell.style, now_color)
                styled.append(Cell(cell.char, cache[cell.style]))
            lines.append(to_ansi(styled))
        return lines

    def format(self, state: BoardState) -> list[str]:
        """The board as text lines (with ANSI colors when enabled)."""
        return self._to_lines(self.layout(state))

    # -- drawing -----------------------------------------------------------------

    @property
    def pulsing(self) -> bool:
        return self.pulse and self._has_now

    @property
    def animating(self) -> bool:
        """True while split-flaps are turning or a "Now" is fading; call tick() to advance."""
        return (self.animator is not None and self.animator.animating) or self.pulsing

    def render(self, state: BoardState) -> None:
        self._target = self.layout(state)
        self._has_now = any(c.style == S.NOW for row in self._target for c in row)
        if self.animator:
            self.animator.set_target(self._target)
        self._draw(self._current())

    def tick(self) -> None:
        """Draw the next animation frame (no-op when nothing is animating)."""
        if self.animating:
            self._draw(self._current())

    def _current(self) -> Grid:
        return self.animator.frame() if self.animator else self._target

    def _draw(self, grid: Grid) -> None:
        lines = self._to_lines(grid)
        if self.clear:
            prefix = (_CLEAR_SCREEN + _HIDE_CURSOR if self._first_frame else "") + _HOME
            out = prefix + "".join(line + _CLEAR_EOL + "\n" for line in lines) + _CLEAR_BELOW
        else:
            out = "\n".join(lines) + "\n"
        self._first_frame = False
        self.stream.write(out)
        self.stream.flush()

    def close(self) -> None:
        if self.clear and not self._first_frame:
            self.stream.write(_SHOW_CURSOR)
            self.stream.flush()
