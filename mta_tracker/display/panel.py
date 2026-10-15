"""HUB75 LED panel geometry: standard module sizes, chaining, pitch and physical size."""
from __future__ import annotations

from dataclasses import dataclass

# Common HUB75 module resolutions (width x height in LEDs).
STANDARD_MODULES: dict[str, tuple[int, int]] = {
    "32x16": (32, 16),
    "32x32": (32, 32),
    "64x32": (64, 32),
    "64x64": (64, 64),
    "128x64": (128, 64),
}

# Common LED pitches (mm between LED centers): P1.5 ... P10.
STANDARD_PITCHES: tuple[float, ...] = (1.5, 1.86, 2.0, 2.5, 3.0, 4.0, 5.0, 6.0, 8.0, 10.0)

MM_PER_INCH = 25.4


@dataclass(frozen=True)
class PanelConfig:
    """A display built from identical modules: `chain` side by side, `parallel` stacked.

    This mirrors rpi-rgb-led-matrix's options (--led-cols, --led-rows,
    --led-chain, --led-parallel). Note the Adafruit Bonnet/HAT drive a single
    chain, so parallel > 1 needs a board with multiple outputs.
    """

    module: str = "64x64"
    chain: int = 2
    parallel: int = 1
    pitch_mm: float = 2.5

    def __post_init__(self):
        if self.module not in STANDARD_MODULES:
            raise ValueError(f"unknown module {self.module!r}; standard sizes: {', '.join(STANDARD_MODULES)}")
        if self.chain < 1 or self.parallel < 1:
            raise ValueError("chain and parallel must be >= 1")
        if self.pitch_mm <= 0:
            raise ValueError("pitch must be positive")

    @property
    def module_cols(self) -> int:
        return STANDARD_MODULES[self.module][0]

    @property
    def module_rows(self) -> int:
        return STANDARD_MODULES[self.module][1]

    @property
    def width(self) -> int:
        return self.module_cols * self.chain

    @property
    def height(self) -> int:
        return self.module_rows * self.parallel

    @property
    def size_mm(self) -> tuple[float, float]:
        return self.width * self.pitch_mm, self.height * self.pitch_mm

    @property
    def size_in(self) -> tuple[float, float]:
        w, h = self.size_mm
        return w / MM_PER_INCH, h / MM_PER_INCH

    @property
    def modules(self) -> int:
        return self.chain * self.parallel

    def default_font(self) -> str:
        """5x7 reads best; drop to 4x6 when the panel is too narrow for useful text."""
        return "5x7" if self.width >= 128 else "4x6"

    def describe(self) -> str:
        (wmm, hmm), (win, hin) = self.size_mm, self.size_in
        layout = f"{self.chain}x{self.parallel}" if self.parallel > 1 else str(self.chain)
        return (f"{self.width}x{self.height} px ({layout}x {self.module} modules, P{self.pitch_mm:g}) "
                f"- {wmm:g} x {hmm:g} mm ({win:.1f} x {hin:.1f} in)")

    def true_size_pixel_px(self, dpi: float = 96) -> int:
        """On-screen pixels per LED so a preview is roughly life-size at `dpi`."""
        return max(2, round(self.pitch_mm / MM_PER_INCH * dpi))


def parse_pitch(value: str) -> float:
    """Accepts '2.5', 'P2.5' or 'p2.5'."""
    pitch = float(value.lstrip("Pp"))
    if pitch not in STANDARD_PITCHES:
        raise ValueError(f"non-standard pitch P{pitch:g}; standard: "
                         + ", ".join(f"P{p:g}" for p in STANDARD_PITCHES))
    return pitch


# Handy whole-display presets: name -> (module, chain, parallel)
PRESETS: dict[str, tuple[str, int, int]] = {
    "64x32": ("64x32", 1, 1),
    "128x32": ("64x32", 2, 1),
    "64x64": ("64x64", 1, 1),
    "128x64": ("64x64", 2, 1),
    "192x64": ("64x64", 3, 1),
    "256x64": ("64x64", 4, 1),
    "128x128": ("64x64", 2, 2),
}


def panel_table(pitches=(2.0, 2.5, 3.0, 4.0, 5.0)) -> str:
    """A text table of the presets: resolution, text grid per font, and physical size per pitch."""
    from .fonts import load_font

    header = ["preset", "modules", "text grid (5x7 / 4x6)"] + [f"P{p:g} size (mm)" for p in pitches]
    rows = []
    for name, (module, chain, parallel) in PRESETS.items():
        cfg = PanelConfig(module, chain, parallel)
        grids = []
        for font_name in ("5x7", "4x6"):
            f = load_font(font_name)
            grids.append(f"{cfg.width // f.width}x{cfg.height // (f.height + 1)}")
        sizes = [f"{cfg.width * p:g} x {cfg.height * p:g}" for p in pitches]
        rows.append([name, f"{chain * parallel}x {module}", " / ".join(grids)] + sizes)
    widths = [max(len(r[i]) for r in rows + [header]) for i in range(len(header))]
    fmt = "  ".join(f"{{:<{w}}}" for w in widths)
    return "\n".join([fmt.format(*header), fmt.format(*("-" * w for w in widths))]
                     + [fmt.format(*r) for r in rows])
