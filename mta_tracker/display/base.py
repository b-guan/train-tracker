"""Renderer-agnostic board state. Terminal and LED displays both consume this."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, Sequence

from ..arrivals import Arrival


@dataclass
class BoardState:
    station_name: str
    arrivals: Sequence[Arrival]
    now: float
    updated_at: float | None = None   # when the arrivals were last fetched successfully
    error: str | None = None          # most recent fetch error, if the data is stale
    directions: tuple[str, ...] = field(default=("N", "S"))
    page: int = 0                     # which page of trains to show (0 = the soonest)
    pages: int = 1                    # how many pages are being cycled through
    page_elapsed: float = 0.0         # seconds the current page has been up
    page_seconds: float = 0.0         # how long each page stays up (0 = not paging)

    def _trains(self, direction: str) -> list[Arrival]:
        return [a for a in self.arrivals if a.direction == direction]

    def page_shown(self, direction: str, limit: int) -> int:
        """The page actually shown for `direction`: a direction without enough
        trains to fill the requested page keeps showing its first page."""
        return self.page if self.page * limit < len(self._trains(direction)) else 0

    def page_count(self, direction: str, limit: int) -> int:
        """How many of the cycled pages `direction` has trains for (at least 1)."""
        n = len(self._trains(direction))
        return max(1, min(self.pages, -(-n // limit)))

    def by_direction(self, direction: str, limit: int) -> list[Arrival]:
        start = self.page_shown(direction, limit) * limit
        return self._trains(direction)[start:start + limit]


class Display(Protocol):
    @property
    def animating(self) -> bool: ...

    def render(self, state: BoardState) -> None: ...

    def tick(self) -> None: ...

    def close(self) -> None: ...


class MultiDisplay:
    """Mirrors the board to several displays, e.g. the terminal and an LED panel."""

    def __init__(self, displays: Sequence[Display]):
        self.displays = list(displays)

    @property
    def animating(self) -> bool:
        return any(d.animating for d in self.displays)

    def render(self, state: BoardState) -> None:
        for d in self.displays:
            d.render(state)

    def tick(self) -> None:
        for d in self.displays:
            d.tick()

    def close(self) -> None:
        for d in self.displays:
            d.close()
