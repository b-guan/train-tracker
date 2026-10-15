"""Interactive station search: type to fuzzy-search, arrow keys to choose, Enter to open."""
from __future__ import annotations

import shutil
from dataclasses import replace

from . import terminal as keys
from .display.ascii import route_badge
from .stops import Complex, StopIndex

_REVERSE, _BOLD, _DIM, _RESET = "\x1b[7m", "\x1b[1m", "\x1b[2m", "\x1b[0m"
_HINT = "Up/Down move  Enter select  Esc quit"


class StationPicker:
    """Search state plus rendering; key handling is pure so it can be tested without a terminal."""

    MAX_RESULTS = 50

    def __init__(self, index: StopIndex, query: str = "", color: bool = True):
        self.index = index
        self.color = color
        self.query = query
        self._all = sorted(index.complexes, key=lambda c: (c.name, c.id))
        self.results: list[Complex] = []
        self.selected = 0
        self.scroll = 0
        self._update()

    @property
    def current(self) -> Complex | None:
        return self.results[self.selected] if self.results else None

    def _update(self) -> None:
        q = self.query.strip()
        self.results = self.index.search(q, limit=self.MAX_RESULTS) if q else self._all
        self.selected = self.scroll = 0

    def move(self, delta: int) -> None:
        if self.results:
            self.selected = max(0, min(len(self.results) - 1, self.selected + delta))

    def handle_key(self, key: str | None, page: int = 10) -> tuple[str, Complex | None] | None:
        """Returns ("select", complex), ("cancel", None), or None to keep going."""
        if key in (keys.ESC, keys.CTRL_C):
            return ("cancel", None)
        if key == keys.ENTER:
            return ("select", self.current) if self.current else None
        if key == keys.UP:
            self.move(-1)
        elif key == keys.DOWN:
            self.move(1)
        elif key == keys.PGUP:
            self.move(-page)
        elif key == keys.PGDN:
            self.move(page)
        elif key == keys.HOME:
            self.move(-len(self.results))
        elif key == keys.END:
            self.move(len(self.results))
        elif key == keys.BACKSPACE:
            if self.query:
                self.query = self.query[:-1]
                self._update()
        elif key == keys.CTRL_U:
            self.query = ""
            self._update()
        elif key == keys.CTRL_W:
            trimmed = self.query.rstrip()
            self.query = trimmed[:trimmed.rfind(" ") + 1]
            self._update()
        elif key and len(key) == 1 and key.isprintable():
            self.query += key
            self._update()
        return None

    # -- rendering --------------------------------------------------------------

    def _style(self, text: str, style: str) -> str:
        return style + text + _RESET if self.color else text

    def _badges(self, cx: Complex, max_width: int) -> tuple[str, int]:
        """Route badges for a row and their visible width."""
        routes, seen = [], set()
        for rid in cx.routes:
            route = self.index.routes.get(rid)
            label = route.label if route else rid
            if label not in seen:
                seen.add(label)
                routes.append((rid, route, label))
        if self.color and 4 * len(routes) - 1 <= max_width:
            # Show express variants with the plain line badge (6X -> 6).
            badges = [route_badge(replace(r, express=False) if r else None, rid, True)
                      for rid, r, _ in routes]
            return " ".join(badges), 4 * len(routes) - 1
        plain = " ".join(label for _, _, label in routes)[:max_width]
        return plain, len(plain)

    def _row(self, cx: Complex, selected: bool, width: int) -> str:
        badges, badge_width = self._badges(cx, max(0, width - 24))
        name_width = max(10, width - badge_width - 5)
        name = self.index.complex_label(cx)
        if len(name) > name_width:
            name = name[:name_width - 3] + "..."
        name = name.ljust(name_width)
        marker = ">" if selected else " "
        if selected:
            name = self._style(name, _REVERSE)
        return f" {marker} {name} {badges}"

    def lines(self, width: int, height: int) -> list[str]:
        """The full screen: title, search box, scrolling result list and footer."""
        width = max(width, 30)
        list_height = max(3, height - 6)
        if self.selected < self.scroll:
            self.scroll = self.selected
        elif self.selected >= self.scroll + list_height:
            self.scroll = self.selected - list_height + 1

        rule = " " + "-" * (width - 2)
        cursor = self._style(" ", _REVERSE) if self.color else "_"
        out = [
            self._style(" MTA STATION SEARCH", _BOLD),
            f" Search: {self.query}{cursor}",
            rule,
        ]
        visible = self.results[self.scroll:self.scroll + list_height]
        for i, cx in enumerate(visible, self.scroll):
            out.append(self._row(cx, i == self.selected, width))
        if not self.results:
            out.append(self._style("   No matching stations", _DIM))
        out.extend("" for _ in range(list_height - max(1, len(visible))))
        out.append(rule)

        n = len(self.results)
        more = "+" if self.query.strip() and n >= self.MAX_RESULTS else ""
        count = f" {n}{more} station{'s' if n != 1 else ''}"
        footer = count + _HINT.rjust(width - len(count) - 1) if len(count) + len(_HINT) < width else count
        out.append(self._style(footer, _DIM))
        return out


def pick_station(index: StopIndex, term: keys.RawTerminal, query: str = "",
                 color: bool = True) -> tuple[Complex | None, str]:
    """Run the search screen until a station is chosen or the user quits.

    Returns the chosen complex (None if cancelled) and the final query text,
    so returning to the search later can pick up where it left off.
    """
    picker = StationPicker(index, query, color)
    while True:
        size = shutil.get_terminal_size()
        lines = picker.lines(size.columns - 1, size.lines)
        term.write("\x1b[H" + "\n".join(line + "\x1b[K" for line in lines) + "\x1b[J")
        result = picker.handle_key(term.read_key(timeout=0.5))  # timeout: redraw on resize
        if result:
            action, cx = result
            return (cx if action == "select" else None), picker.query
