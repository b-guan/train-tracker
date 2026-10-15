"""Where LED frames go: a real HUB75 panel, the RGBMatrixEmulator, or a PNG preview.

Both the hardware library (hzeller/rpi-rgb-led-matrix, module `rgbmatrix`) and
RGBMatrixEmulator expose the same API, so one class drives either.
"""
from __future__ import annotations

import contextlib
import json
import os
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageDraw

from .. import config
from .panel import PanelConfig

EMULATOR_ADAPTERS = ("browser", "pygame", "tkinter", "terminal", "sixel", "turtle")
EMULATOR_STYLES = ("real", "circle", "square")


@dataclass
class MatrixOptions:
    backend: str = "auto"              # auto | hardware | emulator
    brightness: int = 60               # percent
    gpio_mapping: str = "adafruit-hat"  # adafruit-hat-pwm after the GPIO4-GPIO18 jumper mod
    gpio_slowdown: int = 4             # Pi 4 typically needs 2-4
    emulator_adapter: str = "browser"
    emulator_style: str = "real"
    emulator_pixel_size: int | None = None  # None = roughly life-size for the panel pitch
    emulator_port: int = 8888
    open_browser: bool = True


@contextlib.contextmanager
def _chdir(path: Path):
    old = os.getcwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(old)


def _emulator_config(panel: PanelConfig, opts: MatrixOptions) -> dict:
    return {
        "pixel_outline": 0,
        "pixel_size": opts.emulator_pixel_size or panel.true_size_pixel_px(),
        "pixel_style": opts.emulator_style,
        "pixel_glow": 6,
        "display_adapter": opts.emulator_adapter,
        "allow_adapter_fallback": True,
        "icon_path": None,
        "emulator_title": f"MTA Tracker - {panel.describe()}",
        "browser": {
            "_comment": "Written by mta_tracker; regenerated on every run.",
            "port": opts.emulator_port,
            "target_fps": 30,
            "fps_display": False,
            "quality": 90,
            "image_border": True,
            "debug_text": False,
            "image_format": "PNG",
            "open_immediately": opts.open_browser,
        },
        "log_level": "error",
    }


class MatrixOutput:
    """Shows frames on an RGBMatrix (hardware or emulated) via an offscreen canvas + vsync swap."""

    def __init__(self, panel: PanelConfig, opts: MatrixOptions | None = None):
        self.panel = panel
        self.opts = opts or MatrixOptions()
        self.backend = self._resolve_backend()
        if self.backend == "hardware":
            from rgbmatrix import RGBMatrix, RGBMatrixOptions
            self._matrix = self._make_matrix(RGBMatrix, RGBMatrixOptions)
        else:
            # The emulator reads/writes emulator_config.json in the working directory,
            # so give it its own directory instead of littering the project.
            emu_dir = config.CACHE_DIR / "emulator"
            emu_dir.mkdir(parents=True, exist_ok=True)
            (emu_dir / "emulator_config.json").write_text(
                json.dumps(_emulator_config(panel, self.opts), indent=2), encoding="utf-8")
            with _chdir(emu_dir):
                from RGBMatrixEmulator import RGBMatrix, RGBMatrixOptions
                self._matrix = self._make_matrix(RGBMatrix, RGBMatrixOptions)
        self._canvas = self._matrix.CreateFrameCanvas()

    def _resolve_backend(self) -> str:
        if self.opts.backend != "auto":
            return self.opts.backend
        try:
            import rgbmatrix  # noqa: F401
            return "hardware"
        except ImportError:
            return "emulator"

    def _make_matrix(self, matrix_cls, options_cls):
        o = options_cls()
        o.rows = self.panel.module_rows
        o.cols = self.panel.module_cols
        o.chain_length = self.panel.chain
        o.parallel = self.panel.parallel
        o.brightness = self.opts.brightness
        if self.backend == "hardware":
            o.hardware_mapping = self.opts.gpio_mapping
            o.gpio_slowdown = self.opts.gpio_slowdown
            o.drop_privileges = True
        return matrix_cls(options=o)

    def show(self, image: Image.Image) -> None:
        self._canvas.SetImage(image, 0, 0)
        self._canvas = self._matrix.SwapOnVSync(self._canvas)

    def close(self) -> None:
        with contextlib.suppress(Exception):
            self._matrix.Clear()


def preview_image(frame: Image.Image, pixel_size: int = 8, gap: float = 0.2,
                  background=(18, 18, 18)) -> Image.Image:
    """Upscale a panel frame so each LED is drawn as a round dot, like the real thing.

    Unlit LEDs are shown faintly so the panel's grid is visible.
    """
    w, h = frame.size
    out = Image.new("RGB", (w * pixel_size, h * pixel_size), background)
    draw = ImageDraw.Draw(out)
    inset = max(1, round(pixel_size * gap / 2)) if pixel_size >= 4 else 0
    px = frame.load()
    for y in range(h):
        for x in range(w):
            r, g, b = px[x, y]
            color = (r, g, b) if r or g or b else (34, 34, 34)
            x0, y0 = x * pixel_size + inset, y * pixel_size + inset
            draw.ellipse([x0, y0, x0 + pixel_size - 1 - 2 * inset, y0 + pixel_size - 1 - 2 * inset], fill=color)
    return out


class PngOutput:
    """Writes the most recent frame as an LED-style preview PNG on close()."""

    def __init__(self, path: str | Path, panel: PanelConfig, pixel_size: int = 8):
        self.path = Path(path)
        self.panel = panel
        self.pixel_size = pixel_size
        self.last: Image.Image | None = None

    def show(self, image: Image.Image) -> None:
        self.last = image.copy()

    def close(self) -> None:
        if self.last is not None:
            preview_image(self.last, self.pixel_size).save(self.path)
