"""Minimal BDF bitmap-font reader for the LED panel renderer.

Glyphs are turned into Pillow masks once and cached, so drawing a frame is
just a paste per character.
"""
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from PIL import Image

FONT_DIR = Path(__file__).parent / "fonts"
FONTS = ("4x6", "5x7", "5x8", "6x10")


@dataclass(frozen=True)
class Glyph:
    width: int
    height: int
    x_offset: int
    y_offset: int     # bottom of the bitmap relative to the baseline (BDF convention)
    rows: tuple[int, ...]  # one int per row, bit (width-1) is the leftmost pixel


class BdfFont:
    """A fixed-width BDF font. Each character occupies a `width` x `height` cell."""

    def __init__(self, path: Path):
        self.name = path.stem
        self.glyphs: dict[str, Glyph] = {}
        self.width = self.height = self.ascent = 0
        self._parse(path.read_text(encoding="ascii").splitlines())
        self._masks: dict[str, Image.Image] = {}

    def _parse(self, lines: list[str]) -> None:
        i = 0
        while i < len(lines):
            parts = lines[i].split()
            if not parts:
                i += 1
                continue
            key = parts[0]
            if key == "FONTBOUNDINGBOX":
                self.width, self.height = int(parts[1]), int(parts[2])
            elif key == "FONT_ASCENT":
                self.ascent = int(parts[1])
            elif key == "STARTCHAR":
                encoding, bbx, rows = None, None, []
                i += 1
                while not lines[i].startswith("ENDCHAR"):
                    p = lines[i].split()
                    if p[0] == "ENCODING":
                        encoding = int(p[1])
                    elif p[0] == "BBX":
                        bbx = tuple(int(v) for v in p[1:5])
                    elif p[0] == "BITMAP":
                        i += 1
                        while not lines[i].startswith("ENDCHAR"):
                            hex_row = lines[i].strip()
                            # Rows are padded to whole bytes; keep only the leftmost `w` bits.
                            rows.append(int(hex_row, 16) >> (len(hex_row) * 4 - bbx[0]))
                            i += 1
                        break
                    i += 1
                if encoding is not None and bbx is not None:
                    w, h, xo, yo = bbx
                    self.glyphs[chr(encoding)] = Glyph(w, h, xo, yo, tuple(rows))
            i += 1

    def mask(self, ch: str) -> Image.Image:
        """An 'L' mask of size width x height with the glyph drawn at 255."""
        m = self._masks.get(ch)
        if m is None:
            m = Image.new("L", (self.width, self.height), 0)
            g = self.glyphs.get(ch) or self.glyphs.get("?")
            if g:
                px = m.load()
                top = self.ascent - (g.y_offset + g.height)
                for r, bits in enumerate(g.rows):
                    for c in range(g.width):
                        if bits >> (g.width - 1 - c) & 1:
                            x, y = g.x_offset + c, top + r
                            if 0 <= x < self.width and 0 <= y < self.height:
                                px[x, y] = 255
            self._masks[ch] = m
        return m


@lru_cache(maxsize=None)
def load_font(name: str) -> BdfFont:
    if name not in FONTS:
        raise ValueError(f"unknown font {name!r}; choose from {', '.join(FONTS)}")
    return BdfFont(FONT_DIR / f"{name}.bdf")
