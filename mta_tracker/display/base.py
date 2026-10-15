"""Renderer-agnostic board state. Terminal and (future) LED displays both consume this."""
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

    def by_direction(self, direction: str, limit: int) -> list[Arrival]:
        return [a for a in self.arrivals if a.direction == direction][:limit]


class Display(Protocol):
    def render(self, state: BoardState) -> None: ...

    def close(self) -> None: ...
