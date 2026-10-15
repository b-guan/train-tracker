"""Fixed-size ASCII arrival board for the terminal, laid out like an LED panel."""
from __future__ import annotations

import sys
import time
from typing import Mapping, TextIO

from ..stops import Route
from .base import BoardState

DIRECTION_TITLES = {"N": "NORTHBOUND", "S": "SOUTHBOUND"}

_RESET = "\x1b[0m"
_HOME, _CLEAR_SCREEN, _CLEAR_EOL, _CLEAR_BELOW = "\x1b[H", "\x1b[2J", "\x1b[K", "\x1b[J"
_HIDE_CURSOR, _SHOW_CURSOR = "\x1b[?25l", "\x1b[?25h"
_DIM, _AMBER = "\x1b[2m", "\x1b[38;2;255;176;0m"


def _rgb(hex_color: str, background: bool) -> str:
    r, g, b = (int(hex_color[i:i + 2], 16) for i in (0, 2, 4))
    return f"\x1b[{48 if background else 38};2;{r};{g};{b}m"


def format_eta(seconds: float) -> str:
    minutes = max(0, int(seconds // 60))
    return "Now" if minutes == 0 else f"{minutes} min"


class AsciiBoard:
    """Renders a BoardState as a box of constant width and height.

    Each direction always gets `rows` lines so the layout never jumps around,
    which also mirrors what a fixed-size LED matrix can show.
    """

    ETA_WIDTH = 6

    def __init__(self, routes: Mapping[str, Route] | None = None, width: int = 46, rows: int = 4,
                 color: bool = True, clear: bool = True, stream: TextIO | None = None):
        self.routes = routes or {}
        self.width = max(width, 30)
        self.rows = rows
        self.color = color
        self.clear = clear
        self.stream = stream or sys.stdout
        self._first_frame = True

    # -- pieces ---------------------------------------------------------------

    @property
    def inner(self) -> int:
        return self.width - 2

    def _bullet(self, route_id: str) -> str:
        """Three visible characters: (A) for local, <6> for express, SIR as-is."""
        route = self.routes.get(route_id)
        label = route.label if route else route_id
        express = route.express if route else False
        if len(label) == 1:
            text = f"<{label}>" if express else (f" {label} " if self.color else f"({label})")
        else:
            text = label[:3].ljust(3)
        if self.color and route:
            return _rgb(route.color, True) + _rgb(route.text_color, False) + text + _RESET
        return text

    def _line(self, text: str, visible_len: int | None = None, style: str = "") -> str:
        visible_len = len(text) if visible_len is None else visible_len
        pad = " " * max(0, self.inner - visible_len)
        if style and self.color:
            text = style + text + _RESET
        return "|" + text + pad + "|"

    def _rule(self) -> str:
        return "+" + "-" * self.inner + "+"

    def _arrival_line(self, arrival, now: float) -> str:
        eta = format_eta(arrival.time - now).rjust(self.ETA_WIDTH)
        dest_width = self.inner - 3 - self.ETA_WIDTH - 4  # " XXX dest eta "
        dest = arrival.headsign[:dest_width].ljust(dest_width)
        text = f" {self._bullet(arrival.route_id)} {dest} "
        eta_text = (_AMBER + eta + _RESET) if self.color else eta
        return "|" + text + eta_text + " |"

    # -- whole frame ----------------------------------------------------------

    def format(self, state: BoardState) -> list[str]:
        clock = time.strftime("%I:%M:%S %p", time.localtime(state.now))
        name_width = self.inner - len(clock) - 3
        header = f" {state.station_name.upper()[:name_width].ljust(name_width)} {clock} "

        lines = [self._rule(), self._line(header), self._rule()]
        for direction in state.directions:
            lines.append(self._line(" " + DIRECTION_TITLES.get(direction, direction), style=_DIM))
            upcoming = state.by_direction(direction, self.rows)
            for arrival in upcoming:
                lines.append(self._arrival_line(arrival, state.now))
            if not upcoming:
                msg = "   Loading..." if state.updated_at is None and not state.error else "   No trains scheduled"
                lines.append(self._line(msg))
            lines.extend(self._line("") for _ in range(self.rows - max(1, len(upcoming))))
        lines.append(self._rule())

        if state.error:
            age = f" {int(state.now - state.updated_at)}s old" if state.updated_at else ""
            status = f" STALE{age}: {state.error}"
        elif state.updated_at:
            status = " Updated " + time.strftime("%I:%M:%S %p", time.localtime(state.updated_at))
        else:
            status = " Fetching..."
        lines.append(self._line(status[:self.inner], style=_DIM))
        lines.append(self._rule())
        return lines

    def render(self, state: BoardState) -> None:
        lines = self.format(state)
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
