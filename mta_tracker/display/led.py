"""LED matrix panel board: a compact countdown-clock layout rendered to pixels.

The layout is a grid of semantic cells sized from the panel resolution and a
bitmap font (one cell = one character). It goes through the same SplitFlap
animator as the terminal, then is rasterized into a Pillow image that an
output (real panel, emulator, PNG) displays.

    128x64, 5x7 font -> 25 columns x 8 rows
    +-------------------------+
    |Times Sq-42 St       1:24|
    |1 Van Cortlandt Park  2m|   1 = filled circle (2 cells) in the line's color; while
    |2 Wakefield-241 St    3m|   paging, a dim arrival number (1-3, 4-6) leads each row.
    |N Astoria-Ditmars     5m|   express trains get a diamond
    |- - - - - -o- - - - - - -|   dim dotted rule between directions; while paging, a
    |Q Coney Island       Now|   white dot (o) crosses it in time with the page flip
    |1 South Ferry         9m|   "Now" fades in and out
    |A Far Rockaway       12m|
    +-------------------------+
"""
from __future__ import annotations

import re
import time
from typing import Mapping, Protocol

from PIL import Image, ImageDraw

from ..stops import Route
from . import styles as S
from .base import BoardState
from .fonts import BdfFont, load_font
from .panel import PanelConfig
from .splitflap import Cell, Grid, SplitFlap

# Panel palette. LEDs are very bright, so "white" is a soft white.
COLORS = {
    S.TEXT: (200, 200, 200),
    S.HEADER: (255, 255, 255),
    S.DIM: (90, 90, 90),
    S.ETA: S.AMBER_RGB,
    S.ALERT: (255, 50, 40),
    S.RULE: (60, 60, 60),
}
BACKGROUND = (0, 0, 0)
PAGE_DOT = (255, 255, 255)  # page dot color when no train's line color is known
PAGE_TRAIL = 8              # pixels of fading trail behind the dot

ETA_WIDTH = 3      # "Now", "9m", "12m"
BULLET_CELLS = 2   # a route bullet spans two character cells

_ABBREV = [(r"\bPark\b", "Pk"), (r"\bStreet\b", "St"), (r"\bAvenue\b", "Av"),
           (r"\bBoulevard\b", "Blvd"), (r"\bCenter\b", "Ctr"), (r"\bHeights\b", "Hts"),
           (r"\bParkway\b", "Pkwy"), (r"\bSquare\b", "Sq"), (r"\bJunction\b", "Jct")]


def short_headsign(name: str, width: int) -> str:
    """Fit a destination name into `width` characters the way countdown clocks do.

    "Coney Island-Stillwell Av" -> "Coney Island"; "34 St-Hudson Yards" -> "Hudson Yards".
    """
    if len(name) <= width:
        return name
    if "-" in name:
        first, rest = name.split("-", 1)
        name = rest if first[:1].isdigit() else first
    for pattern, repl in _ABBREV:
        if len(name) <= width:
            break
        name = re.sub(pattern, repl, name)
    return name[:width].rstrip(" -/")


def format_led_eta(seconds: float) -> str:
    minutes = S.minutes_until(seconds)
    return "Now" if minutes == 0 else f"{min(minutes, 99)}m"


class FrameOutput(Protocol):
    def show(self, image: Image.Image) -> None: ...

    def close(self) -> None: ...


class LedBoard:
    """A Display that renders to an LED panel (or anything accepting Pillow images)."""

    def __init__(self, panel: PanelConfig, output: FrameOutput | None = None,
                 routes: Mapping[str, Route] | None = None, font: str | None = None,
                 animator: SplitFlap | None = None, pulse: bool = True, clock=time.monotonic):
        self.panel = panel
        self.output = output
        self.routes = routes or {}
        self.font: BdfFont = load_font(font or panel.default_font())
        # Bullet letters use the smallest font so a ring of line color shows around them.
        self.bullet_font: BdfFont = load_font("4x6")
        self.animator = animator
        self.pulse = pulse
        self.clock = clock
        self.cell_w = self.font.width
        self.cell_h = self.font.height + 1  # one blank pixel row between lines
        self.cols = panel.width // self.cell_w
        self.rows = panel.height // self.cell_h
        # Center the text grid on the panel.
        self.x0 = (panel.width - self.cols * self.cell_w) // 2
        self.y0 = (panel.height - self.rows * self.cell_h) // 2
        self._target: Grid = []
        self._separators: list[int] = []  # grid rows that start a new direction group
        self._has_now = False
        self._page_seconds = 0.0  # > 0 while some direction has another page to flip to
        self._page_anchor = 0.0   # clock() reading when the current page went up
        self._page_colors: list[tuple[int, int, int]] = [PAGE_DOT]  # cycled along the dot's trail
        self.image = Image.new("RGB", (panel.width, panel.height), BACKGROUND)

    # -- layout (semantic) -----------------------------------------------------

    @property
    def show_header(self) -> bool:
        return self.rows >= 5

    def _row(self, *parts: list[Cell]) -> list[Cell]:
        row = [c for part in parts for c in part][:self.cols]
        return row + S.cells(" " * (self.cols - len(row)))

    def _arrival_row(self, arrival, now: float, ordinal: str = "") -> list[Cell]:
        route = self.routes.get(arrival.route_id)
        label = (route.label if route else arrival.route_id)[:1]
        bullet = [Cell(label, S.route_style(arrival.route_id))] + \
            S.cells(" " * (BULLET_CELLS - 1), S.route_style(arrival.route_id))
        eta = format_led_eta(arrival.time - now)
        dest_width = self.cols - len(ordinal) - BULLET_CELLS - 1 - ETA_WIDTH
        dest = short_headsign(arrival.headsign, dest_width).ljust(dest_width)
        return self._row(S.cells(ordinal, S.DIM), bullet, S.cells(dest + " "),
                         S.cells(eta.rjust(ETA_WIDTH), S.NOW if eta == "Now" else S.ETA))

    def layout(self, state: BoardState) -> Grid:
        grid: Grid = []
        if self.show_header:
            clock = time.strftime("%I:%M", time.localtime(state.now)).lstrip("0")
            name_width = self.cols - len(clock) - 1
            grid.append(self._row(S.cells(state.station_name[:name_width].ljust(name_width) + " ", S.HEADER),
                                  S.cells(clock, S.ALERT if state.error else S.HEADER)))
        groups = len(state.directions)
        per_group = max(1, (self.rows - len(grid)) // max(1, groups))
        self._separators = []
        flips = any(state.page_count(d, per_group) > 1 for d in state.directions)
        self._page_seconds = state.page_seconds if flips else 0.0
        self._page_colors = self._soonest_colors(
            [a for d in state.directions for a in state.by_direction(d, per_group)], state.now)
        # While paging, number trains in arrival order (1-3, then 4-6) so each page is identifiable.
        ordinal_width = len(str(state.pages * per_group)) if state.pages > 1 else 0
        for i, direction in enumerate(state.directions):
            if len(grid) >= self.rows:
                break
            if i > 0:
                self._separators.append(len(grid))
            upcoming = state.by_direction(direction, per_group)
            first = state.page_shown(direction, per_group) * per_group + 1
            group = [self._arrival_row(a, state.now, str(first + n).rjust(ordinal_width) if ordinal_width else "")
                     for n, a in enumerate(upcoming)]
            if not group:
                text = "Loading..." if state.updated_at is None and not state.error else "No trains"
                group = [self._row(S.cells(" " * (ordinal_width + BULLET_CELLS) + text, S.DIM))]
            group += [self._row([]) for _ in range(per_group - len(group))]
            grid.extend(group[:self.rows - len(grid)])
        grid += [self._row([]) for _ in range(self.rows - len(grid))]
        return grid

    def _soonest_colors(self, shown, now: float) -> list[tuple[int, int, int]]:
        """Line colors of the shown trains tied for the soonest ETA on the board."""
        if not shown:
            return [PAGE_DOT]
        soonest = min(S.minutes_until(a.time - now) for a in shown)  # ties as the board shows them
        colors = []
        for a in shown:
            route = self.routes.get(a.route_id)
            color = self._hex(route.color) if route else PAGE_DOT
            if S.minutes_until(a.time - now) == soonest and color not in colors:
                colors.append(color)
        return colors

    # -- rasterizing -------------------------------------------------------------

    def _now_color(self) -> tuple[int, int, int]:
        level = S.pulse_level(self.clock()) if self.pulse else 1.0
        return tuple(round(v * level) for v in S.AMBER_RGB)

    @staticmethod
    def _hex(color: str) -> tuple[int, int, int]:
        return tuple(int(color[i:i + 2], 16) for i in (0, 2, 4))

    def _draw_bullet(self, draw: ImageDraw.ImageDraw, x: int, y: int, cell: Cell) -> None:
        route = self.routes.get(S.route_of(cell.style))
        fill = self._hex(route.color) if route else COLORS[S.DIM]
        ink = self._hex(route.text_color) if route else BACKGROUND
        d = self.cell_h - 1  # leave the blank pixel row so stacked bullets don't touch
        if d < 7:  # too small for a letter inside a circle: draw the letter in the line color
            self.image.paste(fill, (x, y, x + self.font.width, y + self.font.height), self.font.mask(cell.char))
            return
        cx0 = x + (BULLET_CELLS * self.cell_w - 1 - d) // 2
        if route and route.express:  # express trains get a diamond, like the real signage
            c = (d - 1) / 2
            draw.polygon([(cx0 + c, y), (cx0 + d - 1, y + c), (cx0 + c, y + d - 1), (cx0, y + c)], fill=fill)
        else:
            draw.ellipse([cx0, y, cx0 + d - 1, y + d - 1], fill=fill)
        font = self.bullet_font
        mask = font.mask(cell.char)
        ink_box = mask.getbbox()
        if ink_box:  # center the glyph's actual pixels inside the bullet
            left, top, right, bottom = ink_box
            gx = cx0 + (d - (right - left)) // 2 - left
            gy = y + (d - (bottom - top)) // 2 - top
            self.image.paste(ink, (gx, gy, gx + font.width, gy + font.height), mask)

    def rasterize(self, grid: Grid) -> Image.Image:
        img = self.image
        img.paste(BACKGROUND, (0, 0, img.width, img.height))
        draw = ImageDraw.Draw(img)
        now_color = self._now_color()
        for r, row in enumerate(grid):
            y = self.y0 + r * self.cell_h
            c = 0
            while c < len(row):
                cell = row[c]
                x = self.x0 + c * self.cell_w
                if S.route_of(cell.style) is not None:
                    self._draw_bullet(draw, x, y, cell)
                    c += BULLET_CELLS
                    continue
                if cell.char != " ":
                    color = now_color if cell.style == S.NOW else COLORS.get(cell.style, COLORS[S.TEXT])
                    img.paste(color, (x, y, x + self.font.width, y + self.font.height),
                              self.font.mask(cell.char))
                c += 1
        for r in self._separators:  # dotted rule in the blank pixel row above the group
            y = self.y0 + r * self.cell_h - 1
            for x in range(self.x0, self.x0 + self.cols * self.cell_w, 2):
                img.putpixel((x, y), COLORS[S.RULE])
        if self.paging and self._separators:
            self._draw_page_dot(img, self.y0 + self._separators[0] * self.cell_h - 1)
        return img

    def _draw_page_dot(self, img: Image.Image, y: int) -> None:
        """The dot plus a trail that fades linearly into the rule behind it, in the
        soonest train's line color (cycling through each line when trains tie)."""
        x = self._page_dot_x()
        rule = COLORS[S.RULE]
        colors = self._page_colors
        for i in range(min(PAGE_TRAIL, x - self.x0) + 1):
            level = 1 - i / (PAGE_TRAIL + 1)
            dot = colors[i % len(colors)]
            img.putpixel((x - i, y), tuple(round(r + (d - r) * level) for r, d in zip(rule, dot)))

    def _page_dot_x(self) -> int:
        """Left edge when a page goes up, right edge when it's about to flip."""
        progress = min(1.0, max(0.0, (self.clock() - self._page_anchor) / self._page_seconds))
        span = self.cols * self.cell_w - 1
        return self.x0 + round(progress * span)

    # -- Display interface ---------------------------------------------------------

    @property
    def pulsing(self) -> bool:
        return self.pulse and self._has_now

    @property
    def paging(self) -> bool:
        return self._page_seconds > 0

    @property
    def animating(self) -> bool:
        return (self.animator is not None and self.animator.animating) or self.pulsing or self.paging

    def _current(self) -> Grid:
        return self.animator.frame() if self.animator else self._target

    def render(self, state: BoardState) -> None:
        self._target = self.layout(state)
        self._page_anchor = self.clock() - state.page_elapsed
        self._has_now = any(c.style == S.NOW for row in self._target for c in row)
        if self.animator:
            self.animator.set_target(self._target)
        self._show()

    def tick(self) -> None:
        if self.animating:
            self._show()

    def _show(self) -> None:
        image = self.rasterize(self._current())
        if self.output:
            self.output.show(image)

    def close(self) -> None:
        """The output outlives one station's board (the caller owns it), so leave it open."""
