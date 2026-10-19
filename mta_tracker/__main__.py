"""CLI: `python -m mta_tracker` opens an interactive station search, then the live board."""
from __future__ import annotations

import argparse
import logging
import math
import os
import sys
import time
from typing import NamedTuple, Sequence

from . import config
from . import terminal as keys
from .arrivals import get_arrivals, platform_ids
from .display import AsciiBoard, BoardState, MultiDisplay, SplitFlap
from .feeds import FeedError, FeedPoller, fetch_alerted_routes
from .picker import pick_station
from .stops import Complex, StopIndex, load_index

log = logging.getLogger(__name__)


def parse_args(argv=None) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="mta_tracker", description="Real-time NYC subway arrival board.")
    p.add_argument("query", nargs="*",
                   help="optional text to pre-fill the station search (or, with --once / no terminal, "
                        "the station name or GTFS stop ID to show)")
    p.add_argument("-a", "--also", action="append", default=[], metavar="QUERY",
                   help="another station to rotate through after the first (repeatable); "
                        "on the board, press 'a' to add one")
    p.add_argument("-d", "--direction", choices=["N", "S", "both"], default="both",
                   help="N = northbound/uptown, S = southbound/downtown (default: both)")
    p.add_argument("-n", "--rows", type=int, default=config.DEFAULT_ROWS, help="trains shown per direction")
    p.add_argument("-r", "--refresh", type=int, default=config.DEFAULT_REFRESH,
                   help="seconds between data fetches (default: %(default)s)")
    p.add_argument("-w", "--width", type=int, default=config.DEFAULT_WIDTH, help="board width in characters")
    p.add_argument("--once", action="store_true", help="print one board and exit")
    p.add_argument("--no-color", action="store_true", help="disable ANSI colors")
    p.add_argument("--no-animation", action="store_true", help="disable animations (split-flap transitions, fading 'Now')")
    p.add_argument("-p", "--page-seconds", type=float, default=config.DEFAULT_PAGE_SECONDS,
                   help="alternate between the soonest trains and the next ones every this many "
                        "seconds (default: %(default)s; 0 shows only the soonest)")
    p.add_argument("--refresh-stations", action="store_true", help="re-download the static station list")
    p.add_argument("-v", "--verbose", action="store_true", help="log fetch details to stderr")

    led = p.add_argument_group("LED panel", "mirror the board to a HUB75 LED matrix (real or emulated)")
    led.add_argument("--led", choices=["emulator", "hardware", "auto"],
                     help="enable LED output: 'emulator' previews it on this computer, 'hardware' drives "
                          "a panel on a Raspberry Pi, 'auto' picks hardware when rgbmatrix is installed")
    led.add_argument("--panel", default="128x64", metavar="PRESET",
                     help="whole-display preset (default: %(default)s); see --list-panels")
    led.add_argument("--module", metavar="WxH", help="override the preset: size of each panel module, "
                     "one of 32x16, 32x32, 64x32, 64x64, 128x64")
    led.add_argument("--chain", type=int, help="override the preset: modules chained side by side")
    led.add_argument("--parallel", type=int, help="override the preset: module rows stacked vertically")
    led.add_argument("--pitch", default="2.5", metavar="MM",
                     help="LED pitch in mm, e.g. 2.5 or P3 (default: %(default)s); sets the physical size")
    led.add_argument("--font", choices=["4x6", "5x7", "5x8", "6x10"],
                     help="panel font (default: 5x7 on panels 128px wide or more, else 4x6)")
    led.add_argument("--brightness", type=int, default=60, help="panel brightness 1-100 (default: %(default)s)")
    led.add_argument("--gpio-mapping", default="adafruit-hat",
                     help="hardware: rgbmatrix hardware mapping (default: %(default)s; "
                          "adafruit-hat-pwm after the GPIO4-GPIO18 jumper mod)")
    led.add_argument("--gpio-slowdown", type=int, default=4, help="hardware: GPIO slowdown (Pi 4: 2-4)")
    led.add_argument("--emulator-adapter", default="browser",
                     choices=["browser", "pygame", "tkinter", "terminal", "sixel", "turtle"],
                     help="emulator: where to draw the panel (default: %(default)s, at http://localhost:8888)")
    led.add_argument("--emulator-style", default="real", choices=["real", "circle", "square"],
                     help="emulator: LED look (default: %(default)s; 'real' is browser-only)")
    led.add_argument("--pixel-size", type=int,
                     help="screen pixels per LED for the emulator and snapshots (default: life-size for the pitch)")
    led.add_argument("--no-browser", action="store_true", help="emulator: don't open the browser automatically")
    led.add_argument("--snapshot", metavar="PNG", help="write an LED-panel preview of the station as a PNG and exit")
    led.add_argument("--list-panels", action="store_true", help="list standard panel presets and sizes, then exit")
    return p.parse_args(argv)


def panel_from_args(args: argparse.Namespace):
    from .display.panel import PRESETS, PanelConfig, parse_pitch

    if args.panel not in PRESETS:
        raise ValueError(f"unknown panel preset {args.panel!r}; choose from {', '.join(PRESETS)}")
    module, chain, parallel = PRESETS[args.panel]
    return PanelConfig(module=args.module or module, chain=args.chain or chain,
                       parallel=args.parallel or parallel, pitch_mm=parse_pitch(args.pitch))


def open_led_output(panel, args: argparse.Namespace):
    """The panel connection (hardware or emulator); opened once and reused across stations."""
    from .display.matrix import MatrixOptions, MatrixOutput

    return MatrixOutput(panel, MatrixOptions(
        backend=args.led, brightness=args.brightness, gpio_mapping=args.gpio_mapping,
        gpio_slowdown=args.gpio_slowdown, emulator_adapter=args.emulator_adapter,
        emulator_style=args.emulator_style, emulator_pixel_size=args.pixel_size,
        open_browser=not args.no_browser))


def describe(index: StopIndex, cx: Complex) -> str:
    names = dict.fromkeys([cx.name] + [index.station_name(sid) for sid in cx.station_ids])
    return f"{' / '.join(names)}  [{' '.join(index.route_labels(cx.routes))}]  (id {cx.id})"


def choose_complex(index: StopIndex, query: str, input_fn=input, out=sys.stdout) -> Complex | None:
    matches = index.search(query)
    if not matches:
        print(f"No station matches {query!r}.", file=out)
        return None
    if len(matches) == 1:
        return matches[0]
    for i, cx in enumerate(matches, 1):
        print(f"{i:>3}. {describe(index, cx)}", file=out)
    while True:
        choice = input_fn(f"Pick a station [1-{len(matches)}]: ").strip()
        if choice.isdigit() and 1 <= int(choice) <= len(matches):
            return matches[int(choice) - 1]
        if not choice:
            return None


FRAME_INTERVAL = 1 / 30  # seconds between split-flap animation frames
BACK_KEYS = {"s", "S", "/", keys.ESC, keys.BACKSPACE}
QUIT_KEYS = {"q", "Q", keys.CTRL_C}
ADD_KEYS = {"a", "A"}


def build_board(index: StopIndex, args: argparse.Namespace, term: keys.RawTerminal | None,
                led=None, show_terminal: bool = True):
    """The display(s) for one station: the terminal board, the LED panel, or both."""
    animate = not args.no_animation and not args.once
    displays = []
    if show_terminal:
        color = not args.no_color and sys.stdout.isatty()
        if color and os.name == "nt":
            os.system("")  # enables ANSI escape processing in the Windows console
        displays.append(AsciiBoard(
            index.routes, width=args.width, rows=args.rows, color=color,
            clear=term is not None or (not args.once and sys.stdout.isatty()),
            hint="[s]earch [a]dd [q]uit" if term else "", stream=term.stream if term else None,
            animator=SplitFlap() if animate else None, pulse=not args.no_animation))
    if led is not None:
        from .display.led import LedBoard
        displays.append(LedBoard(led.panel, led, index.routes, font=args.font,
                                 animator=SplitFlap() if animate else None, pulse=not args.no_animation))
    return displays[0] if len(displays) == 1 else MultiDisplay(displays)


class Slot(NamedTuple):
    station: int         # index into the rotation's stations
    page: int
    elapsed: float       # seconds into this page


def rotation_slot(t: float, stations: int, pages: int, page_seconds: float) -> Slot:
    """What's up `t` seconds into the rotation: each station's pages, one station after another."""
    slot, elapsed = divmod(t, page_seconds)
    station, page = divmod(int(slot) % (stations * pages), pages)
    return Slot(station, page, elapsed)


def run(index: StopIndex, stations: Sequence[Complex], args: argparse.Namespace,
        term: keys.RawTerminal | None = None, led=None, show_terminal: bool = True) -> str:
    """Show the live board, rotating through `stations` (each with its pages of trains).

    Returns "search" to go back to the search screen, "add" to add a station, else "quit".
    With a `term`, key presses are read between redraws; without one it just
    sleeps (non-interactive output, --once). `led` is an open LED output to mirror to.
    """
    stations = list(stations)
    board = build_board(index, args, term, led, show_terminal)
    directions = ("N", "S") if args.direction == "both" else (args.direction,)
    poller = FeedPoller(platform_ids(sid for cx in stations for sid in cx.station_ids))

    arrivals: list[list] = [[] for _ in stations]
    updated_at, error = None, None
    alerted: frozenset[str] = frozenset()
    next_fetch = next_render = 0.0
    started = math.floor(time.time())  # renders land on whole seconds, so pages flip on one
    pages = config.PAGES if args.page_seconds > 0 else 1
    # Without paging, each station still gets a turn of the default page length.
    page_seconds = args.page_seconds if args.page_seconds > 0 else config.DEFAULT_PAGE_SECONDS
    try:
        while True:
            if time.time() >= next_fetch:
                try:
                    feeds = poller.poll()
                    updated_at = time.time()
                    arrivals = [get_arrivals(feeds, cx.station_ids, index.station_name, updated_at)
                                for cx in stations]
                    error = None
                except FeedError as e:
                    error = str(e)
                try:
                    alerted = fetch_alerted_routes(poller.session, time.time())
                except Exception as e:  # alerts are extra: keep the last known ones, don't mark the board stale
                    log.warning("Alerts feed failed: %s", e)
                next_fetch = time.time() + args.refresh

            if time.time() >= next_render:  # new content on each second so the clock/ETAs tick
                now = time.time()
                slot = rotation_slot(now - started, len(stations), pages, page_seconds)
                changes = pages > 1 or len(stations) > 1  # the progress dot times the next change
                board.render(BoardState(stations[slot.station].name, arrivals[slot.station], now,
                                        updated_at, error, directions, page=slot.page, pages=pages,
                                        page_elapsed=slot.elapsed if changes else 0.0,
                                        page_seconds=page_seconds if changes else 0.0,
                                        rotating=len(stations) > 1, alerted_routes=alerted))
                if args.once:
                    return "quit"
                next_render = math.floor(time.time()) + 1

            # Between content updates, wake up often enough to draw animation frames.
            wait = max(0.0, next_render - time.time())
            if board.animating:
                wait = min(wait, FRAME_INTERVAL)
            key = term.read_key(timeout=wait) if term else time.sleep(wait)
            if key in QUIT_KEYS:
                return "quit"
            if key in BACK_KEYS:
                return "search"
            if key in ADD_KEYS:
                return "add"
            board.tick()
    except KeyboardInterrupt:
        return "quit"
    finally:
        if term is None:  # the RawTerminal restores the cursor itself
            board.close()


def resolve_stations(index: StopIndex, queries: Sequence[str]) -> list[Complex] | None:
    """Look up each query (asking when one is ambiguous); None if any can't be resolved."""
    stations = []
    for query in queries:
        cx = choose_complex(index, query)
        if cx is None:
            return None
        if cx not in stations:
            stations.append(cx)
    return stations


def interactive(index: StopIndex, args: argparse.Namespace, led=None) -> int:
    """Search screen -> live board, until the user quits.

    On the board, 's' starts over with a new station and 'a' adds one to the rotation.
    """
    query = " ".join(args.query)
    try:
        extra = resolve_stations(index, args.also)  # --also stations join the first one picked
    except (KeyboardInterrupt, EOFError):
        return 130
    if extra is None:
        return 1
    stations: list[Complex] = []
    action = "search"
    try:
        with keys.RawTerminal() as term:
            while True:
                if action == "search":
                    cx, query = pick_station(index, term, query, color=not args.no_color)
                    if cx is None:
                        return 0
                    stations = [cx] + [s for s in extra if s != cx]
                    extra = []
                else:  # add: Esc goes back to the board unchanged
                    cx, _ = pick_station(index, term, "", color=not args.no_color, title="ADD A STATION",
                                         hint="Up/Down move  Enter add  Esc back")
                    if cx is not None and cx not in stations:
                        stations.append(cx)
                action = run(index, stations, args, term, led)
                if action == "quit":
                    return 0
    except KeyboardInterrupt:
        return 0


def snapshot(index: StopIndex, cx: Complex, args: argparse.Namespace, panel) -> int:
    """Render one LED frame for `cx` and save it as an LED-style preview PNG."""
    from .display.matrix import PngOutput

    out = PngOutput(args.snapshot, panel, pixel_size=args.pixel_size or panel.true_size_pixel_px())
    args.once = True
    args.no_animation = True  # a still frame: no flaps mid-turn, "Now" at full brightness
    run(index, [cx], args, led=out, show_terminal=False)
    out.close()
    print(f"Wrote {args.snapshot}: {panel.describe()}")
    return 0


def main(argv=None) -> int:
    args = parse_args(argv)
    logging.basicConfig(level=logging.INFO if args.verbose else logging.ERROR,
                        format="%(levelname)s %(name)s: %(message)s")

    if args.list_panels:
        from .display.panel import panel_table
        print(panel_table())
        return 0
    panel = None
    if args.led or args.snapshot:
        try:
            panel = panel_from_args(args)
        except ValueError as e:
            print(e, file=sys.stderr)
            return 2

    if not (config.CACHE_DIR / "index.json").exists() or args.refresh_stations:
        print("Downloading MTA station list (first run only)...", file=sys.stderr)
    try:
        index = load_index(refresh=args.refresh_stations)
    except Exception as e:
        print(f"Could not load station data: {e}", file=sys.stderr)
        return 1

    tty = sys.stdin.isatty() and sys.stdout.isatty()
    if tty and not args.once and not args.snapshot:
        led = open_led_output(panel, args) if args.led else None
        try:
            return interactive(index, args, led)
        finally:
            if led:
                led.close()

    try:
        query = " ".join(args.query) or input("Station: ")
        stations = resolve_stations(index, [query] + args.also)
    except (KeyboardInterrupt, EOFError):
        return 130
    if stations is None:
        return 1

    if args.snapshot:
        return snapshot(index, stations[0], args, panel)
    led = open_led_output(panel, args) if args.led else None
    try:
        # Headless with a panel (e.g. a systemd service): don't fill the log with terminal boards.
        run(index, stations, args, led=led, show_terminal=led is None or sys.stdout.isatty())
    finally:
        if led:
            led.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
