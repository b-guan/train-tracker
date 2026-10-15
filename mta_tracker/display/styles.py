"""Semantic cell styles shared by every renderer.

Layouts tag each `Cell` with a role (what the text *is*), not a color. Each
renderer maps roles to its own colors: ANSI codes in the terminal, RGB on the
LED panel. The split-flap animator just carries the role along.
"""
from __future__ import annotations

import math

from .splitflap import Cell

TEXT = ""          # ordinary text
HEADER = "header"  # station name / clock
DIM = "dim"        # direction titles, status line, placeholders
ETA = "eta"        # minutes until arrival
NOW = "now"        # an arrival that is due now: fades in and out
ALERT = "alert"    # stale data / errors
RULE = "rule"      # separators and borders
_ROUTE = "route:"  # route bullet, e.g. "route:A"

AMBER_RGB = (255, 176, 0)

PULSE_PERIOD = 1.6  # seconds for one fade out-and-in of "Now"
PULSE_FLOOR = 0.12  # dimmest point, as a fraction of full brightness


def route_style(route_id: str) -> str:
    return _ROUTE + route_id


def route_of(style: str) -> str | None:
    return style[len(_ROUTE):] if style.startswith(_ROUTE) else None


def cells(text: str, style: str = TEXT) -> list[Cell]:
    return [Cell(ch, style) for ch in text]


def pulse_level(t: float, period: float = PULSE_PERIOD, floor: float = PULSE_FLOOR) -> float:
    """Brightness in [floor, 1] following a smooth (cosine) fade cycle; full at t=0."""
    return floor + (1 - floor) * (0.5 + 0.5 * math.cos(2 * math.pi * t / period))


def minutes_until(seconds: float) -> int:
    return max(0, int(seconds // 60))
